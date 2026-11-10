"""SENTINEL fraud-explain API.

POST /explain {"transaction_id": "TX_..."} ->
    risk summary, the reason codes that fired, a recommended action and the cited policy sources.

Run:  uvicorn api:app --port 8000      then open http://127.0.0.1:8000/docs
"""
import time
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import llm
import settings
from stores import GraphStore, PolicyStore, transaction_store

REASON_TEXT = {  # wording of the SENTINEL explanations (decision_audit / investigator notes)
    "R01_NEW_DEVICE": "Device not observed for this customer in the preceding 90 days",
    "R02_GEO_MISMATCH": "Unusual observed city or customer to merchant distance above 500 km",
    "R03_ODD_HOUR": "Authorisation requested between midnight and 05:00 IST",
    "R04_FAILED_ATTEMPTS": "At least three failed payment outcomes observed in the preceding 24 hours",
    "R05_AMOUNT_SPIKE": "Amount is at least five times the observed 90 day average",
    "R06_NEW_ACCOUNT": "Account age is below 30 days",
    "R07_VELOCITY": "At least four prior authorisations observed in the preceding hour",
    "R08_HIGH_RISK_MCC": "Elevated category flag (gaming, gift_cards or electronics) under the synthetic teaching policy",
}
ACTION_RANK = {"ALLOW": 0, "REVIEW": 1, "BLOCK": 2}
FEATURE_KEYS = ["feature_as_of", "amount_to_avg_ratio", "is_new_device", "customer_merchant_distance_km",
                "is_new_city", "hour_of_day", "is_night", "has_recent_failures", "is_new_account",
                "txn_count_last_1h", "txn_amount_last_24h_paise", "distinct_customers_per_device_7d",
                "combined_risk_flags", "mcc_target_encoded_rate", "missing_customer_location",
                "missing_device", "cold_start"]

app = FastAPI(title="SENTINEL fraud explain API", version="1.0.0",
              description="Explain the risk of one payment and cite the policy (synthetic SENTINEL data).")
_stores = {}


def stores():
    """Open the three connections once, on the first request."""
    if not _stores:
        _stores["tx"], _stores["graph"], _stores["policy"] = transaction_store(), GraphStore(), PolicyStore()
        _stores["rules"] = _stores["tx"].policy_tables()
    return _stores


class ExplainRequest(BaseModel):
    transaction_id: str = Field(..., examples=["TX_0000817832"])  # an ID from the loaded validation split
    include_context: bool = Field(False, description="also return the full context sent to the LLM")


# ----------------------------------------------------------------------------------------------------
# Deterministic policy: hard rules first, then the score cutoffs (0.30 / 0.60 / 0.85)
# ----------------------------------------------------------------------------------------------------
def apply_policy(tx, rules, lists, thr):
    medium, high, critical = (float(thr.get(k, d)) for k, d in
                              [("medium_from", 0.30), ("high_from", 0.60), ("critical_from", 0.85)])
    fired_rules = []
    for r in rules:  # sorted by priority, highest first: the blocklist (100) precedes the allowlist (10)
        expr = r["expression"]
        if expr.get("operator") != "in_list":
            continue
        field = expr["field"]
        value = (tx.get("device") or {}).get("device_id") if field == "device_id" else tx.get(field)
        if value and value in lists.get(expr["list"], set()):
            fired_rules.append({"rule_id": r["rule_id"], "action": r["action"], "priority": int(r["priority"])})

    score = (tx.get("score") or {}).get("fraud_probability")
    if score is None:
        level, action = None, None
    else:
        level = "LOW" if score < medium else "MEDIUM" if score < high else "HIGH" if score < critical else "CRITICAL"
        action = "ALLOW" if score < high else "REVIEW" if score < critical else "BLOCK"
    if any(r["action"] == "BLOCK" for r in fired_rules):
        action = "BLOCK"
    elif any(r["action"] == "CAP_AT_REVIEW" for r in fired_rules) and action == "BLOCK":
        action = "REVIEW"
    return {"score": score, "score_note": "simulated, not calibrated (decision_audit)",
            "cutoffs": {"medium_from": medium, "review_from": high, "block_from": critical},
            "risk_level": level, "hard_rules_fired": fired_rules, "policy_action": action}


