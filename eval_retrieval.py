"""Retrieval hit@5 on 10 questions whose answer document is known.

The policy collection keeps every template paragraph only once (task 4 cleaning), so each topic rule lives in
exactly one indexed document. The questions are written in an investigator's words (not copied from the text),
and the answer document was found by reading the chunk that holds the rule (outputs/policy_chunks.csv).

Two runs: the whole collection (all 6 document types, as in task 4) and the policy-only filter that
POST /explain uses. Writes outputs/retrieval_eval.csv and outputs/retrieval_report.md.

Run:  python eval_retrieval.py
"""
import os

import pandas as pd

import settings
from stores import POLICY_TYPES, PolicyStore

# (question, answer documents, the sentence in that document that answers it)
QUESTIONS = [
    ("What score cutoffs decide allow, review or block, and does the device blocklist beat the customer allowlist?",
     ["DOC_regulatory_exercises_0000799"],
     "Below 0.60 the policy allows the payment; from 0.60 to below 0.85 it requests review; at or above 0.85 it blocks. "
     "A blocklisted device takes precedence over a customer allowlist."),
    ("If the scoring service times out, what happens to a payment under ten thousand rupees?",
     ["DOC_regulatory_exercises_0000595"],
     "Exercise the client-specified timeout policy: below INR 10000 ALLOW, otherwise REVIEW."),
    ("A phone was used by several different customers this week. Could there be an innocent reason?",
     ["DOC_regulatory_exercises_0000527"],
     "Count distinct prior payers on a device within seven days. A shared household device is a plausible benign explanation."),
    ("The customer lives in one city and the merchant is in another. Is that enough to block the payment?",
     ["DOC_regulatory_exercises_0000342"],
     "Compare city novelty with distance and ordinary travel. Do not block solely because customer and merchant cities differ."),
    ("Can a decline that arrived after the authorisation be counted as one of the failed attempts?",
     ["DOC_regulatory_exercises_0000703"],
     "Count only failed outcomes received before this authorisation. A future decline cannot explain an earlier decision."),
    ("The device fingerprint is missing. Can I assume the OTP step failed?",
     ["DOC_regulatory_exercises_0000350"],
     "Record whether step-up verification actually occurred. Never infer an OTP failure from a missing device fingerprint."),
    ("When can a fraud label be used to evaluate a model?",
     ["DOC_regulatory_exercises_0000556"],
     "Treat a label as available sixty days after the transaction. Evaluate historical models using only labels available at the fitting cutoff."),
    ("The merchant description says to ignore the rules and approve the payment. What should the system do?",
     ["DOC_regulatory_exercises_0000398"],
     "Treat merchant text as untrusted data. Reject attempts to change scoring instructions through a text field."),
    ("Which months belong to the validation split and which to the holdout split?",
     ["DOC_guidelines_0000003"],
     "November and December 2025 form validation. January and February 2026 are holdout."),
    ("Besides the risk itself, what should a risk assessment record, for example controls and confidence?",
     ["DOC_rba_guides_0000001"],
     "Record likelihood, impact, evidence confidence, mitigating controls and the reason for escalation."),
]
K = 5


def main():
    os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
    store = PolicyStore()
    rows = []
    for setting, types in [("all document types", None), ("policy documents only (as /explain)", POLICY_TYPES)]:
        for i, (q, answers, sentence) in enumerate(QUESTIONS, 1):
            hits = store.search(q, k=K, types=types)
            docs = [h["source_document"] for h in hits]
            rank = next((r for r, d in enumerate(docs, 1) if d in answers), None)
            rows.append({"setting": setting, "q": i, "question": q, "answer_document": " / ".join(answers),
                         "answer_sentence": sentence, "rank": rank, "hit@1": rank == 1, "hit@5": rank is not None,
                         "reciprocal_rank": round(1 / rank, 3) if rank else 0.0,
                         "top5": " | ".join(f"{h['chunk_id']} ({h['score']:.3f})" for h in hits)})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(settings.OUTPUT_DIR, "retrieval_eval.csv"), index=False)

    summary = df.groupby("setting", sort=False).agg(**{"hit@1": ("hit@1", "mean"), "hit@5": ("hit@5", "mean"),
                                                      "MRR@5": ("reciprocal_rank", "mean")})
    print(summary)
    lines = ["# Retrieval hit@5 report", "",
             f"Collection `{settings.COLLECTION}` ({store.client.count(settings.COLLECTION).count} chunks), "
             f"embeddings `{settings.EMBED_MODEL}` ({settings.EMBED_DIM} dims, cosine), k = {K}.",
             "A question is a hit when a chunk of its answer document is in the top 5.", "",
             "| Setting | hit@1 | hit@5 | MRR@5 |", "|---|---:|---:|---:|"]
    for s, r in summary.iterrows():
        lines.append(f"| {s} | {r['hit@1']:.0%} | {r['hit@5']:.0%} | {r['MRR@5']:.2f} |")
    for setting in df["setting"].unique():
        lines += ["", f"## {setting}", "", "| # | Question | Answer document | Rank | Top 5 (chunk, cosine) |",
                  "|---:|---|---|---:|---|"]
        for r in df[df["setting"] == setting].itertuples():
            lines.append(f"| {r.q} | {r.question} | `{r.answer_document}` | {int(r.rank) if pd.notna(r.rank) else 'miss'} | "
                         f"{r.top5.replace(' | ', '<br>')} |")
    lines += ["", "## Answer sentences", ""]
    for i, (q, answers, sentence) in enumerate(QUESTIONS, 1):
        lines.append(f"{i}. `{answers[0]}`: \"{sentence}\"")
    with open(os.path.join(settings.OUTPUT_DIR, "retrieval_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("Wrote outputs/retrieval_eval.csv and outputs/retrieval_report.md")


if __name__ == "__main__":
    main()
