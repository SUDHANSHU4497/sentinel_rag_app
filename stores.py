"""The three data sources behind POST /explain.

TransactionStore  MongoDB (task 1) or Supabase (Project Work 5): the payment, its feature snapshot, the customer
                  and the client's policy tables (hard rules, block/allow lists, cutoffs).
GraphStore        Neo4j (task 2): the device and customer neighbourhood, as it looked at payment time.
PolicyStore       Qdrant (task 4) + Gemini Embedding 2: the policy chunks that match the fired signals.

Every store returns plain dicts, so the API and the prompt do not care which database a fact came from.
None of them returns the fraud label: it is only known 60 days after the payment.
"""
import json

import requests

import settings
from embeddings import embed, query_input


def _json(v):
    return json.loads(v) if isinstance(v, str) and v[:1] in "[{" else v


# ====================================================================================================
# Transactions + features
# ====================================================================================================
class MongoStore:
    """Task 1 design: transactions reference the customer; merchant, device, features and score are embedded."""

    def __init__(self):
        from pymongo import MongoClient
        self.client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=10000)
        self.db = self.client[settings.MONGODB_DB]

    def ping(self):
        self.client.admin.command("ping")
        return "mongodb"

    def get_transaction(self, tx_id):
        tx = self.db.transactions.find_one({"_id": tx_id})
        if tx is None:
            return None
        tx["transaction_id"] = tx.pop("_id")
        cust = self.db.customers.find_one({"_id": tx["customer_id"]}, {"devices": 0}) or {}
        cust.pop("_id", None)
        tx["customer"] = cust
        return tx

    def policy_tables(self):
        rules = list(self.db.hard_rules.find({"enabled": True}, {"_id": 0}).sort("priority", -1))
        lists = {}
        for e in self.db.list_entries.find({}, {"_id": 0, "list_type": 1, "entity_id": 1}):
            lists.setdefault(e["list_type"], set()).add(e["entity_id"])
        thr = self.db.threshold_sets.find_one({"status": "active_synthetic"}, {"_id": 0}) or {}
        return rules, lists, thr