def to_ist(ts):
    t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return (t + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M IST")


def signals_for(codes, graph):
    s = list(codes)
    dev = graph.get("device") or {}
    if dev.get("customers_90d", 0) >= 3 or dev.get("customers_7d", 0) >= 2:
        s.append("SHARED_DEVICE")
    if dev.get("other_customers_with_known_fraud") or graph["two_hop"]["of_them_with_known_fraud"] \
            or graph["customer"].get("own_known_fraud"):
        s.append("KNOWN_FRAUD_NEARBY")
    return s


def build_context(tx, graph, policy, chunks):
    f = tx.get("features") or {}
    return {
        "TRANSACTION": {
            "transaction_id": tx["transaction_id"], "time_utc": tx["transaction_time"],
            "time_ist": to_ist(tx["transaction_time"]), "amount_inr": tx["amount"],
            "payment_channel": tx["payment_channel"], "merchant": tx["merchant"], "device": tx.get("device"),
            "customer_id": tx["customer_id"], "customer_age": tx.get("customer_age"),
            "customer_location": tx.get("customer_location"),
            "customer_home_city": (tx.get("customer") or {}).get("home_city"),
            "account_age_days": tx.get("account_age_days"), "previous_transactions": tx.get("previous_transactions"),
            "average_transaction_value_inr": tx.get("average_transaction_value"),
            "failed_transactions": tx.get("failed_transactions"),
        },
        "FEATURES_AT_AUTHORISATION": {k: f.get(k) for k in FEATURE_KEYS},
        "FIRED_REASON_CODES": [{"code": c, "meaning": REASON_TEXT.get(c, c)} for c in f.get("reason_codes", [])],
        "GRAPH_NEIGHBOURHOOD": graph,
        "SCORE_AND_POLICY": policy,
        "POLICY_CHUNKS": [{"chunk_id": c["chunk_id"], "document_title": c["document_title"],
                           "document_type": c["document_type"], "source_body": c["source_body"], "text": c["text"]}
                          for c in chunks],
    }


@app.get("/health")
def health():
    s = stores()
    return {"status": "ok", "stores": [s["tx"].ping(), s["graph"].ping(), s["policy"].ping()],
            "llm": f"{settings.LLM_PROVIDER}:{settings.LLM_MODEL}", "embeddings": settings.EMBED_MODEL}


@app.post("/explain")
def explain(req: ExplainRequest):
    t0 = time.perf_counter()
    s = stores()
    tx = s["tx"].get_transaction(req.transaction_id)
    if tx is None:
        raise HTTPException(404, f"{req.transaction_id} not found in {settings.STORE}")
    t1 = time.perf_counter()
    graph = s["graph"].neighbourhood(tx)
    t2 = time.perf_counter()
    codes = (tx.get("features") or {}).get("reason_codes", []) or []
    policy = apply_policy(tx, *s["rules"])
    chunks = s["policy"].for_signals(signals_for(codes, graph))
    t3 = time.perf_counter()
    context = build_context(tx, graph, policy, chunks)
    answer, usage = llm.explain(context)
    t4 = time.perf_counter()

    warnings = []
    # reason codes: the list comes from the feature snapshot, the LLM only adds the evidence text
    evidence = {r.get("code"): r.get("evidence") for r in answer.get("reason_codes", []) if isinstance(r, dict)}
    extra = sorted(set(evidence) - set(codes))
    if extra:
        warnings.append(f"LLM named reason codes that did not fire, dropped: {extra}")
    reason_codes = [{"code": c, "description": REASON_TEXT.get(c, c), "evidence": evidence.get(c) or REASON_TEXT.get(c, c)}
                    for c in codes]

    # citations: keep only chunks that were really in the context, and add where they come from
    by_id = {c["chunk_id"]: c for c in chunks}
    cited = []
    for c in answer.get("cited_sources", []):
        cid = c.get("chunk_id") if isinstance(c, dict) else c
        if cid in by_id:
            ch = by_id[cid]
            cited.append({"document_id": ch["source_document"], "document_title": ch["document_title"],
                          "document_type": ch["document_type"], "source_body": ch["source_body"],
                          "chunk_id": cid, "chunk_number": ch["chunk_number"], "retrieval_score": ch["score"],
                          "used_for": c.get("used_for") if isinstance(c, dict) else None,
                          "text": ch["text"]})
        else:
            warnings.append(f"LLM cited a chunk that was not retrieved, dropped: {cid}")

    # action guardrail: hard rules always win, and the LLM may raise the policy action but never lower it
    action = str(answer.get("recommended_action", "")).upper()
    if action not in ACTION_RANK:
        warnings.append(f"LLM action {action!r} is not ALLOW/REVIEW/BLOCK")
        action = policy["policy_action"] or "REVIEW"
    final, overridden = action, False
    if policy["policy_action"] and ACTION_RANK[action] < ACTION_RANK[policy["policy_action"]]:
        final, overridden = policy["policy_action"], True
    if any(r["action"] == "CAP_AT_REVIEW" for r in policy["hard_rules_fired"]) and final == "BLOCK" \
            and not any(r["action"] == "BLOCK" for r in policy["hard_rules_fired"]):
        final, overridden = "REVIEW", True
    if overridden:
        warnings.append(f"LLM action {action} replaced by policy action {final}")

    out = {
        "transaction_id": tx["transaction_id"],
        "as_of": tx["transaction_time"],
        "risk_summary": answer.get("risk_summary"),
        "risk_level": answer.get("risk_level") or policy["risk_level"],
        "reason_codes": reason_codes,
        "graph_findings": answer.get("graph_findings"),
        "recommended_action": {"action": final, "rationale": answer.get("action_rationale"),
                               "llm_action": action, "policy_action": policy["policy_action"],
                               "score": policy["score"], "hard_rules_fired": policy["hard_rules_fired"],
                               "overridden_by_policy": overridden},
        "cited_sources": cited,
        "retrieved_chunks": [{"chunk_id": c["chunk_id"], "score": c["score"], "matched_query": c["matched_query"]}
                             for c in chunks],
        "warnings": warnings,
        "meta": {"stores": {"transaction": settings.STORE, "graph": "neo4j", "policy": f"qdrant:{settings.COLLECTION}"},
                 "llm": f"{settings.LLM_PROVIDER}:{settings.LLM_MODEL}", "embedding_model": settings.EMBED_MODEL,
                 "usage": usage,
                 "latency_ms": {"transaction": round((t1 - t0) * 1000), "graph": round((t2 - t1) * 1000),
                                "retrieval": round((t3 - t2) * 1000), "llm": round((t4 - t3) * 1000),
                                "total": round((t4 - t0) * 1000)},
                 "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
    }
    if req.include_context:
        out["context"] = context
    return out
