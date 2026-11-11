# SENTINEL fraud-explain API

A small FastAPI service for a fraud investigator: give it a transaction id, and it explains the risk and cites the policy.

```
POST /explain {"transaction_id": "TX_0000874973"}
```
returns JSON with the **risk summary**, the **reason codes that fired**, a **recommended action** and the **cited sources** (document and chunk).

It reuses the earlier tasks: the MongoDB documents from task 1, the Neo4j graph from task 2, the features and reason codes from task 3 and the Qdrant collection with Gemini Embedding 2 from task 4.

**Results in one line:** all 10 test calls returned valid JSON with citations and no hallucinated codes or chunks; retrieval **hit@5 is 100%** on 10 questions with a known answer document (70% when the case notes are searched too).

## Where each requirement is

| # | Requirement | Code | Evidence in this repo |
|---|---|---|---|
| 1 | FastAPI service with `POST /explain {transaction_id}` | [`api.py`](api.py) | [Swagger call](screenshots/step3_swagger_response.png), [health check](screenshots/step1_health.png) |
| 2 | Reads transaction + features (MongoDB or Supabase), device and customer neighbourhood (Neo4j), policy chunks (Qdrant + Gemini Embedding 2) | [`stores.py`](stores.py), [`embeddings.py`](embeddings.py), [`settings.py`](settings.py), loaders [`load_mongo.py`](load_mongo.py), [`load_neo4j.py`](load_neo4j.py), [`build_policy_index.py`](build_policy_index.py) | [Qdrant collection](screenshots/step7_qdrant_collection.png), `/health` lists all three stores |
| 3 | LLM returns JSON: risk summary, reason codes, recommended action, cited sources (document and chunk) | [`llm.py`](llm.py) + guardrails in [`api.py`](api.py) | [a saved response](screenshots/step5_saved_response.png) |
| 4 | 10 test transactions (5 fraud, 5 genuine, validation split), responses saved | [`run_tests.py`](run_tests.py) | [`tests/responses/`](tests/responses), [`tests/summary.md`](tests/summary.md), [screenshot](screenshots/step4_test_summary.png) |
| 5 | 10 questions with a known answer document, retrieval hit@5 | [`eval_retrieval.py`](eval_retrieval.py) | [`outputs/retrieval_report.md`](outputs/retrieval_report.md), [`outputs/retrieval_eval.csv`](outputs/retrieval_eval.csv), [screenshot](screenshots/step6_retrieval_hit_at_5.png) |
| 6 | One-page architecture diagram: which database stores what, and why | [`architecture.svg`](architecture.svg) | [`architecture.png`](architecture.png), shown below |
| | Setup and safe configuration | [`requirements.txt`](requirements.txt), [`.env.example`](.env.example), [`docker-compose.yml`](docker-compose.yml), [`.gitignore`](.gitignore) | [Setup](#setup) below; no key is in the code or outputs |
| | Everything in one run, with outputs | [`sentinel_rag_app.ipynb`](sentinel_rag_app.ipynb) | health check, a live `/explain` call, a 404, the 10 saved responses, hit@5 rerun, diagram |

## Files

| File | What it is |
|---|---|
| `sentinel_rag_app.ipynb` | The notebook: runs the API in-process, one live call, the saved tests and the hit@5 eval, with outputs |
| `api.py` | The FastAPI service: `POST /explain`, `GET /health` |
| `stores.py` | The three data sources: MongoDB or Supabase, Neo4j, Qdrant |
| `llm.py` | The prompt and the LLM call (Euron EURI gateway or Google Gemini API), JSON out |
| `embeddings.py` | Gemini Embedding 2 (3072 dimensions), same as task 4 |
| `load_mongo.py` | Loads transactions + features + customers + policy tables into MongoDB |
| `load_neo4j.py` | Loads the Customer / Device / Merchant graph into Neo4j (task 2 model) |
| `build_policy_index.py` | Builds the Qdrant collection exactly as in task 4 (skip it if task 4's collection exists) |
| `run_tests.py` | Calls the API for 5 fraud + 5 genuine validation transactions and saves the answers |
| `eval_retrieval.py` | 10 questions with a known answer document, reports hit@1, hit@5 and MRR |
| `tests/responses/*.json` | The 10 saved API responses |
| `tests/summary.md` | One line per test transaction |
| `outputs/retrieval_report.md` | The hit@5 report (and `retrieval_eval.csv`) |
| `outputs/policy_chunks.csv` | Every chunk in the Qdrant collection, without vectors |
| `settings.py`, `tables.py` | Settings from `.env`; reading the SENTINEL tables from the folder or the zip |
| `architecture.png`, `architecture.svg` | The one-page architecture diagram |
| `screenshots/` | Output of each step from a real run (shown below) |
| `docker-compose.yml` | MongoDB, Neo4j and Qdrant on your laptop (instead of Atlas, Aura and Qdrant Cloud) |
| `requirements.txt`, `.env.example`, `.gitignore` | Packages, settings template, keeps `.env` out of git |

---

## Architecture

![Architecture](architecture.png)

The source is `architecture.svg` (edit it in any text editor or Inkscape and re-export).

### Which database stores what, and why

| Store | What it holds here | Why this database |
|---|---|---|
| **MongoDB** (task 1), or **Supabase** | `transactions`: one document per payment with merchant, device, the **feature snapshot** (reason codes included) and the simulated score **embedded**; `customers` with their devices embedded; `hard_rules`, `list_entries`, `threshold_sets`; `labels` in a separate collection | The API needs everything about one payment in **one key lookup** (`_id = transaction_id`, about 2 ms). The feature snapshot is written once at authorisation and always read with the payment, so embedding it saves a join. Supabase holds the same tables in Postgres and is the source of truth for the batch pipeline; `STORE=supabase` reads them through the REST API with the same output. |
| **Neo4j** (task 2) | `(:Customer)-[:USED_DEVICE]->(:Device)`, `(:Customer)-[:PAID {amount, time, fraud_label, label_available_at, device_id}]->(:Merchant)` for Aug to Dec 2025 (364,070 payments) | The questions are about **relationships**: who else used this device in the last 7 or 90 days, which of them has known fraud, which customers are 2 hops away through a shared device. In a table these are self-joins over millions of rows; in a graph they are short path patterns. |
| **Qdrant** (task 4) | 325 chunks of 223 cleaned train-split documents (RBI/NPCI exercises, playbooks, guides, case notes), each a 3072-dim Gemini Embedding 2 vector with payload (document, type, topic, chunk number, text) | Policy text has to be found **by meaning** ("is a city mismatch enough to block?"), not by keyword. Qdrant does the nearest-neighbour search and the payload filter (`document_type` in policy types) in one call. |
| **LLM** (no storage) | nothing stored | Turns the facts into a short explanation for a person, and maps each signal to the policy chunk behind it. It never decides alone: the guardrails below keep the facts and the action tied to the data. |

**What is never sent to the LLM:** the fraud label. Labels only exist 60 days after a payment, so the API never reads the `labels` collection. In the graph, a fraud label only counts if `label_available_at` is before the payment being explained.

---

## Setup

1. `pip install -r requirements.txt`
2. Start the three databases. Either on your laptop:
   ```
   docker compose up -d
   ```
   or use your cloud ones (Atlas from task 1, Aura from task 2, Qdrant Cloud from task 4).
3. Copy `.env.example` to `.env` and fill in `EURI_API_KEY` (embeddings and LLM), plus the cloud URLs and keys if you use them. `DATA_PATH` points to the SENTINEL tables folder.
4. Load the data (each script is safe to run twice: MongoDB uses upserts, Neo4j uses MERGE, the Qdrant collection is rebuilt):
   ```
   python load_mongo.py            # about 1 minute, 144,803 validation payments
   python load_neo4j.py            # about 1 minute, 364,070 payments (Aug to Dec 2025)
   python build_policy_index.py    # about 1 minute, about 32,000 embedding tokens (skip if task 4 already built it)
   ```
5. Start the API and open the Swagger page at http://127.0.0.1:8000/docs:
   ```
   uvicorn api:app --port 8000
   ```
6. In a second terminal:
   ```
   python run_tests.py             # the 10 test transactions -> tests/
   python eval_retrieval.py        # hit@5 -> outputs/retrieval_report.md
   ```
7. Or, instead of 5 and 6, open `sentinel_rag_app.ipynb` and click **Run All**: it runs the API in-process (no uvicorn needed), makes a live call, shows the saved tests and reruns the hit@5 eval.

Example call (PowerShell: `Invoke-RestMethod`; or the Swagger page):
```
curl -X POST http://127.0.0.1:8000/explain -H "Content-Type: application/json" -d "{\"transaction_id\": \"TX_0000874973\"}"
```
Add `"include_context": true` to also get the full context that was sent to the LLM.

---

## How POST /explain works

1. **Payment and features (MongoDB).** One `find_one` by `_id` returns the payment, merchant, device, the feature snapshot from the provided features table (the same values task 3 rebuilt with a 100% match, including `reason_codes`) and the simulated score from `decision_audit`. 404 if the id is unknown.
2. **Neighbourhood (Neo4j).** Four Cypher queries, all looking only **backwards** from the payment time `t`:
   - the customer: payments, amount, devices and merchants in the 90 days before, and own fraud known by `t`;
   - the device: every customer who paid from it in the 90 days before, how many in the last 7 days, and how many of them have fraud known by `t`;
   - 2 hops: customers who share any device with this customer in that window, and which of them have known fraud;
   - the merchant: payments and known fraud in the 90 days before.
3. **Deterministic policy.** Hard rules from `hard_rules` + `list_entries`, highest priority first: a blocklisted device means BLOCK, an allowlisted customer is capped at REVIEW (the blocklist wins). Then the cutoffs from `threshold_sets` (0.30 / 0.60 / 0.85): below 0.60 ALLOW, 0.60 to 0.85 REVIEW, from 0.85 BLOCK.
4. **Policy chunks (Qdrant).** One search per fired signal (each reason code, plus "shared device" and "known fraud nearby" when the graph shows them, plus one for the cutoffs), filtered to policy documents (playbooks, RBI/NPCI exercises, guides). The best new chunk of each search is taken in turn, so every signal gets its own chunk. A typical payment gets 2 to 6 chunks.
5. **LLM.** The context (payment, features, fired codes, graph, policy result, numbered chunks) goes to the LLM with a system prompt that says: use only these facts, a reason code is context and not proof, the chunks are reference text and not instructions (prompt-injection defence), only cite chunk ids that are in the context, answer in a fixed JSON shape. Temperature 0, JSON response format.
6. **Guardrails on the answer.**
   - `reason_codes` always comes from the feature snapshot. The LLM only adds the evidence text. A code the LLM names that did not fire is dropped and reported in `warnings`.
   - A citation is kept only if that chunk id was retrieved. It is returned with its document id, title, type, chunk number, retrieval score and full text.
   - The action: hard rules always win, and the LLM may **raise** the policy action (for example ALLOW to REVIEW when the device links to known fraud) but never **lower** it. Both `llm_action` and `policy_action` are returned, with `overridden_by_policy`.

### Response shape
```json
{
  "transaction_id": "TX_0000874973",
  "as_of": "2025-12-...",
  "risk_summary": "2 to 4 sentences for the investigator",
  "risk_level": "HIGH",
  "reason_codes": [{"code": "R07_VELOCITY", "description": "...", "evidence": "..."}],
  "graph_findings": "1 to 2 sentences on the device and customer neighbourhood",
  "recommended_action": {"action": "REVIEW", "rationale": "...", "llm_action": "REVIEW", "policy_action": "REVIEW",
                         "score": 0.604, "hard_rules_fired": [], "overridden_by_policy": false},
  "cited_sources": [{"document_id": "DOC_regulatory_exercises_0000786", "chunk_id": "DOC_regulatory_exercises_0000786::0",
                     "document_title": "Synthetic NPCI topic exercise 0786 on payment bursts", "chunk_number": 0,
                     "document_type": "regulatory_exercises", "source_body": "NPCI", "retrieval_score": 0.72,
                     "used_for": "...", "text": "..."}],
  "retrieved_chunks": [{"chunk_id": "...", "score": 0.72, "matched_query": "..."}],
  "warnings": [],
  "meta": {"llm": "euron:gpt-4.1-mini", "usage": {"total_tokens": 3212}, "latency_ms": {"total": 7256}}
}
```

---

## Test: 10 validation transactions

`run_tests.py` draws 5 fraud and 5 genuine transactions at random (seed 42) from the **validation split** (Nov to Dec 2025). The label is used only to pick and score them. The full answers are in `tests/responses/`, one line each in [`tests/summary.md`](tests/summary.md).

| Transaction | True label | Score | Action | Reason codes | Notes |
|---|---|---:|---|---|---|
| TX_0000933774 | fraud | 0.031 | **BLOCK** | R02, R03, R08 | device is on the blocklist (`HR_BLOCKLIST_DEVICE`); 22 customers on the device, 3 with known fraud |
| TX_0000917129 | fraud | 0.062 | ALLOW | R02, R03, R08 | device used only by this customer, no known fraud nearby |
| TX_0000817832 | fraud | 0.133 | ALLOW | R02, R03, R04, R08 | |
| TX_0000874973 | fraud | 0.604 | **REVIEW** | R02, R03, R04, R07, R08 | score just above the 0.60 review cutoff |
| TX_0000841094 | fraud | 0.104 | ALLOW | R02, R03, R05, R08 | amount 8.8 x the 90-day average |
| TX_0000922383 | genuine | 0.020 | ALLOW | R02, R08 | |
| TX_0000837350 | genuine | 0.011 | ALLOW | R02 | |
| TX_0000842171 | genuine | 0.013 | ALLOW | R02 | |
| TX_0000909126 | genuine | 0.017 | ALLOW | R02 | |
| TX_0000865089 | genuine | 0.132 | ALLOW | R02, R03, R04, R08 | |

- **Explanations:** 10 of 10 valid JSON, every one with citations (2 to 5 chunks), 0 warnings (no code that did not fire, no chunk that was not retrieved, no override needed).
- **Catching fraud:** 2 of 5 fraud go to REVIEW or BLOCK, 0 of 5 genuine do. The API explains a decision, it does not replace the model: the misses all have a low simulated score (0.06 to 0.13, the dataset card says it is not calibrated) and nothing in the graph that links them to earlier fraud, so the policy says ALLOW and the LLM correctly does not invent a reason to escalate. The explanations still list the signals (night, distance, amount spike), so an investigator reading them sees why they could be worth a look.
- **Citations follow the signals:** night payments cite the night-activity exercise (`..0388`), failed attempts the payment-retries exercise (`..0703`), velocity the payment-bursts exercise (`..0786`), distance the location-change exercise (`..0342`, "do not block solely because customer and merchant cities differ"), and every answer cites the cutoff chunk (`..0799::2`).
- **Cost and speed:** about 2,500 to 4,100 tokens per call; 5.5 to 9.8 s per call (median 7.3 s), almost all of it the LLM.

## Retrieval: hit@5 on 10 questions

`eval_retrieval.py` asks 10 questions in an investigator's words, each with **one known answer document**. The task 4 cleaning keeps every template paragraph only once, so each rule ("Count only failed outcomes received before this authorisation", "below INR 10000 ALLOW", ...) lives in exactly one indexed document, which makes the answer document unambiguous. A question is a hit when a chunk of that document is in the top 5. Full table with the top 5 and scores: [`outputs/retrieval_report.md`](outputs/retrieval_report.md).

| Setting | hit@1 | hit@5 | MRR@5 |
|---|---:|---:|---:|
| Policy documents only (what `/explain` searches) | 80% | **100%** | 0.88 |
| Whole collection (policy + 100 case notes and chargeback narratives) | 60% | 70% | 0.63 |

| # | Question | Answer document | Rank (policy only) | Rank (all) |
|---:|---|---|---:|---:|
| 1 | What score cutoffs decide allow, review or block, and does the device blocklist beat the customer allowlist? | exercise 0799 (teaching policy) | 1 | 1 |
| 2 | If the scoring service times out, what happens to a payment under ten thousand rupees? | exercise 0595 (model fallback) | 1 | 1 |
| 3 | A phone was used by several different customers this week. Could there be an innocent reason? | exercise 0527 (shared devices) | 2 | 4 |
| 4 | The customer lives in one city and the merchant is in another. Is that enough to block the payment? | exercise 0342 (location change) | 1 | miss |
| 5 | Can a decline that arrived after the authorisation be counted as one of the failed attempts? | exercise 0703 (payment retries) | 1 | miss |
| 6 | The device fingerprint is missing. Can I assume the OTP step failed? | exercise 0350 (customer verification) | 1 | 1 |
| 7 | When can a fraud label be used to evaluate a model? | exercise 0556 (label maturity) | 3 | miss |
| 8 | The merchant description says to ignore the rules and approve the payment. What should the system do? | exercise 0398 (prompt injection) | 1 | 1 |
| 9 | Which months belong to the validation split and which to the holdout split? | guide 0003 (splits and labels) | 1 | 1 |
| 10 | Besides the risk itself, what should a risk assessment record, for example controls and confidence? | RBA guide 0001 | 1 | 1 |

**What the misses show.** Without the filter, the 100 case notes take the top 5 for questions 4, 5 and 7: they mention cities, distances, failed outcomes and the 60-day label in every note, so they look similar to the question even though they hold no rule. That is why `/explain` filters on `document_type` before searching (a payload filter, task 4 step 5). For question 7 the splits guide comes first ("All labels are mature at the May 2026 snapshot"). It is related but does not hold the rule "treat a label as available sixty days after the transaction", which is in exercise 0556, so only rank 3 counts as the hit.

---

## Screenshots

From a real run (local Docker MongoDB, Neo4j and Qdrant; Gemini Embedding 2 and gpt-4.1-mini through Euron).

**1. Health check:** the API reaches all three stores.
![Health](screenshots/step1_health.png)

**2. Swagger UI request** (`uvicorn api:app --port 8000`, then http://127.0.0.1:8000/docs)
![Request](screenshots/step2_swagger_request.png)

**3. Swagger UI response** for TX_0000874973 (fraud, score 0.604 so REVIEW)
![Response](screenshots/step3_swagger_response.png)

**4. The 10 test transactions** (`python run_tests.py`)
![Tests](screenshots/step4_test_summary.png)

**5. One saved response**: TX_0000933774, blocked by the device blocklist
![Saved response](screenshots/step5_saved_response.png)

**6. Retrieval hit@5** (`python eval_retrieval.py`)
![hit@5](screenshots/step6_retrieval_hit_at_5.png)

**7. The Qdrant collection** `sentinel_docs` with its payload (dashboard at http://localhost:6333/dashboard)
![Qdrant](screenshots/step7_qdrant_collection.png)

---

## Notes and limits

- **Synthetic data.** The RBI/NPCI exercises are teaching scenarios, not real circulars, and the score in `decision_audit` is simulated (`SYNTHETIC-HEURISTIC-NOT-A-MODEL`). The citations show which SENTINEL document a rule came from, not a regulatory obligation.
- **Where the saved run happened.** The responses and the hit@5 report come from a run with local Docker databases (MongoDB 7, Neo4j 5.26, Qdrant 1.12) loaded by the scripts above, with Gemini Embedding 2 and `gpt-4.1-mini` through the Euron EURI gateway. The Supabase reader (`STORE=supabase`) follows `sql/schema.sql` but was not run against a live Supabase project.
- **Graph window.** `load_neo4j.py` loads Aug to Dec 2025 so every validation payment has 90 days of history. A payment outside the window still gets an answer, with `"in_graph": false` in the neighbourhood.
- **Keys.** Only read from `.env`, never written to the code, the outputs or the responses. `.gitignore` keeps `.env` and the embedding cache out of git.
