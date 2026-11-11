# Weekly Report — Week 1

| | |
|---|---|
| **Team** | TrailGuard AI |
| **Use case** | UC1 — Online Store Support Agent (*TrailRun TR* Specialty Trail Running & Outdoor Gear Store) |
| **Week** | 1 |
| **Repository** | `https://github.com/uygaregeK/trailguard-ai` |
| **Commit tag** | `week-1` |
| **Presenter** | Uygar Ege Kocakır & Dilara Yıldız |
| **Members and roles** | Uygar Ege Kocakır (Agent and tools lead), Dilara Yıldız (Data and retrieval lead), Arda Agovic (Evaluation and safety lead) |

---

## 1. Summary

We built the repository, multi-temperature evaluation harness (`eval/run_w1_baseline.py`), and baseline system prompt (`prompts/v1_baseline.txt`) for **TrailGuard AI**, an automated customer support and return operations agent for *TrailRun TR* (`UC1`). We curated 25 realistic customer inputs (`data/w1_inputs.jsonl`) spanning all Section 10 ingredients, specified our 32-document RAG corpus and 5-table store schema (`docs/data_inventory.md`), and ran all 25 inputs across $T \in \{0.0, 0.7, 1.2\}$ (75 live Gemini API calls in `data/w1_baseline_outputs.json`). At $T = 0.0$, mean cost is $\$0.000362$/task ($\$0.3618$ per 1,000 requests), median latency is $1.115\text{ s}$, and exact ID preservation is $100.0\%$ ($15/15$).

---

## 2. Deliverables

