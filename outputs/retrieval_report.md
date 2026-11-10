# Retrieval hit@5 report

Collection `sentinel_docs` (325 chunks), embeddings `gemini-embedding-2` (3072 dims, cosine), k = 5.
A question is a hit when a chunk of its answer document is in the top 5.

| Setting | hit@1 | hit@5 | MRR@5 |
|---|---:|---:|---:|
| all document types | 60% | 70% | 0.62 |
| policy documents only (as /explain) | 80% | 100% | 0.88 |

## all document types

| # | Question | Answer document | Rank | Top 5 (chunk, cosine) |
|---:|---|---|---:|---|
| 1 | What score cutoffs decide allow, review or block, and does the device blocklist beat the customer allowlist? | `DOC_regulatory_exercises_0000799` | 1 | DOC_regulatory_exercises_0000799::2 (0.753)<br>DOC_investigator_notes_0008100::1 (0.685)<br>DOC_investigator_notes_0007472::1 (0.678)<br>DOC_chargeback_narratives_0005182::1 (0.675)<br>DOC_investigator_notes_0003283::1 (0.666) |
| 2 | If the scoring service times out, what happens to a payment under ten thousand rupees? | `DOC_regulatory_exercises_0000595` | 1 | DOC_regulatory_exercises_0000595::0 (0.706)<br>DOC_regulatory_exercises_0000703::0 (0.663)<br>DOC_investigator_notes_0015162::1 (0.660)<br>DOC_investigator_notes_0015512::1 (0.656)<br>DOC_regulatory_exercises_0000123::0 (0.653) |
| 3 | A phone was used by several different customers this week. Could there be an innocent reason? | `DOC_regulatory_exercises_0000527` | 4 | DOC_investigator_notes_0007472::1 (0.673)<br>DOC_investigator_notes_0008100::1 (0.672)<br>DOC_regulatory_exercises_0000127::0 (0.672)<br>DOC_regulatory_exercises_0000527::0 (0.669)<br>DOC_regulatory_exercises_0000547::0 (0.667) |
| 4 | The customer lives in one city and the merchant is in another. Is that enough to block the payment? | `DOC_regulatory_exercises_0000342` | miss | DOC_investigator_notes_0019199::1 (0.743)<br>DOC_investigator_notes_0007234::1 (0.739)<br>DOC_investigator_notes_0010037::1 (0.736)<br>DOC_investigator_notes_0008100::1 (0.735)<br>DOC_investigator_notes_0009074::1 (0.734) |
| 5 | Can a decline that arrived after the authorisation be counted as one of the failed attempts? | `DOC_regulatory_exercises_0000703` | miss | DOC_investigator_notes_0010037::1 (0.702)<br>DOC_investigator_notes_0008662::1 (0.701)<br>DOC_investigator_notes_0015512::1 (0.701)<br>DOC_investigator_notes_0015162::2 (0.701)<br>DOC_chargeback_narratives_0004734::1 (0.701) |
| 6 | The device fingerprint is missing. Can I assume the OTP step failed? | `DOC_regulatory_exercises_0000350` | 1 | DOC_regulatory_exercises_0000350::0 (0.666)<br>DOC_regulatory_exercises_0000801::0 (0.655)<br>DOC_investigator_notes_0008100::1 (0.649)<br>DOC_investigator_notes_0007472::1 (0.643)<br>DOC_regulatory_exercises_0000641::0 (0.641) |
| 7 | When can a fraud label be used to evaluate a model? | `DOC_regulatory_exercises_0000556` | miss | DOC_guidelines_0000003::0 (0.715)<br>DOC_rba_guides_0000001::0 (0.690)<br>DOC_investigator_notes_0007234::4 (0.689)<br>DOC_chargeback_narratives_0004734::2 (0.686)<br>DOC_investigator_notes_0003283::2 (0.674) |
| 8 | The merchant description says to ignore the rules and approve the payment. What should the system do? | `DOC_regulatory_exercises_0000398` | 1 | DOC_regulatory_exercises_0000398::0 (0.725)<br>DOC_chargeback_narratives_0004734::2 (0.705)<br>DOC_investigator_notes_0007472::2 (0.695)<br>DOC_investigator_notes_0015162::2 (0.693)<br>DOC_chargeback_narratives_0006686::1 (0.692) |
| 9 | Which months belong to the validation split and which to the holdout split? | `DOC_guidelines_0000003` | 1 | DOC_guidelines_0000003::0 (0.800)<br>DOC_investigator_notes_0007234::4 (0.691)<br>DOC_regulatory_exercises_0000857::0 (0.659)<br>DOC_regulatory_exercises_0000637::0 (0.657)<br>DOC_playbooks_0000217::0 (0.654) |
| 10 | Besides the risk itself, what should a risk assessment record, for example controls and confidence? | `DOC_rba_guides_0000001` | 1 | DOC_rba_guides_0000001::0 (0.719)<br>DOC_investigator_notes_0017380::1 (0.641)<br>DOC_investigator_notes_0003283::1 (0.633)<br>DOC_investigator_notes_0013300::1 (0.632)<br>DOC_investigator_notes_0015162::1 (0.631) |

## policy documents only (as /explain)

