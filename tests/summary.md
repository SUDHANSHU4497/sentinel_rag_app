# Test run: 10 validation transactions

LLM `euron:gpt-4.1-mini`, transactions from `mongodb`, graph from Neo4j, policy from Qdrant `sentinel_docs`.

- Fraud sent to REVIEW or BLOCK: 2 of 5
- Genuine sent to REVIEW or BLOCK: 0 of 5
- Responses with at least one citation: 10 of 10
- Median latency: 7256 ms

| Transaction | True label | Score | Risk level | Action (LLM / policy) | Reason codes | Cited chunks |
|---|---|---:|---|---|---|---|
| [TX_0000933774](responses/TX_0000933774.json) | fraud | 0.031 | CRITICAL | **BLOCK** (BLOCK / BLOCK) | R02_GEO_MISMATCH, R03_ODD_HOUR, R08_HIGH_RISK_MCC | DOC_regulatory_exercises_0000342::0<br>DOC_regulatory_exercises_0000388::0<br>DOC_regulatory_exercises_0000527::0<br>DOC_regulatory_exercises_0000799::2 |
| [TX_0000917129](responses/TX_0000917129.json) | fraud | 0.062 | LOW | **ALLOW** (ALLOW / ALLOW) | R02_GEO_MISMATCH, R03_ODD_HOUR, R08_HIGH_RISK_MCC | DOC_regulatory_exercises_0000342::0<br>DOC_regulatory_exercises_0000388::0<br>DOC_regulatory_exercises_0000799::2 |
| [TX_0000817832](responses/TX_0000817832.json) | fraud | 0.133 | LOW | **ALLOW** (ALLOW / ALLOW) | R02_GEO_MISMATCH, R03_ODD_HOUR, R04_FAILED_ATTEMPTS, R08_HIGH_RISK_MCC | DOC_regulatory_exercises_0000342::0<br>DOC_regulatory_exercises_0000388::0<br>DOC_regulatory_exercises_0000703::0<br>DOC_regulatory_exercises_0000799::2 |
| [TX_0000874973](responses/TX_0000874973.json) | fraud | 0.604 | HIGH | **REVIEW** (REVIEW / REVIEW) | R02_GEO_MISMATCH, R03_ODD_HOUR, R04_FAILED_ATTEMPTS, R07_VELOCITY, R08_HIGH_RISK_MCC | DOC_regulatory_exercises_0000342::0<br>DOC_regulatory_exercises_0000388::0<br>DOC_regulatory_exercises_0000703::0<br>DOC_regulatory_exercises_0000786::0<br>DOC_regulatory_exercises_0000799::2 |
| [TX_0000841094](responses/TX_0000841094.json) | fraud | 0.104 | LOW | **ALLOW** (ALLOW / ALLOW) | R02_GEO_MISMATCH, R03_ODD_HOUR, R05_AMOUNT_SPIKE, R08_HIGH_RISK_MCC | DOC_regulatory_exercises_0000799::2<br>DOC_regulatory_exercises_0000831::0<br>DOC_regulatory_exercises_0000342::0<br>DOC_regulatory_exercises_0000388::0<br>DOC_regulatory_exercises_0000044::0 |
| [TX_0000922383](responses/TX_0000922383.json) | genuine | 0.020 | LOW | **ALLOW** (ALLOW / ALLOW) | R02_GEO_MISMATCH, R08_HIGH_RISK_MCC | DOC_regulatory_exercises_0000799::2<br>DOC_regulatory_exercises_0000342::0 |
| [TX_0000837350](responses/TX_0000837350.json) | genuine | 0.011 | LOW | **ALLOW** (ALLOW / ALLOW) | R02_GEO_MISMATCH | DOC_regulatory_exercises_0000342::0<br>DOC_regulatory_exercises_0000799::2 |
| [TX_0000842171](responses/TX_0000842171.json) | genuine | 0.013 | LOW | **ALLOW** (ALLOW / ALLOW) | R02_GEO_MISMATCH | DOC_regulatory_exercises_0000799::2<br>DOC_regulatory_exercises_0000342::0 |
| [TX_0000909126](responses/TX_0000909126.json) | genuine | 0.017 | LOW | **ALLOW** (ALLOW / ALLOW) | R02_GEO_MISMATCH | DOC_regulatory_exercises_0000342::0<br>DOC_regulatory_exercises_0000799::2 |
| [TX_0000865089](responses/TX_0000865089.json) | genuine | 0.132 | LOW | **ALLOW** (ALLOW / ALLOW) | R02_GEO_MISMATCH, R03_ODD_HOUR, R04_FAILED_ATTEMPTS, R08_HIGH_RISK_MCC | DOC_regulatory_exercises_0000342::0<br>DOC_regulatory_exercises_0000388::0<br>DOC_regulatory_exercises_0000703::0<br>DOC_regulatory_exercises_0000799::2 |