class SupabaseStore:
    """Same output as MongoStore, read from the Supabase REST API (tables from sql/schema.sql + ingest.py)."""

    def __init__(self):
        if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
            raise SystemExit("STORE=supabase needs SUPABASE_URL and SUPABASE_KEY in .env")
        self.base = settings.SUPABASE_URL.rstrip("/") + "/rest/v1/"
        self.h = {"apikey": settings.SUPABASE_KEY, "Authorization": f"Bearer {settings.SUPABASE_KEY}",
                  "Accept-Profile": settings.SUPABASE_SCHEMA}

    def _get(self, table, **params):
        r = requests.get(self.base + table, headers=self.h, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def ping(self):
        self._get("threshold_sets", select="threshold_id", limit=1)
        return "supabase"

    def get_transaction(self, tx_id):
        rows = self._get("transactions", transaction_id=f"eq.{tx_id}", select="*")
        if not rows:
            return None
        t = rows[0]
        f = (self._get("features", transaction_id=f"eq.{tx_id}", select="*") or [{}])[0]
        m = (self._get("merchants", merchant_id=f"eq.{t['merchant_id']}", select="*") or [{}])[0]
        d = (self._get("devices", device_id=f"eq.{t['device_id']}", select="*") or [{}])[0] if t.get("device_id") else None
        c = (self._get("customers", customer_id=f"eq.{t['customer_id']}", select="*") or [{}])[0]
        try:
            s = (self._get("decision_audit", transaction_id=f"eq.{tx_id}",
                           select="fraud_probability,decision,risk_level,model_version") or [None])[0]
        except requests.HTTPError:
            s = None
        tx = {
            "transaction_id": tx_id, "customer_id": t["customer_id"], "transaction_time": t["transaction_time"],
            "amount": float(t["transaction_amount"]), "amount_paise": t.get("amount_paise"),
            "payment_channel": t["payment_channel"],
            "merchant": {"merchant_id": t["merchant_id"], "name": m.get("synthetic_name"),
                         "merchant_category": t["merchant_category"], "location": _json(t["merchant_location"])},
            "device": {"device_id": t["device_id"], "device_kind": d.get("device_kind")} if d else None,
            "customer_age": t.get("customer_age"), "customer_location": _json(t.get("customer_location")),
            "account_age_days": t.get("account_age"), "previous_transactions": t.get("previous_transactions"),
            "average_transaction_value": t.get("average_transaction_value"),
            "failed_transactions": t.get("failed_transactions"), "split": t.get("split"),
            "features": {k: _json(v) for k, v in f.items() if k != "is_synthetic"},
            "customer": {k: c.get(k) for k in ("created_at", "customer_age", "home_city", "region")},
        }
        if s:
            tx["score"] = s
        return tx

    def policy_tables(self):
        rules = sorted([dict(r, expression=_json(r["expression"])) for r in self._get("hard_rules", enabled="eq.true")],
                       key=lambda r: -int(r["priority"]))
        lists = {}
        for e in self._get("list_entries", select="list_type,entity_id"):
            lists.setdefault(e["list_type"], set()).add(e["entity_id"])
        thr = (self._get("threshold_sets", status="eq.active_synthetic") or [{}])[0]
        return rules, lists, thr


def transaction_store():
    return SupabaseStore() if settings.STORE == "supabase" else MongoStore()


# ====================================================================================================
# Neo4j neighbourhood
# ====================================================================================================
# Every query takes the payment time $t and looks only BACKWARDS (the 90 days before it). A fraud label
# only counts if it was available by then (label_available_at <= $t), so nothing from the future leaks in.

CUSTOMER_Q = """
WITH datetime($t) AS t
MATCH (c:Customer {customer_id: $cid})
OPTIONAL MATCH (c)-[p:PAID]->(m:Merchant) WHERE p.time < t AND p.time >= t - duration({days: 90})
RETURN c.customer_age AS age, c.home_city AS home_city,
       count(p) AS payments_90d, round(coalesce(sum(p.amount), 0), 2) AS amount_90d,
       count(DISTINCT p.device_id) AS devices_90d, count(DISTINCT m) AS merchants_90d,
       sum(CASE WHEN p.fraud_label = 1 AND p.label_available_at <= t THEN 1 ELSE 0 END) AS own_known_fraud,
       sum(CASE WHEN m.merchant_category = $mcc THEN 1 ELSE 0 END) AS payments_same_category_90d
"""

DEVICE_Q = """
WITH datetime($t) AS t
MATCH (c:Customer)-[p:PAID]->() WHERE p.device_id = $did AND p.time < t AND p.time >= t - duration({days: 90})
WITH t, c, count(p) AS n, max(p.time) AS last_time,
     sum(CASE WHEN p.fraud_label = 1 AND p.label_available_at <= t THEN 1 ELSE 0 END) AS fraud_on_device
OPTIONAL MATCH (c)-[f:PAID {fraud_label: 1}]->() WHERE f.label_available_at <= t
RETURN c.customer_id AS customer_id, n AS payments_from_device, toString(last_time) AS last_used,
       last_time >= t - duration({days: 7}) AS used_in_last_7d, fraud_on_device,
       count(f) AS customer_known_fraud
ORDER BY payments_from_device DESC
"""

TWO_HOP_Q = """
WITH datetime($t) AS t
MATCH (c:Customer {customer_id: $cid})-[u:USED_DEVICE]->(d:Device)<-[u2:USED_DEVICE]-(o:Customer)
WHERE o <> c
  AND any(x IN u.times  WHERE x < t AND x >= t - duration({days: 90}))
  AND any(x IN u2.times WHERE x < t AND x >= t - duration({days: 90}))
OPTIONAL MATCH (o)-[f:PAID {fraud_label: 1}]->() WHERE f.label_available_at <= t
WITH o, collect(DISTINCT d.device_id) AS via, count(DISTINCT f) AS known_fraud
RETURN o.customer_id AS customer_id, via AS shared_devices, known_fraud
ORDER BY known_fraud DESC, size(via) DESC
LIMIT 25
"""

MERCHANT_Q = """
WITH datetime($t) AS t
MATCH (m:Merchant {merchant_id: $mid})<-[p:PAID]-()
WHERE p.time < t AND p.time >= t - duration({days: 90})
RETURN m.name AS name, m.merchant_category AS category, m.city AS city, count(p) AS payments_90d,
       sum(CASE WHEN p.fraud_label = 1 AND p.label_available_at <= t THEN 1 ELSE 0 END) AS known_fraud_90d
"""


class GraphStore:
    def __init__(self):
        from neo4j import GraphDatabase
        self.driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))

    def ping(self):
        self.driver.verify_connectivity()
        return "neo4j"

    def _run(self, q, **p):
        records, _, _ = self.driver.execute_query(q, p)
        return [r.data() for r in records]

    def neighbourhood(self, tx):
        t, cid = tx["transaction_time"], tx["customer_id"]
        did = (tx.get("device") or {}).get("device_id")
        mcc = tx["merchant"]["merchant_category"]
        cust = (self._run(CUSTOMER_Q, t=t, cid=cid, mcc=mcc) or [{}])[0]
        out = {"window": "90 days before the payment; fraud labels counted only if available by payment time",
               "in_graph": bool(cust.get("home_city") is not None or cust.get("payments_90d")),
               "customer": cust}
        if did:
            users = self._run(DEVICE_Q, t=t, did=did)
            others = [u for u in users if u["customer_id"] != cid]
            out["device"] = {
                "device_id": did,
                "customers_90d": len(users),
                "customers_7d": sum(1 for u in users if u["used_in_last_7d"]),
                "other_customers": others[:10],
                "other_customers_with_known_fraud": sum(1 for u in others if u["customer_known_fraud"] > 0),
                "known_fraud_payments_from_device": sum(u["fraud_on_device"] for u in users),
                "seen_for_this_customer_90d": any(u["customer_id"] == cid for u in users),
            }
        else:
            out["device"] = None
        hop = self._run(TWO_HOP_Q, t=t, cid=cid)
        out["two_hop"] = {"customers_sharing_a_device_90d": len(hop),
                          "of_them_with_known_fraud": sum(1 for h in hop if h["known_fraud"] > 0),
                          "examples": hop[:5]}
        out["merchant"] = (self._run(MERCHANT_Q, t=t, mid=tx["merchant"]["merchant_id"]) or [{}])[0]
        return out


