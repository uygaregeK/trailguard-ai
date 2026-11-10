# TrailGuard AI — Online Store Support Assistant (UC1)

**Course:** AIC 390 Prompt Engineering  
**Use Case:** UC1 — Online Store Support Agent (Target Niche: *TrailRun TR*, Boutique Trail Running & Outdoor Gear Online Store)  
**Team Members & Roles:**
- **Uygar Ege Kocakır** — Agent and tools lead (`task_success`, `cost_per_task_usd`, `latency_p50_s`, `spend_week_usd`, `spend_total_usd`)
- **Dilara Yıldız** — Data and retrieval lead (`hit_at_5`, `mrr`, `unsupported_claims`)
- **Arda Agovic** — Evaluation and safety lead (`test_set_size`, `e2e_accuracy`, `abstention_correct`, `pass_k`, `injection_success`)

---

## Quick Setup & Run (Rule R19: $\le 10$ Commands)

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure your API key (Rule R13: .env is git-ignored)
cp .env.example .env
# Edit .env and paste your GEMINI_API_KEY from https://aistudio.google.com/app/apikey

# 4. Run Week 1 Baseline across temperatures 0, 0.7, and 1.2 (W1.5 & W1.6)
python3 eval/run_w1_baseline.py

# 5. Deterministically recompute scoreboard & token/cost metrics from saved outputs
python3 eval/run_w1_baseline.py --recompute
```

---

## Repository Structure

```text
├── README.md                      # Setup guide and deliverable index (W1.8)
├── requirements.txt               # Minimal dependencies
├── .env.example                   # Environment template (Rule R13)
├── docs/
│   ├── appendix_c_preferences.md  # Use case preference form (Appendix C)
│   ├── team_agreement.md          # W1.1: Roles, meetings, decision rules, IP
│   ├── use_case_brief.md          # W1.2: First customer, persona, 5 user stories, scope
│   ├── data_inventory.md          # W1.4: RAG corpus plan, DB schema, action API, untrusted inputs
│   └── cost_and_failures.md       # W1.6 & W1.7: Cost formula + 7 Module-1 predicted failures
├── data/
│   ├── w1_inputs.jsonl            # W1.3: 25 labeled realistic user inputs
│   └── w1_baseline_outputs.json   # W1.5: Saved outputs across T=0.0, 0.7, 1.2
├── prompts/
│   └── v1_baseline.txt            # W1.5: Baseline system prompt
├── src/
│   └── llm.py                     # Minimal Gemini API wrapper with token & cost tracking
├── eval/
│   └── run_w1_baseline.py         # W1.5 & W1.6: Reproducible evaluation script
└── reports/
    └── week-1.md                  # Weekly report following report_template.md (Rule R7)
```

---

## Week 1 Deliverables Index

| ID | Deliverable | Status | Evidence |
|---|---|---|---|
| **W1.1** | Team agreement | Done | [`docs/team_agreement.md`](docs/team_agreement.md) |
| **W1.2** | Use case brief & Product track | Done | [`docs/use_case_brief.md`](docs/use_case_brief.md) |
| **W1.3** | 25 realistic labeled user inputs | Done | [`data/w1_inputs.jsonl`](data/w1_inputs.jsonl) |
| **W1.4** | Data inventory | Done | [`docs/data_inventory.md`](docs/data_inventory.md) |
| **W1.5** | Baseline run at $T \in \{0, 0.7, 1.2\}$ | Done | [`eval/run_w1_baseline.py`](eval/run_w1_baseline.py), [`data/w1_baseline_outputs.json`](data/w1_baseline_outputs.json) |
| **W1.6** | Cost estimate & token formula | Done | [`docs/cost_and_failures.md`](docs/cost_and_failures.md), [`eval/run_w1_baseline.py`](eval/run_w1_baseline.py) |
| **W1.7** | Predicted failures ($\ge 5$, Module 1) | Done | [`docs/cost_and_failures.md`](docs/cost_and_failures.md) |
| **W1.8** | Repository with README, tagged `week-1` | Done | [`README.md`](README.md) |

