"""Load the transactions the API explains into MongoDB (same document design as task 1, plus the features).

customers    : one document per customer, devices EMBEDDED (a customer has about 2 devices)
transactions : one document per payment, the customer REFERENCED by customer_id; merchant, device,
               the feature snapshot and the (simulated) score are embedded, because the API always
               reads them together with the payment and they never change after authorisation
hard_rules, threshold_sets, list_entries : the client's policy tables (blocklist, allowlist, cutoffs)
labels       : fraud labels in their own collection. The API never reads it (a label only exists
               60 days after the payment); run_tests.py uses it to pick 5 fraud and 5 genuine cases.

Run:  python load_mongo.py          (LOAD_SPLITS=validation by default; "validation,holdout" or "all" for more)
"""
import json
import math

import pandas as pd
from pymongo import ASCENDING, MongoClient, ReplaceOne

import settings
from tables import read_table

SPLITS = settings.env("LOAD_SPLITS", "validation")
SPLITS = None if SPLITS == "all" else [s.strip() for s in SPLITS.split(",")]


def clean(v):
    """Turn pandas values into plain JSON/BSON values (NaN -> None, numpy -> python)."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if hasattr(v, "item"):
        return v.item()
    return v


def as_json(v):
    """Parse the JSON text columns (locations, reason code lists)."""
    v = clean(v)
    return json.loads(v) if isinstance(v, str) and v[:1] in "[{" else v


def main():
    client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=10000)
    client.admin.command("ping")  # fails straight away on a wrong URI, user or IP rule
    db = client[settings.MONGODB_DB]
    print("Connected to MongoDB, database:", settings.MONGODB_DB)

    tx = read_table(settings.DATA_PATH, "transactions", SPLITS)
    ids = set(tx["transaction_id"])
    feats = read_table(settings.DATA_PATH, "features", SPLITS).set_index("transaction_id")
    labels = read_table(settings.DATA_PATH, "labels", SPLITS)
    merchants = read_table(settings.DATA_PATH, "merchants").set_index("merchant_id")
    devices = read_table(settings.DATA_PATH, "devices").set_index("device_id")
    customers = read_table(settings.DATA_PATH, "customers")
    try:  # the simulated score at authorisation (optional: decision_audit is large)
        audit = read_table(settings.DATA_PATH, "decision_audit", SPLITS,
                           usecols=["transaction_id", "fraud_probability", "decision", "risk_level", "model_version"])
        audit = audit[audit["transaction_id"].isin(ids)].set_index("transaction_id")
    except SystemExit:
        audit = pd.DataFrame()
        print("decision_audit not found: transactions are loaded without the simulated score")
    print(f"Read {len(tx):,} transactions, {len(feats):,} feature rows, {len(audit):,} scores")

    # ---- customers with their devices embedded (devices seen in the loaded transactions) ----
    dev_by_cust = tx.dropna(subset=["device_id"]).groupby("customer_id")["device_id"].unique()
    cust_docs = []
    for c in customers[customers["customer_id"].isin(tx["customer_id"])].itertuples():
        devs = dev_by_cust.get(c.customer_id, [])
        cust_docs.append({
            "_id": c.customer_id, "created_at": c.created_at, "customer_age": clean(c.customer_age),
            "home_city": c.home_city, "region": c.region,
            "devices": [{"device_id": d, "device_kind": devices["device_kind"].get(d)} for d in devs],
        })

    # ---- transactions with merchant, device, features and score embedded ----
    feat_cols = [c for c in feats.columns if c not in ("is_synthetic",)]
    tx_docs = []
    for r in tx.itertuples(index=False):
        m = merchants.loc[r.merchant_id]
        doc = {
            "_id": r.transaction_id, "customer_id": r.customer_id,
            "transaction_time": r.transaction_time, "amount": clean(r.transaction_amount),
            "amount_paise": clean(r.amount_paise), "payment_channel": r.payment_channel,
            "merchant": {"merchant_id": r.merchant_id, "name": m["synthetic_name"],
                         "merchant_category": r.merchant_category, "location": as_json(r.merchant_location)},
            "device": None if pd.isna(r.device_id) else
                      {"device_id": r.device_id, "device_kind": devices["device_kind"].get(r.device_id)},
            "customer_age": clean(r.customer_age), "customer_location": as_json(r.customer_location),
            "account_age_days": clean(r.account_age), "previous_transactions": clean(r.previous_transactions),
            "average_transaction_value": clean(r.average_transaction_value),
            "failed_transactions": clean(r.failed_transactions), "split": r.split,
        }
        if r.transaction_id in feats.index:
            f = feats.loc[r.transaction_id]
            doc["features"] = {c: as_json(f[c]) for c in feat_cols}
        if len(audit) and r.transaction_id in audit.index:
            a = audit.loc[r.transaction_id]
            doc["score"] = {"fraud_probability": clean(a["fraud_probability"]), "decision": a["decision"],
                            "risk_level": a["risk_level"], "model_version": a["model_version"]}
        tx_docs.append(doc)

    label_docs = [{"_id": r.transaction_id, "fraud_label": int(r.fraud_label), "label_source": r.label_source,
                   "label_available_at": r.label_available_at, "split": r.split} for r in labels.itertuples()]

    # ReplaceOne + upsert: running the load twice gives the same documents, never copies
    for name, docs in [("customers", cust_docs), ("transactions", tx_docs), ("labels", label_docs)]:
        col = db[name]
        for i in range(0, len(docs), 5000):
            col.bulk_write([ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in docs[i:i + 5000]], ordered=False)
        print(f"{name}: {col.count_documents({}):,} documents")

    # ---- the policy tables the hard rules need (small: 2 rules, 1 threshold set, ~140 list entries) ----
    for name in ["hard_rules", "threshold_sets", "list_entries"]:
        t = read_table(settings.DATA_PATH, name)
        id_col = t.columns[0]
        docs = [{"_id": r[id_col], **{k: as_json(v) for k, v in r.items()}} for r in t.to_dict("records")]
        db[name].bulk_write([ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in docs])
        print(f"{name}: {db[name].count_documents({}):,} documents")

    db.transactions.create_index([("customer_id", ASCENDING), ("transaction_time", ASCENDING)])
    db.transactions.create_index([("transaction_time", ASCENDING)])
    db.labels.create_index([("split", ASCENDING), ("fraud_label", ASCENDING)])
    print("Indexes:", list(db.transactions.index_information()))


if __name__ == "__main__":
    main()