# ====================================================================================================
# Qdrant policy chunks
# ====================================================================================================
POLICY_TYPES = ["playbooks", "regulatory_exercises", "guidelines", "rba_guides"]

# one search question per signal, written as an investigator would ask it. Each wording was checked
# so that its top hit (policy documents only) is the exercise that holds the rule for that signal.
SIGNAL_QUERIES = {
    "R01_NEW_DEVICE": "payment from a device the customer has not used in the preceding 90 days, or a missing fingerprint",
    "R02_GEO_MISMATCH": "how to review a location change or a large customer to merchant distance",
    "R03_ODD_HOUR": "is a payment between midnight and 05:00 IST proof of fraud, and how is the hour derived",
    "R04_FAILED_ATTEMPTS": "which failed payment outcomes count as retries before this authorisation",
    "R05_AMOUNT_SPIKE": "amount much higher than the customer's 90 day average spending, or no history",
    "R06_NEW_ACCOUNT": "is a young account alone enough to call a payment fraud",
    "R07_VELOCITY": "how to review a burst of many payments within one hour",
    "R08_HIGH_RISK_MCC": "how to write a risk explanation for a high risk merchant category using only facts from the saved input",
    "SHARED_DEVICE": "how to review a payment made from a device shared by many customers",
    "KNOWN_FRAUD_NEARBY": "how to write up evidence and unknowns when a linked customer has confirmed fraud",
    "POLICY": "what are the probability cutoffs for allow, review and block and does a blocklist take precedence",
}


class PolicyStore:
    def __init__(self):
        from qdrant_client import QdrantClient, models
        self.models = models
        self.client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, timeout=60,
                                   check_compatibility=False)

    def ping(self):
        self.client.get_collection(settings.COLLECTION)
        return "qdrant"

    def search(self, question, k=5, types=None):
        """Top k chunks for one question. types=None searches every document type."""
        flt = None
        if types:
            flt = self.models.Filter(must=[self.models.FieldCondition(
                key="document_type", match=self.models.MatchAny(any=types))])
        vec = embed([query_input(question)])[0]
        res = self.client.query_points(settings.COLLECTION, query=vec, limit=k, query_filter=flt, with_payload=True)
        return [{**p.payload, "score": round(p.score, 4)} for p in res.points]

    def for_signals(self, signals, k=settings.TOP_K):
        """One search per fired signal (policy documents only), then the best new chunk of each search
        in turn, so every signal gets at least one chunk before any signal gets a second one."""
        queries = [SIGNAL_QUERIES[s] for s in signals if s in SIGNAL_QUERIES] + [SIGNAL_QUERIES["POLICY"]]
        vecs = embed([query_input(q) for q in queries])
        flt = self.models.Filter(must=[self.models.FieldCondition(
            key="document_type", match=self.models.MatchAny(any=POLICY_TYPES))])
        per_query = []
        for q, v in zip(queries, vecs):
            res = self.client.query_points(settings.COLLECTION, query=v, limit=3, query_filter=flt, with_payload=True)
            per_query.append([{**p.payload, "score": round(p.score, 4), "matched_query": q} for p in res.points])
        picked, seen = [], set()
        for rank in range(3):
            for hits in per_query:
                if rank < len(hits) and hits[rank]["chunk_id"] not in seen and len(picked) < max(k, len(queries)):
                    picked.append(hits[rank])
                    seen.add(hits[rank]["chunk_id"])
        return picked
