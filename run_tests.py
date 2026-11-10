"""Call POST /explain for 10 validation transactions (5 fraud, 5 genuine) and save the responses.

The 10 are drawn at random (seed 42) from the validation split: 5 with fraud_label = 1 and 5 with
fraud_label = 0. The label is read here only to pick and score the cases; the API never sees it.

Start the API first (uvicorn api:app --port 8000), then:  python run_tests.py
Writes tests/responses/<transaction_id>.json and tests/summary.md / tests/summary.csv
"""
import json
import os

import pandas as pd
import requests

import settings

SEED = 42
OUT = os.path.join("tests", "responses")


def pick_cases():
    if settings.STORE == "mongodb":
        from pymongo import MongoClient
        db = MongoClient(settings.MONGODB_URI)[settings.MONGODB_DB]
        labels = pd.DataFrame(db.labels.find({"split": "validation"}, {"fraud_label": 1, "label_source": 1}))
        labels = labels.rename(columns={"_id": "transaction_id"})
    else:
        from tables import read_table
        labels = read_table(settings.DATA_PATH, "labels", ["validation"])
    fraud = labels[labels["fraud_label"] == 1].sample(5, random_state=SEED)
    genuine = labels[labels["fraud_label"] == 0].sample(5, random_state=SEED)
    return pd.concat([fraud, genuine])[["transaction_id", "fraud_label", "label_source"]]


def main():
    os.makedirs(OUT, exist_ok=True)
    cases = pick_cases()
    rows = []
    for c in cases.itertuples():
        r = requests.post(f"{settings.API_URL}/explain", json={"transaction_id": c.transaction_id}, timeout=300)
        r.raise_for_status()
        resp = r.json()
        with open(os.path.join(OUT, f"{c.transaction_id}.json"), "w", encoding="utf-8") as f:
            json.dump(resp, f, indent=2, ensure_ascii=False)
        act = resp["recommended_action"]
        rows.append({"transaction_id": c.transaction_id, "true_label": "fraud" if c.fraud_label else "genuine",
                     "label_source": c.label_source, "score": act["score"], "risk_level": resp["risk_level"],
                     "action": act["action"], "llm_action": act["llm_action"], "policy_action": act["policy_action"],
                     "reason_codes": ", ".join(x["code"] for x in resp["reason_codes"]),
                     "cited": ", ".join(x["chunk_id"] for x in resp["cited_sources"]),
                     "warnings": len(resp["warnings"]), "latency_ms": resp["meta"]["latency_ms"]["total"]})
        print(f"{c.transaction_id} {rows[-1]['true_label']:8} -> {act['action']:6} ({resp['risk_level']})")
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join("tests", "summary.csv"), index=False)

    flagged = df["action"].isin(["REVIEW", "BLOCK"])
    is_fraud = df["true_label"] == "fraud"
    lines = ["# Test run: 10 validation transactions", "",
             f"LLM `{settings.LLM_PROVIDER}:{settings.LLM_MODEL}`, transactions from `{settings.STORE}`, "
             f"graph from Neo4j, policy from Qdrant `{settings.COLLECTION}`.", "",
             f"- Fraud sent to REVIEW or BLOCK: {int((flagged & is_fraud).sum())} of {int(is_fraud.sum())}",
             f"- Genuine sent to REVIEW or BLOCK: {int((flagged & ~is_fraud).sum())} of {int((~is_fraud).sum())}",
             f"- Responses with at least one citation: {int((df['cited'] != '').sum())} of {len(df)}",
             f"- Median latency: {int(df['latency_ms'].median())} ms", "",
             "| Transaction | True label | Score | Risk level | Action (LLM / policy) | Reason codes | Cited chunks |",
             "|---|---|---:|---|---|---|---|"]
    for r in df.itertuples():
        lines.append(f"| [{r.transaction_id}](responses/{r.transaction_id}.json) | {r.true_label} | {r.score:.3f} | "
                     f"{r.risk_level} | **{r.action}** ({r.llm_action} / {r.policy_action}) | {r.reason_codes} | "
                     f"{r.cited.replace(', ', '<br>')} |")
    with open(os.path.join("tests", "summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines[3:7]))


if __name__ == "__main__":
    main()
