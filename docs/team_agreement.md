# W1.1 — Team Agreement

**Project:** TrailGuard AI (`UC1` — Online Store Support Agent for *TrailRun TR*)  
**Date:** Week 1 (Fall 2026)

---

## 1. Team Members, Official Roles, and Owned Scoreboard Metrics

| Member | Official Handbook Role | Primary Technical Scope | Secondary Scope (Cross-Area Commits) | Owned Scoreboard Metrics |
| :--- | :--- | :--- | :--- | :--- |
| **Uygar Ege Kocakır** | **Agent and tools lead** | System prompts (`prompts/`), LLM client (`src/llm.py`), request classifier (`src/classifier.py`), agent loop (`src/agent.py`), context management (`src/context_manager.py`), tools (`src/tools.py`), MCP server (`src/mcp_server.py`), CLI runner (`app/run.py`) | Baseline evaluation harness (`eval/run_w1_baseline.py`), cost & latency analysis | `task_success`, `cost_per_task_usd`, `latency_p50_s`, `spend_week_usd`, `spend_total_usd` |
| **Dilara Yıldız** | **Data and retrieval lead** | 32-document corpus (`data/corpus/`), document cleaning & metadata, chunking (`src/chunker.py`), BM25 + dense hybrid search & reranker (`src/retriever.py`), store database & resettable sandbox (`src/db.py`, `src/sandbox.py`) | Versioned prompt templates (`prompts/`), hallucination log & lethal trifecta analysis | `hit_at_5` (plus `hit_at_1, 3, 10`), `mrr`, `unsupported_claims` |
| **Arda Agovic** | **Evaluation and safety lead** | Test sets (`data/`), evaluation harnesses (`eval/`), bootstrap 95% CIs & McNemar test (`eval/stats.py`), LLM judge & Cohen's $\kappa$ calibration (`src/judge.py`), red-team exchange & security evaluation (`eval/run_w5_security.py`), `pass^5` & regression checks | Direct/indirect injection test cases, guardrails (`src/guardrails.py`), weekly scoreboard compilation (`reports/`) | `test_set_size`, `e2e_accuracy`, `abstention_correct`, `pass_k` ($\text{pass}^5$), `injection_success` |

---

## 2. Weekly Meeting Times & Communication Channels

- **Primary Sync #1 (Build & Sprint Planning):** Every **Monday, 19:00–20:30** (Zoom / Discord + GitHub). Goal: Review instructor feedback from the weekly check-in, assign the week's deliverables, and agree on target metric improvements.
- **Primary Sync #2 (Integration, Eval & Report Freeze):** Every **48 hours before class, 19:00–21:00**. Goal: Pull all changes on `main`, run the evaluation harness, populate `reports/week-N.md`, rehearse the 8-minute weekly presentation, and push the `week-N` git tag at least 24 hours before the weekly session.
- **Async Communication:** WhatsApp/Discord group with a **maximum 6-hour response SLA** on weekdays and **3-hour SLA** during the 48-hour window before report submission.

---

## 3. Decision-Making Rule

- **Domain Autonomy:** Fast technical decisions within a member's primary area (e.g., chunk size experiments in `src/chunker.py` or prompt wording in `prompts/`) can be made autonomously by the area lead, provided they are backed by evaluation metrics on the test set.
- **Architectural & Cross-Cutting Decisions:** Changes affecting interfaces between modules (e.g., JSON output schema, tool signatures, model selection, or evaluation rubric definitions) require a **2-of-3 majority vote** after reviewing the tradeoffs.
- **Data-First Tiebreaker:** If two approaches are debated, we run both through the evaluation harness (`eval/`) and pick the one with higher measured accuracy/lower cost within 95% confidence intervals.

---

## 4. Non-Delivery & Blocker Escalation Protocol

1. **Early Warning (T-48h before deadline):** If a team member encounters a blocker or personal emergency that threatens their weekly deliverable, they must notify the team in the group chat **at least 48 hours before the submission deadline** and push their work-in-progress branch.
2. **Redistribution & Pair Recovery (T-36h before deadline):** The remaining two members redistribute the blocked task so the weekly report and `week-N` tag are never late (protecting the team from the $-25\%$ late penalty within 24 hours or $0$ points after 24 hours). The member who missed their task takes on an extra deliverable and leads the presentation the following week.
3. **Persistent Non-Delivery:** If a member fails to deliver their assigned work or fails to commit across two consecutive weeks without valid documented cause:
   - First occurrence: Written summary in the team channel with a concrete 72-hour catch-up commit plan.
   - Second occurrence: Formal escalation to the course instructor prior to the Week 4 / Week 7 Confidential Peer Assessments (`Appendix B`).

---

## 5. Code Hygiene & Rule Compliance Agreement

- **No Secrets in Git:** No API keys or `.env` files will ever be committed. Everyone uses `.env` locally.
- **Reproducible Numbers Only:** Every number in `reports/week-N.md` must come directly from an evaluation script output committed to the repo. Unmeasured metrics remain `null`.
- **Shared Oral Defense Readiness:** Before every weekly session, all 3 members review each other's commits so any member can explain any part of the system during the 5-minute Q&A.

---

## 6. Post-Course Intellectual Property & Code Continuation

- Subject to the university's intellectual property policy for student coursework, all code, synthetic datasets, evaluation harnesses, and documentation created for **TrailGuard AI** are **jointly owned equally** by Uygar Ege Kocakır, Dilara Yıldız, and Arda Agovic under the **MIT License**.
- If the team or a subset of members continues developing **TrailGuard AI** commercially or academically after AIC 390 concludes, any member who opts out retains full attribution and a perpetual, royalty-free right to showcase and fork the course repository in their portfolio, while continuing members share ongoing project equity equally.

---

**Signed & Agreed (Week 1):**
- *Uygar Ege Kocakır* — Agent and tools lead
- *Dilara Yıldız* — Data and retrieval lead
- *Arda Agovic* — Evaluation and safety lead
