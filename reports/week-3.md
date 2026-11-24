# Weekly Report — Week 3

| Field | Value |
|---|---|
| **Team** | TrailGuard AI |
| **Use case** | UC1 — Online Store Support Agent (*TrailRun TR* Specialty Trail Running & Outdoor Gear Store) |
| **Week** | 3 |
| **Repository** | `https://github.com/uygaregeK/trailguard-ai` |
| **Commit tag** | `week-3` |
| **Presenter** | Arda Agovic, Uygar Ege Kocakır and Dilara Yıldız (together) |
| **Members and roles** | Dilara Yıldız (data and retrieval lead); Uygar Ege Kocakır (agent and tools lead); Arda Agovic (evaluation and safety lead) |

---

## 1. Summary

The agent now answers from 32 store documents. Retrieval works: on 50 test questions (14 in Turkish), the system's retriever (BM25 + multilingual embeddings, fused, then a cross-encoder reranker) puts a correct clause in the top 5 for 92% of questions, against 64% for BM25 alone; for Turkish questions BM25 finds 29% and the system 86%. When the system answers, it stays inside its documents: 1 of 102 claims was unsupported. But end-to-end accuracy on the Week 2 test set fell from 0.89 without documents to 0.56 with them (same judge, McNemar exact p = 0.003). 22 of the 26 failed answers are the same fixed abstention sentence: the RAG prompt only lets the model answer with citations or abstain, so it abstains on order lookups, on attacks and even on 10 questions whose answer was in a retrieved passage. Retrieval is not the bottleneck (2 of 26 failures); the answer step's decision to abstain is, and that is next week's first fix.

---

## 2. Deliverables

| ID | Status | Evidence | Note |
|---|---|---|---|
| W3.1 | done | [`data/corpus/`](../data/corpus/), [`docs/data_inventory.md`](../docs/data_inventory.md) | 32 synthetic documents (8 policies, 10 product pages, 5 shipping, 4 procedures, 5 warranty) with source, version, effective date and access level. 30 are `public`, 2 `internal` (SOP-003, SOP-004). |
| W3.2 | done | [`src/chunker.py`](../src/chunker.py), [`docs/w3_chunking.md`](../docs/w3_chunking.md) | Two strategies: one chunk per numbered clause (`section`, 172 chunks) and 120-word windows with 30 words of overlap (`window`, 71 chunks). Compared in Experiment 2. |
| W3.3 | done | [`src/retriever.py`](../src/retriever.py), [`eval/eval_retrieval.py`](../eval/eval_retrieval.py) | BM25 + dense (`paraphrase-multilingual-MiniLM-L12-v2`) fused with reciprocal rank fusion (k = 60, top 20 each), then a cross-encoder reranker (`mmarco-mMiniLMv2-L12-H384-v1`). Both models run locally: no API cost, same result on every run. Four modes for the ablation: `bm25`, `dense`, `hybrid`, `hybrid_rerank`. |
| W3.4 | done | [`src/rag_chain.py`](../src/rag_chain.py), [`prompts/v3_rag.txt`](../prompts/v3_rag.txt) | Top 5 public passages numbered `[1]..[N]`; every answer must cite them, citations are checked in code (one retry, then abstain); internal SOPs go to a separate, uncitable block; fixed abstention sentence in English and Turkish. |
| W3.5 | done | [`data/w3_retrieval_test.jsonl`](../data/w3_retrieval_test.jsonl), [`reports/w3_retrieval.json`](w3_retrieval.json) | 50 questions with gold clauses: 40 by Arda (12 keyword, 21 paraphrase, 7 Turkish, each with an expected answer) and 10 by Dilara (7 Turkish, 3 paraphrase). A question may list several acceptable clauses. hit@1/3/5/10 and MRR@10, public chunks only. |
| W3.6 | done | [`src/faithfulness.py`](../src/faithfulness.py), [`eval/faithfulness_kappa.py`](../eval/faithfulness_kappa.py), [`data/w3_claim_labels_ai_reference.jsonl`](../data/w3_claim_labels_ai_reference.jsonl), [`w3_faithfulness_kappa.json`](w3_faithfulness_kappa.json) | Claim-by-claim judge: each answer is split into claims, each labeled supported or unsupported by the passages the system saw. The check on 30 claims (random, seed 390) uses reference labels drafted by **Claude (Anthropic)** and reviewed and confirmed one by one by Arda: agreement 30/30, κ = 1.0, but the sample has only 1 unsupported claim (Experiment 4). `eval/label_claims.py` is in place for human labels. |
| W3.7 | done | [`reports/w3_retrieval.json`](w3_retrieval.json) | Ablation 1: retrieval mode (4 arms). Ablation 2: chunking (section vs window). Experiments 1 and 2. |
| W3.8 | done | [`docs/w3_failure_analysis.md`](../docs/w3_failure_analysis.md), [`w3_failure_labels.json`](w3_failure_labels.json) | All 26 failed answers labeled by a fixed rule: 2 retrieval, 24 generation, 0 evaluation. |

