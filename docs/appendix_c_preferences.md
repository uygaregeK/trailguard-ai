# Appendix C — Use Case Preference Form

**Team Name:** TrailGuard AI  
**Course:** AIC 390 — Applied LLM Systems (Spring 2026)

---

## Team Members & Assigned Roles

| Name | Role | Primary Responsibilities | Owned Scoreboard Metrics |
| :--- | :--- | :--- | :--- |
| **Uygar Ege Kocakır** | **Agent & Tools Lead** | System prompts, structured output schemas, intent classifier, tool definitions, ReAct agent loop, MCP server, cost/latency optimization | `task_success`, `steps_per_task`, `cost_per_task_usd` |
| **Dilara Yıldız** | **Data & Retrieval Lead** | Policy/product corpus curation, document cleaning, chunking strategies, dense + BM25 hybrid retrieval, citation grounding, retrieval evaluation set | `hit_at_5`, `mrr`, `unsupported_claims` |
| **Arda Agovic** | **Evaluation & Safety Lead** | Golden/adversarial/OOD test sets, evaluation harness, bootstrap CIs & paired significance tests, LLM-as-judge calibration, red-teaming, sandbox & guardrails | `e2e_accuracy`, `abstention_correct`, `injection_success`, `pass_k`, `latency_p50_s`, `latency_p95_s` |

---

## Ranked Use Case Preferences

### 1st Choice (Selected): `UC1` — Online Store Support Agent (*TrailRun TR*)
- **Specific Niche:** Customer support and order operations assistant for **TrailRun TR**, a specialty online retailer selling trail running shoes, hydration vests, GPS watches, and alpine rain shells in Turkey.
- **Why this fits every course milestone:**
  - **RAG (`Week 3`):** Rich, multi-clause return policies (e.g., race-used vs unworn trail shoes, waterproof membrane warranty, electronics hygiene rules, size-exchange shipping fees).
  - **Structured Database Lookups (`Week 4`):** Relational order, shipment, and inventory tables (`orders`, `order_items`, `products`, `shipments`, `returns`) with exact alphanumeric IDs (`ORD-2026-8841`, `SKU-SAL-SPDC6-42`, `TRK-YURT-99201`).
  - **State-Changing Write Tool (`Week 4 & 5`):** `create_return_request(order_id, sku, reason, condition)` which mutates database state after checking eligibility rules and user confirmation.
  - **Adversarial & Untrusted Inputs (`Week 5`):** Customer return reason notes and imported product reviews containing indirect prompt injections attempting to bypass the 30-day window or force unauthorized refunds.

### 2nd Choice: `UC7` — IT Helpdesk & Onboarding Assistant
- **Specific Niche:** Internal IT support agent for a 250-person software company handling VPN troubleshooting, hardware provisioning, and access-request tickets (`create_it_ticket`).

### 3rd Choice: `UC2` — Clinic Front-Desk & Appointment Triage Assistant
- **Specific Niche:** Outpatient sports-medicine clinic assistant answering preparation instructions from clinic SOPs, checking doctor slot availability, and booking appointments (`book_appointment`) while abstaining from medical diagnosis.

