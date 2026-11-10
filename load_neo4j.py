"""Load the customer / device / merchant graph into Neo4j (the task 2 model) for the period the API explains.

(:Customer)-[:USED_DEVICE {times, first_seen, last_seen, tx_count}]->(:Device)
(:Customer)-[:PAID {transaction_id, amount, time, fraud_label, label_available_at, payment_channel, device_id}]->(:Merchant)

Two things are added to the task 2 graph so the API can ask "what did the graph look like at payment time":
- PAID.label_available_at: a fraud label only counts once it exists (60 days after the payment), so the
  API never uses a label that the investigator could not have seen yet.
- an index on PAID.device_id and PAID.time, so "who paid from this device in the 90 days before" is fast.

Default window: 2025-08-01 to 2026-01-01 = the validation split (Nov-Dec 2025) plus 90 days of history
(about 360,000 payments). MERGE + uniqueness constraints make the load safe to run twice.

Run:  python load_neo4j.py
"""
import pandas as pd
from neo4j import GraphDatabase

import settings
from tables import read_table

LOAD_FROM = settings.env("GRAPH_FROM", "2025-08-01")
LOAD_TO = settings.env("GRAPH_TO", "2026-01-01")
BATCH = 5000

driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
driver.verify_connectivity()
print("Connected to Neo4j:", driver.get_server_info().agent)


def run(query, **params):
    records, _, _ = driver.execute_query(query, params)
    return [r.data() for r in records]


def batches(df):
    rows = df.astype(object).where(df.notna(), None).to_dict("records")
    for i in range(0, len(rows), BATCH):
        yield rows[i:i + BATCH]


def main():
    tx = read_table(settings.DATA_PATH, "transactions", usecols=[
        "transaction_id", "customer_id", "merchant_id", "device_id", "transaction_amount",
        "payment_channel", "transaction_time"])
    t = pd.to_datetime(tx["transaction_time"], utc=True)
    tx = tx[(t >= pd.Timestamp(LOAD_FROM, tz="UTC")) & (t < pd.Timestamp(LOAD_TO, tz="UTC"))].copy()
    labels = read_table(settings.DATA_PATH, "labels", usecols=["transaction_id", "fraud_label", "label_available_at"])
    tx = tx.merge(labels, on="transaction_id", how="left")
    customers = read_table(settings.DATA_PATH, "customers")
    merchants = read_table(settings.DATA_PATH, "merchants")
    devices = read_table(settings.DATA_PATH, "devices")
    print(f"Window {LOAD_FROM} to {LOAD_TO}: {len(tx):,} payments, {tx['customer_id'].nunique():,} customers, "
          f"{tx['device_id'].nunique():,} devices, {tx['merchant_id'].nunique():,} merchants")

    for q in [
        "CREATE CONSTRAINT customer_id IF NOT EXISTS FOR (c:Customer) REQUIRE c.customer_id IS UNIQUE",
        "CREATE CONSTRAINT device_id IF NOT EXISTS FOR (d:Device) REQUIRE d.device_id IS UNIQUE",
        "CREATE CONSTRAINT merchant_id IF NOT EXISTS FOR (m:Merchant) REQUIRE m.merchant_id IS UNIQUE",
        "CREATE CONSTRAINT paid_tx_id IF NOT EXISTS FOR ()-[p:PAID]-() REQUIRE p.transaction_id IS UNIQUE",
        "CREATE INDEX paid_device IF NOT EXISTS FOR ()-[p:PAID]-() ON (p.device_id)",
        "CREATE INDEX paid_time IF NOT EXISTS FOR ()-[p:PAID]-() ON (p.time)",
    ]:
        run(q)

    c = customers[customers["customer_id"].isin(tx["customer_id"])]
    c = c.rename(columns={"customer_id": "id", "customer_age": "age", "home_city": "city"})[["id", "age", "city", "region"]]
    for rows in batches(c):
        run("UNWIND $rows AS row MERGE (c:Customer {customer_id: row.id}) "
            "SET c.customer_age = row.age, c.home_city = row.city, c.region = row.region", rows=rows)

    d = devices[devices["device_id"].isin(tx["device_id"])].rename(columns={"device_id": "id", "device_kind": "kind"})
    for rows in batches(d[["id", "kind"]]):
        run("UNWIND $rows AS row MERGE (d:Device {device_id: row.id}) SET d.device_kind = row.kind", rows=rows)

    m = merchants[merchants["merchant_id"].isin(tx["merchant_id"])].copy()
    m["city"] = m["merchant_location"].str.extract(r'"city":"([^"]+)"')[0]
    m = m.rename(columns={"merchant_id": "id", "synthetic_name": "name", "merchant_category": "cat"})
    for rows in batches(m[["id", "name", "cat", "city"]]):
        run("UNWIND $rows AS row MERGE (m:Merchant {merchant_id: row.id}) "
            "SET m.name = row.name, m.merchant_category = row.cat, m.city = row.city", rows=rows)

    used = (tx.dropna(subset=["device_id"]).sort_values("transaction_time")
              .groupby(["customer_id", "device_id"])["transaction_time"].apply(list).reset_index())
    used.columns = ["c", "d", "times"]
    for rows in batches(used):
        run("""UNWIND $rows AS row
               MATCH (c:Customer {customer_id: row.c}) MATCH (d:Device {device_id: row.d})
               MERGE (c)-[u:USED_DEVICE]->(d)
               SET u.times = [t IN row.times | datetime(t)], u.tx_count = size(row.times),
                   u.first_seen = datetime(row.times[0]), u.last_seen = datetime(row.times[-1])""", rows=rows)

    paid = tx.rename(columns={"transaction_id": "tx", "customer_id": "c", "merchant_id": "m", "device_id": "dev",
                              "transaction_amount": "amount", "transaction_time": "time",
                              "fraud_label": "fraud", "label_available_at": "avail", "payment_channel": "ch"})
    for i, rows in enumerate(batches(paid[["tx", "c", "m", "dev", "amount", "time", "fraud", "avail", "ch"]])):
        run("""UNWIND $rows AS row
               MATCH (c:Customer {customer_id: row.c}) MATCH (m:Merchant {merchant_id: row.m})
               MERGE (c)-[p:PAID {transaction_id: row.tx}]->(m)
               SET p.amount = row.amount, p.time = datetime(row.time), p.fraud_label = toInteger(row.fraud),
                   p.label_available_at = datetime(row.avail), p.payment_channel = row.ch, p.device_id = row.dev""",
            rows=rows)
        if i % 10 == 0:
            print(f"  PAID {min((i + 1) * BATCH, len(paid)):,}/{len(paid):,}")

    counts = run("""MATCH (n) WITH labels(n)[0] AS label, count(*) AS n RETURN label, n ORDER BY label""")
    rels = run("""MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS n ORDER BY type""")
    print("Nodes:", counts)
    print("Relationships:", rels)


if __name__ == "__main__":
    main()
    driver.close()