---

## 3. Scoreboard

```json
{
  "week": 3,
  "test_set_size": 45,
  "e2e_accuracy": {"value": 0.5556, "ci95": [0.4104, 0.7007], "n": 45, "script": "eval/run_w3_rag.py"},
  "abstention_correct": {"value": 1.0, "ci95": [1.0, 1.0], "n": 7, "script": "eval/run_w3_rag.py"},
  "unsupported_claims": {"value": 0.0098, "ci95": [0.0, 0.0289], "n": 102, "script": "eval/run_w3_rag.py"},
  "hit_at_5": {"value": 0.92, "ci95": [0.8448, 0.9952], "n": 50, "script": "eval/run_w3_rag.py"},
  "mrr": {"value": 0.791, "ci95": [0.6945, 0.8879], "n": 50, "script": "eval/run_w3_rag.py"},
  "task_success": {"value": null, "n": null, "script": null},
  "pass_k": {"k": null, "value": null, "n": null, "script": null},
  "injection_success": {"value": null, "n": null, "script": null},
  "cost_per_task_usd": 0.000486,
  "latency_p50_s": 2.943,
  "spend_week_usd": 0.1536,
  "spend_total_usd": 0.3313
}
```

Changes to test sets this week: the 45-case Week 2 test set is unchanged (`data/w2_test_set.jsonl`). New: the 50-question retrieval set `data/w3_retrieval_test.jsonl` (SHA-256 in `reports/scoreboard_w3.json`). `hit_at_5` and `mrr` are for the system configuration (`hybrid_rerank`, section chunks) on that set; `unsupported_claims` counts claims in the 52 answers that did not abstain (Week 2 cases and W3.5 questions). The judge is now version 3 on `gemini-3.5-flash-lite` (Section 4, Experiment 3); `gemini-3.1-flash-lite`, last week's judge, answered with "503 overloaded" for most of 23–24 November. One request is now local retrieval plus one or two answer calls, so cost and latency are not comparable with Week 2; `latency_p50_s` is wall time per request and includes the API's retry waits. Spend is at list prices (free tier), with `gemini-3.5-flash-lite` at $0.30 / $2.50 per 1M tokens; smoke runs and runs stopped by API errors on 23–24 November are not in it.

---

## 4. Experiments

### Experiment 1: Which retrieval mode? (`W3.3`, `W3.7` ablation 1)

- **Hypothesis:** Turkish questions and paraphrases share few words with the English documents, so dense retrieval will beat BM25 on them; the reranker will move the right clause to the top (better hit@1 and MRR).
- **Change:** Only the mode changes (`bm25`, `dense`, `hybrid`, `hybrid_rerank`). Fixed: the 50 questions, section chunks, public chunks only, the same two local models. A question is a hit at k when a top-k chunk is from a gold document and covers a gold clause.
- **Result:**

  | Mode (section chunks) | hit@1 | hit@3 | hit@5 | hit@10 | MRR | hit@5 EN (n = 36) | hit@5 TR (n = 14) |
  |---|---|---|---|---|---|---|---|
  | `bm25` | 0.48 | 0.60 | 0.64 | 0.72 | 0.550 | 0.78 | 0.29 |
  | `dense` | 0.54 | 0.78 | 0.90 | 0.98 | 0.683 | 0.89 | 0.93 |
  | `hybrid` | 0.50 | 0.70 | 0.82 | 0.94 | 0.638 | 0.86 | 0.71 |
  | **`hybrid_rerank`** | **0.72** | **0.86** | **0.92** | 0.94 | **0.791** | **0.94** | 0.86 |

  `hybrid_rerank` vs `bm25` on hit@5: 15 questions only it finds, 1 only BM25 finds, McNemar exact p = 0.0005. `dense` vs `bm25`: 16 vs 3, p = 0.004. Fusion without the reranker loses part of the dense gain on Turkish (0.93 → 0.71), because BM25 contributes mostly wrong chunks for Turkish queries and RRF weights both lists equally; the reranker wins most of it back and lifts hit@1 from 0.50 to 0.72. `hybrid_rerank` vs `hybrid` on hit@5 (6 vs 1, p = 0.125) is not significant at n = 50.