| ID | Status | Evidence | Note |
|---|---|---|---|
| W1.1 | done | [`docs/team_agreement.md`](../docs/team_agreement.md) | Roles, Monday + T-48h meetings, 2-of-3 decision rule, non-delivery escalation, and university IP-compliant post-course ownership. |
| W1.2 | done | [`docs/use_case_brief.md`](../docs/use_case_brief.md) | First customer (*TrailRun TR*), persona (Mert Demir), manual 4-tab workflow analysis, 5 user stories, and in/out-of-scope table. |
| W1.3 | done | [`data/w1_inputs.jsonl`](../data/w1_inputs.jsonl) | 25 realistic inputs (`W1-001`–`W1-025`) labeled with Section 10 ingredients (`exact_identifiers`: 15, `questions`: 11, `look_ups`: 11, `actions`: 7, `multi_step`: 6, `untrusted_input`: 5, `unanswerable`: 4). |
| W1.4 | done | [`docs/data_inventory.md`](../docs/data_inventory.md) | 32-document RAG corpus metadata (`POL-001`–`SOP-004`), 5 database tables (`orders`, `order_items`, `products`, `shipments`, `returns`), `create_return_request` API sketch, and untrusted input sources. |
| W1.5 | done | [`prompts/v1_baseline.txt`](../prompts/v1_baseline.txt), [`eval/run_w1_baseline.py`](../eval/run_w1_baseline.py), [`data/w1_baseline_outputs.json`](../data/w1_baseline_outputs.json) | Baseline prompt run across all 25 inputs at $T \in \{0.0, 0.7, 1.2\}$ (75 live calls) with token, latency, ID-preservation (`15/15` vs `14/15`), and Jaccard similarity comparison. |
| W1.6 | done | [`docs/cost_and_failures.md`](../docs/cost_and_failures.md#L8-L45), [`reports/scoreboard_w1.json`](scoreboard_w1.json) | Exact token & USD math: $\bar{n}_{\text{in}} = 528.16$, $\bar{n}_{\text{out}} = 126.00$, $\$0.000362$/request ($\$0.3618$/1k requests) at $T=0.0$ using official Google AI Studio paid-tier pricing, plus Week 4 multi-step agent projection. |
| W1.7 | done | [`docs/cost_and_failures.md`](../docs/cost_and_failures.md#L48-L85) | 7 predicted failure modes linked to Module 1 concepts (hallucination, BPE tokenization of SKUs, knowledge cutoff, statelessness, autoregressive "no going back", RLHF sycophancy, sampling entropy). |
| W1.8 | done | [`README.md`](../README.md), [`requirements.txt`](../requirements.txt), [`.env.example`](../.env.example) | Clean repository structure with reproducible setup commands (`python3 eval/run_w1_baseline.py --recompute`), tagged `week-1`. |

---

## 3. Scoreboard

```json
{
  "week": 1,
  "test_set_size": 25,
  "e2e_accuracy": null,
  "abstention_correct": null,
  "unsupported_claims": null,
  "hit_at_5": null,
  "mrr": null,
  "task_success": null,
  "pass_k": null,
  "injection_success": null,
  "cost_per_task_usd": 0.000362,
  "latency_p50_s": 1.115,
  "spend_week_usd": 0.028,
  "spend_total_usd": 0.028
}
```

Changes to any test set this week: Created the initial 25-case baseline evaluation dataset (`data/w1_inputs.jsonl`, `W1-001` through `W1-025`) covering `exact_identifiers` (15), `questions` (11), `look_ups` (11), `actions` (7), `multi_step` (6), `untrusted_input` (5), and `unanswerable` out-of-scope queries (4).

---

## 4. Experiments

### Experiment 1: Temperature Sensitivity on Support Determinism, Identifier Preservation, Latency, and Token Cost (`W1.5`, `W1.6`)
- **Hypothesis**: Running `prompts/v1_baseline.txt` at $T = 0.0$ (greedy decoding) will produce higher lexical consistency and preserve exact store identifiers (`ORD-`, `SKU-`, `TRK-`, `RMA-`) more reliably than $T = 0.7$ and $T = 1.2$.
- **Change**: Executed all 25 inputs in `data/w1_inputs.jsonl` at $T = 0.0$, $T = 0.7$, and $T = 1.2$ (`eval/run_w1_baseline.py`, 75 live API calls saved in `data/w1_baseline_outputs.json`: 35 calls on `gemini-2.5-flash` with `thinking_budget=0` and 40 calls on `gemini-3.1-flash-lite`, with $n_{\text{think}} = 0$ across all 75 calls; 32 calls from the initial run — all 13 `gemini-3.5-flash` fallback calls plus 19 `W1-003`–`W1-011` calls — were re-run with the identical prompt `prompts/v1_baseline.txt` due to Free Tier quota limits to eliminate `3.5-flash` thinking tokens and maximize `gemini-2.5-flash` coverage up to the 20 RPD Free Tier cap).
- **Result** (reproducible via `python3 eval/run_w1_baseline.py --recompute`):
  - **Tokens & Cost (`T = 0.0` vs `0.7` vs `1.2`)**: Mean input tokens remained constant at $\bar{n}_{\text{in}} = 528.16$. Mean output tokens rose from $126.00$ at $T=0.0$ ($\$0.000362$/task or $\$0.3618 / 1\text{k}$ tasks) to $132.56$ at $T=0.7$ ($\$0.000378$/task or $\$0.3779 / 1\text{k}$ tasks) and $131.64$ at $T=1.2$ ($\$0.000382$/task or $\$0.3820 / 1\text{k}$ tasks). Total spend across all 75 calls (`spend_week_usd`) is $\$0.0280$ at official paid-tier rates ($\$0.30/\$2.50$ per 1M tokens for `gemini-2.5-flash`; $\$0.25/\$1.50$ per 1M tokens for `gemini-3.1-flash-lite`).
  - **Latency ($p_{50}$ / $p_{95}$)**: Median latency $p_{50}$ was $1.115\text{ s}$ ($T=0.0$), $1.155\text{ s}$ ($T=0.7$), and $1.235\text{ s}$ ($T=1.2$); tail latency $p_{95}$ was $1.894\text{ s}$ ($T=0.0$), $6.027\text{ s}$ ($T=0.7$), and $7.452\text{ s}$ ($T=1.2$). Note that tail latency differences are driven primarily by the model mix (`gemini-2.5-flash` vs `gemini-3.1-flash-lite`), output token length, and Free Tier rate-limit backoff (e.g., `W1-023` at $T=1.2$ recorded `84.25s` total wall time due to quota retry backoff before fallback, which sits above $p_{95}$ and does not affect $p_{50}$ or $p_{95}$).
  - **Lexical Determinism & Exact ID Preservation (`15/15` vs `14/15`)**: Across the 15 cases containing exact alphanumeric identifiers, $T=0.0$ and $T=0.7$ preserved $100.0\%$ ($15/15$) of IDs, whereas $T=1.2$ dropped to $93.3\%$ ($14/15$) because `W1-011` omitted `SKU-LKI-ULTZ-120`. Mean lexical Jaccard similarity against $T=0.0$ dropped from $0.5870$ at $T=0.7$ (min $0.3883$) to $0.4733$ at $T=1.2$ (min $0.2396$).
- **Decision**: Lock $T = 0.0$ as the default for Week 2 classification (`W2.1`), entity extraction, and policy enforcement to guarantee $100\%$ exact identifier retention and deterministic outputs.

---

## 5. Failure analysis

| # | Input (short) | What happened | Root cause | Fix (done or planned) |
|---|---|---|---|---|
| 1 | `W1-003`: *"If I exchange a hydration vest for a larger size, do I have to pay for the return courier and replacement shipping?"* | Across $T=0.0$ (`50` output tokens), $T=0.7$ (`64` tokens), and $T=1.2$ (`46` tokens) on `gemini-2.5-flash`, the model fabricated a free-shipping policy (`"you typically do not have to pay for the return courier or the replacement shipping"` / `"TrailRun TR covers the shipping costs for both"`), even though `prompts/v1_baseline.txt` contains no exchange shipping fee rule. | **Module 1 — Knowledge Cutoff & Next-Token Plausibility (Hallucination)**: Without the store's exchange logistics policy (`POL-005`) in context, the model completes the prompt with plausible-sounding e-commerce boilerplate instead of abstaining. | **Planned (Week 3 — `W3.1`–`W3.4`)**: Index the 32 store policy/SOP documents with hybrid BM25 + dense RAG, reranker, numbered citations, and a fixed abstention response when documents lack the answer. |
| 2 | `W1-011` ($T=1.2$): *"I need to open a return for defective arrival on order ORD-2026-9015 for the broken carbon pole SKU-LKI-ULTZ-120."* | While $T=0.0$ (`169` tokens) and $T=0.7$ (`175` tokens) preserved both `ORD-2026-9015` and `SKU-LKI-ULTZ-120`, at $T=1.2$ (`94` tokens, `gemini-2.5-flash`) the model wrote `"initiating a return for the defective pole from order ORD-2026-9015"` and completely dropped `SKU-LKI-ULTZ-120` (reducing exact ID preservation to $14/15 = 93.3\%$). | **Module 1 — BPE Subword Tokenization & High-$T$ Sampling Entropy**: Flattening logits at $T=1.2$ increases the probability of paraphrasing multi-token alphanumeric SKUs into generic noun phrases (`"the defective pole"`). | **Planned (Week 2 — `W2.1`)**: Extract `entities` (`order_id`, `sku`) into a strict JSON schema at $T=0.0$ with regex validation and automatic retry. |
| 3 | `W1-010` ($T=0.7$) & `W1-024` ($T=1.2$): Requesting order lookup and return creation for `ORD-2026-8841`. | Despite `prompts/v1_baseline.txt` stating no live tools are connected yet, `gemini-2.5-flash` told the user `"I can look it up if you grant me permission to access order details for ORD-2026-8841"` (`W1-010`, $T=0.7$, `186` tokens) and `"Please confirm the delivery date if you have it, or I can attempt to look it up"` (`W1-024`, $T=1.2$, `162` tokens). | **Module 1 — Stateless Text Prediction Without Environment Grounding**: A bare LLM has no intrinsic awareness of runtime tool availability and generates conversational offers to "attempt a lookup" unless grounded by actual tool schemas. | **Planned (Week 4 — `W4.1`, `W4.7`)**: Wire deterministic `lookup_order`, `search_policy_docs`, and sandboxed `create_return_request` tools into the bounded agent loop. |

---

## 6. Response to last week's feedback

none this week

---

## 7. Product track

- **First Customer (`W1.2`)**: **TrailRun TR**, an Istanbul-based specialty online store selling technical trail running shoes, hydration vests, and GPS watches.
- **Target Persona**: **Mert Demir**, Customer Operations Manager overseeing a small support team across web chat, WhatsApp, and email.
- **What Job They Do By Hand Today (and Operational Assumptions to Validate in Week 3)**: Based on our initial domain scoping in `docs/use_case_brief.md` (where operational volumes such as ~180 tickets/day, ~6 minutes/ticket, and ~\$1,200/month in preventable return write-offs are explicitly tracked as baseline assumptions to validate during our Week 3 customer interviews), a human support agent today manually switches across **four browser tabs** per ticket: (1) Shopify order admin to check `order_id` delivery dates and `FINAL-SALE` flags, (2) Yurtiçi/Aras Kargo portals to check `TRK-...` hub scans, (3) an internal Notion wiki to check category-specific return rules (indoor-tried vs mud-worn shoes, GPS watch hygiene seals, 2-year Gore-Tex warranty), and (4) an RMA spreadsheet to issue return shipping codes.

---

## 8. Contributions

| Member | Role | What they did this week | Commits or files | Hours |
|---|---|---|---|---|
| **Uygar Ege Kocakır** | Agent and tools lead | Set up repository structure (`README.md`, `requirements.txt`, `.gitignore`, `.env.example`), implemented Gemini API client (`src/llm.py`), baseline prompt (`prompts/v1_baseline.txt`), and evaluation harness (`eval/run_w1_baseline.py`), and executed the live API runs (`W1.5`, `W1.6`, `W1.8`). | [`src/llm.py`](../src/llm.py), [`prompts/v1_baseline.txt`](../prompts/v1_baseline.txt), [`eval/run_w1_baseline.py`](../eval/run_w1_baseline.py), [`README.md`](../README.md) | 5.0h |
| **Dilara Yıldız** | Data and retrieval lead | Authored and refined the use case brief, customer persona, explicit operational assumptions, 5 user stories, and scope boundaries (`docs/use_case_brief.md`, `W1.2`) and the 32-document RAG corpus metadata, 5-table DB schema, and action API inventory (`docs/data_inventory.md`, `W1.4`). | [`docs/use_case_brief.md`](../docs/use_case_brief.md), [`docs/data_inventory.md`](../docs/data_inventory.md), [`docs/appendix_c_preferences.md`](../docs/appendix_c_preferences.md) | 4.5h |
| **Arda Agovic** | Evaluation and safety lead | Validated the 25 labeled test inputs (`data/w1_inputs.jsonl`, `W1.3`), audited baseline outputs (`data/w1_baseline_outputs.json`), verified token/cost math and Module 1 failure analysis (`docs/cost_and_failures.md`, `W1.6`, `W1.7`), finalized `docs/team_agreement.md` (`W1.1`), and audited `reports/week-1.md`. | [`data/w1_inputs.jsonl`](../data/w1_inputs.jsonl), [`data/w1_baseline_outputs.json`](../data/w1_baseline_outputs.json), [`docs/cost_and_failures.md`](../docs/cost_and_failures.md), [`docs/team_agreement.md`](../docs/team_agreement.md), [`reports/week-1.md`](week-1.md) | 4.5h |

---

## 9. AI tools used

| Tool | Used for |
|---|---|
| **Google Antigravity (AI Coding Assistant)** | Assisted with writing `src/llm.py` and `eval/run_w1_baseline.py`, structuring the 25 test cases in `data/w1_inputs.jsonl`, and drafting markdown documentation in `docs/` and `reports/week-1.md`. |
| **Claude Code / Anthropic Claude** | Independent audit of `eval/run_w1_baseline.py` metric formulas, verification of `data/w1_baseline_outputs.json` against `reports/week-1.md` failure analysis rows, and cross-checking Weeks 1–7 deliverable IDs against `Prompt_Engineering_Project_Handbook.pdf`. |
| **Google Gemini API (`gemini-2.5-flash` & `gemini-3.1-flash-lite`)** | Live execution of the 25 baseline evaluation cases across $T \in \{0.0, 0.7, 1.2\}$ (75 API calls total). |

---

## 10. Next week

| Priority | Metric it should move | Expected change |
|---|---|---|
| **1. Request Classifier (`W2.1`) & 6-Block Versioned Main Prompt (`W2.2`)** — Implement `T=0.0` JSON classifier (`intent`, `entities`, `urgency`) with schema validation/retry and compare 3 prompt versions (`W2.5`). | `e2e_accuracy`, `abstention_correct` | Populate `e2e_accuracy` ($\ge 0.80$ with 95% CI & McNemar test) and `abstention_correct` ($\ge 0.90$). |
| **2. 40+ Case Tagged Test Set (`W2.3`) & Single-Command Harness (`W2.4`)** — Expand test set to $\ge 40$ cases ($\ge 5$ unanswerable, $\ge 5$ adversarial, $\ge 5$ edge) and build single-command scoreboard runner. | `test_set_size` | Increase `test_set_size` from `25` to `45` and automate scoreboard JSON generation. |
| **3. LLM Judge Calibrated with Cohen's $\kappa$ (`W2.6`), Hallucination Log (`W2.7`) & 3 Direct Injection Tests (`W2.8`)** — Compare LLM judge against 20 human labels ($\kappa$), log $\ge 10$ typed hallucinations, and test 3 direct injections. | `e2e_accuracy`, `injection_success` (baseline check) | Achieve human–judge agreement $\kappa \ge 0.75$ and document 10+ categorized hallucinations + 3 direct injection outcomes. |