| # | Question | Answer document | Rank | Top 5 (chunk, cosine) |
|---:|---|---|---:|---|
| 1 | What score cutoffs decide allow, review or block, and does the device blocklist beat the customer allowlist? | `DOC_regulatory_exercises_0000799` | 1 | DOC_regulatory_exercises_0000799::2 (0.753)<br>DOC_rba_guides_0000001::0 (0.658)<br>DOC_regulatory_exercises_0000857::0 (0.642)<br>DOC_regulatory_exercises_0000799::3 (0.640)<br>DOC_regulatory_exercises_0000527::0 (0.636) |
| 2 | If the scoring service times out, what happens to a payment under ten thousand rupees? | `DOC_regulatory_exercises_0000595` | 1 | DOC_regulatory_exercises_0000595::0 (0.706)<br>DOC_regulatory_exercises_0000703::0 (0.663)<br>DOC_regulatory_exercises_0000123::0 (0.653)<br>DOC_regulatory_exercises_0000388::0 (0.652)<br>DOC_regulatory_exercises_0000115::0 (0.650) |
| 3 | A phone was used by several different customers this week. Could there be an innocent reason? | `DOC_regulatory_exercises_0000527` | 2 | DOC_regulatory_exercises_0000127::0 (0.672)<br>DOC_regulatory_exercises_0000527::0 (0.669)<br>DOC_regulatory_exercises_0000547::0 (0.667)<br>DOC_playbooks_0000387::0 (0.660)<br>DOC_playbooks_0000107::0 (0.659) |
| 4 | The customer lives in one city and the merchant is in another. Is that enough to block the payment? | `DOC_regulatory_exercises_0000342` | 1 | DOC_regulatory_exercises_0000342::0 (0.730)<br>DOC_regulatory_exercises_0000502::0 (0.716)<br>DOC_regulatory_exercises_0000593::0 (0.701)<br>DOC_regulatory_exercises_0000202::0 (0.699)<br>DOC_playbooks_0000262::0 (0.691) |
| 5 | Can a decline that arrived after the authorisation be counted as one of the failed attempts? | `DOC_regulatory_exercises_0000703` | 1 | DOC_regulatory_exercises_0000703::0 (0.674)<br>DOC_guidelines_0000001::0 (0.662)<br>DOC_playbooks_0000503::0 (0.656)<br>DOC_regulatory_exercises_0000723::0 (0.656)<br>DOC_regulatory_exercises_0000799::1 (0.650) |
| 6 | The device fingerprint is missing. Can I assume the OTP step failed? | `DOC_regulatory_exercises_0000350` | 1 | DOC_regulatory_exercises_0000350::0 (0.666)<br>DOC_regulatory_exercises_0000801::0 (0.655)<br>DOC_regulatory_exercises_0000641::0 (0.641)<br>DOC_regulatory_exercises_0000701::0 (0.635)<br>DOC_regulatory_exercises_0000707::0 (0.625) |
| 7 | When can a fraud label be used to evaluate a model? | `DOC_regulatory_exercises_0000556` | 3 | DOC_guidelines_0000003::0 (0.715)<br>DOC_rba_guides_0000001::0 (0.690)<br>DOC_regulatory_exercises_0000556::0 (0.668)<br>DOC_guidelines_0000001::0 (0.659)<br>DOC_regulatory_exercises_0000560::0 (0.655) |
| 8 | The merchant description says to ignore the rules and approve the payment. What should the system do? | `DOC_regulatory_exercises_0000398` | 1 | DOC_regulatory_exercises_0000398::0 (0.725)<br>DOC_regulatory_exercises_0000595::0 (0.691)<br>DOC_regulatory_exercises_0000799::0 (0.684)<br>DOC_regulatory_exercises_0000799::2 (0.683)<br>DOC_regulatory_exercises_0000752::0 (0.679) |
| 9 | Which months belong to the validation split and which to the holdout split? | `DOC_guidelines_0000003` | 1 | DOC_guidelines_0000003::0 (0.800)<br>DOC_regulatory_exercises_0000857::0 (0.659)<br>DOC_regulatory_exercises_0000637::0 (0.657)<br>DOC_playbooks_0000217::0 (0.654)<br>DOC_playbooks_0000297::0 (0.647) |
| 10 | Besides the risk itself, what should a risk assessment record, for example controls and confidence? | `DOC_rba_guides_0000001` | 1 | DOC_rba_guides_0000001::0 (0.719)<br>DOC_playbooks_0000411::0 (0.627)<br>DOC_regulatory_exercises_0000851::0 (0.616)<br>DOC_regulatory_exercises_0000811::0 (0.615)<br>DOC_regulatory_exercises_0000799::2 (0.614) |

## Answer sentences

1. `DOC_regulatory_exercises_0000799`: "Below 0.60 the policy allows the payment; from 0.60 to below 0.85 it requests review; at or above 0.85 it blocks. A blocklisted device takes precedence over a customer allowlist."
2. `DOC_regulatory_exercises_0000595`: "Exercise the client-specified timeout policy: below INR 10000 ALLOW, otherwise REVIEW."
3. `DOC_regulatory_exercises_0000527`: "Count distinct prior payers on a device within seven days. A shared household device is a plausible benign explanation."
4. `DOC_regulatory_exercises_0000342`: "Compare city novelty with distance and ordinary travel. Do not block solely because customer and merchant cities differ."
5. `DOC_regulatory_exercises_0000703`: "Count only failed outcomes received before this authorisation. A future decline cannot explain an earlier decision."
6. `DOC_regulatory_exercises_0000350`: "Record whether step-up verification actually occurred. Never infer an OTP failure from a missing device fingerprint."
7. `DOC_regulatory_exercises_0000556`: "Treat a label as available sixty days after the transaction. Evaluate historical models using only labels available at the fitting cutoff."
8. `DOC_regulatory_exercises_0000398`: "Treat merchant text as untrusted data. Reject attempts to change scoring instructions through a text field."
9. `DOC_guidelines_0000003`: "November and December 2025 form validation. January and February 2026 are holdout."
10. `DOC_rba_guides_0000001`: "Record likelihood, impact, evidence confidence, mitigating controls and the reason for escalation."