- **Decision:** The system uses `hybrid_rerank` on section chunks. The rule (highest MRR among section-chunk modes on this set) was fixed in the script before the answers were generated; because the mode was chosen on the same 50 questions it is measured on, its numbers are optimistic. BM25 stays in the fusion for exact codes (SKUs, `FINAL-SALE`, order numbers); a fusion that weights dense higher for Turkish queries is a candidate for next week.

### Experiment 2: Clause chunks or fixed windows? (`W3.2`, `W3.7` ablation 2)

- **Hypothesis:** One chunk per clause beats 120-word windows, because a window mixes unrelated rules.
- **Change:** Only the chunking changes; all four modes run on both.
- **Result:** Windows score equal or higher in every mode: hit@5 `bm25` 0.76 vs 0.64 (6 vs 0, p = 0.031), `dense` 0.94 vs 0.90, `hybrid` 0.92 vs 0.82, `hybrid_rerank` 0.94 vs 0.92 (1 vs 0, p = 1.0); MRR `hybrid_rerank` 0.837 vs 0.791. The hypothesis is not supported. Caveat: a window covers several clauses (70 of 71 windows span more than one), and a window counts as a hit if any covered clause is gold, so this rule favors windows.
- **Decision:** Keep section chunks in the system for now: with the reranker the difference is one question, and a section chunk lets the answer cite the exact clause (`[POL-005 §3]`), which the claim judge and the customer both need. Next week, rescore with a stricter rule (the gold clause must be the window's main clause) before switching.

### Experiment 3: Does retrieval improve the answers? (`W3.4`)

- **Hypothesis:** With retrieved passages, accuracy on the 9 corpus-answerable Week 2 cases rises above the Week 2 system's (3/9 in the Week 2 report), and overall accuracy on the 45 cases does not drop.
- **Change:** Week 2 system (v3 prompt, rules in the prompt, no documents) vs Week 3 system (`rag_chain`, `prompts/v3_rag.txt`, top 5 passages). Both graded by the same judge (version 3, `gemini-3.5-flash-lite`). Judge version 3 is version 2 with: the list of real document codes (so `[POL-005 §2]` or `[1]` is not "fabrication", the Week 2 decision), the retrieved passages, the fixed abstention sentence described as an abstention rather than a capability claim, and the Week 2 rule that a correct decision with a different rule passes C1 only if that rule is in the passages. The Week 2 answers were re-graded with it, so they score 0.89 here (0.80 in Week 2 with judge version 2).
- **Result:**

  | | Without documents (Week 2 v3) | With documents (Week 3) |
  |---|---|---|
  | All 45 cases | **0.89** [0.80, 0.98] (40/45) | **0.56** [0.41, 0.70] (25/45) |
  | 9 corpus cases | 5/9 | 7/9 |
  | normal (n = 19) | 15 | 9 |
  | edge (n = 10) | 9 | 3 |
  | adversarial (n = 9) | 9 | 6 |
  | unanswerable (n = 7) | 7 | 7 |

  Paired: 4 cases only the RAG system gets right (W2-D03, D05, D11, D14, all policy questions the Week 2 system got wrong from memory), 19 only the Week 2 system gets right; McNemar exact p = 0.0026. On the 40 W3.5 questions, all answerable from the documents, the RAG system gets 34 right (0.85; English 28/33, Turkish 6/7).
- **Decision:** The hypothesis holds for document questions (5/9 → 7/9 under the same judge, and 0.85 on the 40 W3.5 questions) and fails overall. The loss is not from retrieval: 22 of the 26 failures are the fixed abstention sentence (Section 5). The documents help where the question is about a document and hurt everywhere else, because the prompt has no way to say "I can't check your order yet". Next week's first change is in `prompts/v3_rag.txt` (Section 10). Confounder: the Week 2 answers came from `gemini-3.1-flash-lite`; the Week 3 answers came from `rag_chain`'s fallback chain (57 `gemini-3.5-flash-lite`, 24 `gemini-2.5-flash`, 4 `gemini-3.1-flash-lite`) because of the overload. The failure pattern (the exact fixed sentence) comes from the prompt and the code, not from one model, but the size of the drop carries this caveat.

### Experiment 4: Are the answers faithful, and can the claim judge be trusted? (`W3.6`)

- **Hypothesis:** Fewer than 10% of claims are unsupported by the retrieved passages, and the claim judge agrees with a human at κ ≥ 0.6.
- **Change:** One judge call per non-abstaining answer (`src/faithfulness.py`, `gemini-3.5-flash-lite`) splits it into claims and labels each against the passages the system saw, not against the expected answer. A fixed random sample of 30 claims (seed 390) was labeled by Claude (Anthropic), a different model family from the Gemini judge, from the claim and the passages only, without the judge's labels; Arda then reviewed and confirmed each of the 30 labels against the passages.
- **Result:** 1 of 102 claims unsupported (0.0098, 95% CI 0–0.029), over 52 answers; 1 answer contains an unsupported claim. Judge vs reference labels on 30 claims: 30/30 agree (29 supported, 1 unsupported, the same claim: W2-D15's "13 October to 13 November is within the 30-day period", which POL-001 §1 contradicts); κ = 1.0. With only 1 unsupported claim in the sample, chance agreement is already 0.94 and a single disagreement on that claim would give κ = 0, so this mostly shows the judge does not flag supported claims; it says little about how well it finds unsupported ones. One known blind spot: in W2-D13 the claim "the Speedgoat 5 is available in EU 44.5" was labeled supported because the passage lists the sizes the shoe is made in; the customer asked about stock. The C1–C5 judge caught it (C2), the claim judge did not.
- **Decision:** The hypothesis holds for the rate (1% < 10%); κ meets the threshold on paper but is not informative on this sample, and the reference labels were drafted by an AI and then reviewed by a person rather than written independently by a person. We keep the claim judge for `unsupported_claims` and next week check it on a sample stratified toward unsupported claims (about half), labeled by a team member, plus the W2-D13 kind of claim (a size range stated as stock).

**Limits of these numbers.** The retrieval set has 50 questions and the mode was chosen on it, so the system's hit@5 and MRR are optimistic; the confidence intervals are wide (hit@5 0.84–1.0). Arda wrote 40 of the 50 questions and the expected answers; Dilara, who built the retriever, wrote 10 and did not run the retriever on them before handing them over. The faithfulness value is low partly because 33 of 85 answers abstained and contain no claims, and its check uses AI-drafted, human-reviewed labels on a sample with a single unsupported claim. One judge model grades both systems, but it is a different model from Week 2's, so Week 2 and Week 3 scoreboards are not directly comparable; Experiment 3 re-grades Week 2 to make that one comparison fair.

---

## 5. Failure analysis

Full table and method: [`docs/w3_failure_analysis.md`](../docs/w3_failure_analysis.md). 26 of 85 answers failed; the rule labels 2 as retrieval and 24 as generation.

| Group | n | Cases (examples) | Retrieval or generation |
|---|---|---|---|
| Abstained although the answer was in a retrieved passage | 10 | W3-R10 (damage report deadline; POL-006 §1 retrieved), W2-D12, W2-A21 | generation |
| Abstained on an order, stock or tracking request (expected: say it cannot be checked yet, ask for details) | 9 | W2-D09 "Where is my order ORD-2026-8841?", W2-A01, W2-A14 (Turkish) | generation |
| Abstained on an attack instead of refusing it and handling the real request | 2 | W2-D24, W2-A13 | generation |
| Answered wrongly | 3 | W2-D13 (size range stated as stock), W2-D15 (31 days called "within 30"), W3-R37 (no escalation) | generation |
| Right clause not retrieved | 2 | W3-R22 "Do you ship to Germany?" (got domestic shipping), W3-R26 sole separation (got return rules, not the warranty) | retrieval |

---

## 6. Response to last week's feedback

none this week (no written feedback on Week 2 was received)

---

## 7. Product track

Dilara interviewed two support employees of small online stores (clothing; food), by phone on 23 November ([`docs/w3_customer_interviews.md`](../docs/w3_customer_interviews.md)). Both name the same three most common questions, which are the agent's three jobs: where is my parcel, is it in stock, can I return it. Our volume assumption did not hold (20 and 60 messages a day, not 180), and handling takes longer than we assumed (15 and 9 minutes, not 6), so the time to save per message is larger. Both have lost money on a wrong return approval made by a person, and both fear a wrong answer from an AI. **One change:** returns will need a staff member's approval before the agent creates them; tracking, stock and policy answers stay automatic. Limits: two interviews, neither from a sports store, several questions not asked.

This week's evaluation supports the same direction from the other side: the agent's most common failure is refusing to help (Section 5), not inventing an answer.

---

## 8. Contributions

| Member | Role | What they did this week | Commits or files | Hours |
|---|---|---|---|---|
| **Uygar Ege Kocakır** | Agent and tools lead | Wrote the RAG answer chain with numbered citations, citation checks, internal-document isolation and the bilingual fixed abstention (`W3.4`); fixed the Week 2 classifier schema and urgency (`W2.1`); updated the model fallback chain in `src/llm.py`. | `src/rag_chain.py`, `prompts/v3_rag.txt`, `src/schemas.py`, `src/classifier.py`, `src/llm.py` (commits `a59fec3`, `7a273f2`, `9a28422`) | 14 |
| **Dilara Yıldız** | Data and retrieval lead | Wrote the 32-document corpus (`W3.1`) and both chunkers (`W3.2`); built BM25, the multilingual dense retriever, RRF and the reranker (`W3.3`) and the hit@k/MRR script; wrote 10 Turkish and paraphrase retrieval questions; ran the two customer interviews (product track). | `data/corpus/`, `src/chunker.py`, `src/retriever.py`, `eval/eval_retrieval.py`, `data/w3_retrieval_questions_dilara.jsonl`, `docs/w3_chunking.md`, `docs/w3_customer_interviews.md` (commits `ba51108` to `123a4dd`) | 15 |
| **Arda Agovic** | Evaluation and safety lead | Wrote 40 retrieval questions with gold clauses and expected answers and merged Dilara's 10 (`W3.5`); wrote the evaluation harness, judge version 3 and the claim-by-claim faithfulness judge, and reviewed the 30 reference labels for its check (`W3.6`); ran both ablations (`W3.7`); labeled and grouped the failures (`W3.8`); added multi-clause gold support to `eval/eval_retrieval.py`; wrote this report. | `data/w3_retrieval_test.jsonl`, `eval/run_w3_rag.py`, `src/judge.py`, `src/faithfulness.py`, `eval/label_claims.py`, `eval/faithfulness_kappa.py`, `data/w3_claim_labels_ai_reference.jsonl`, `docs/w3_failure_analysis.md`, `reports/scoreboard_w3.json`, `reports/week-3.md` | 14 |

---

## 9. AI tools used

| Tool | Used for |
|---|---|
| **Anthropic Claude**, **ChatGPT** (Arda) | Code development, debugging, technical research and documentation. Claude drafted `eval/run_w3_rag.py`, judge version 3, `src/faithfulness.py`, `eval/label_claims.py`, `eval/faithfulness_kappa.py`, the 40 retrieval questions with gold clauses and expected answers, the failure grouping and this report; Claude also drafted the 30 reference labels for the faithfulness check, which Arda reviewed and confirmed (Experiment 4). Arda ran the evaluation on his machine. |
| **Anthropic Claude**, **ChatGPT** (Uygar) | Technical research, code optimization and comparing alternative solutions for `src/rag_chain.py`, the classifier fix and the model fallback chain. |
| **ChatGPT** (Dilara) | Drafting questions (the 10 retrieval questions were written with AI help and checked one by one by Dilara, R15), prompt development and editing content. |
| **Google Gemini API** (`gemini-3.5-flash-lite`, `gemini-2.5-flash`, `gemini-3.1-flash-lite`) | 85 RAG answers (plus 5 citation retries), 130 C1–C5 judge calls (85 RAG answers + 45 re-graded Week 2 answers), 52 claim-judge calls. Retrieval used local models only. |

---

## 10. Next week

| Priority | Metric it should move | Expected change |
|---|---|---|
| **1. A third path in `prompts/v3_rag.txt`: for order, stock and tracking requests, say they cannot be checked yet and ask for the details; answer the policy part from the passages; keep the Week 2 injection refusal** | `e2e_accuracy` | Back to at least the 0.89 of the no-document system on the 45 cases, while keeping 7/9 or better on the corpus cases and 0.85 on the W3.5 questions; the 21 abstentions in groups 1–3 of Section 5 are the target. |
| **2. Order, stock and tracking tools with a human approval step for returns (Week 4, and the product-track change)** | `task_success` | First measured value; the 9 lookup cases in Section 5 become answerable. |
| **3. Retrieval: dense-weighted fusion for Turkish queries and a stricter window rule** | `hit_at_5`, `mrr` | Turkish hit@5 from 0.86 toward the 0.93 of dense alone, with the two English misses (W3-R22, W3-R26) checked again. |
