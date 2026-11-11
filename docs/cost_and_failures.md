# W1.6 & W1.7 — Token & Cost Math + Predicted Failure Analysis

**Project:** TrailGuard AI (`UC1` — Online Store Support Agent)  
**Models Used Across 75 Live Calls (`W1.5`):** `gemini-2.5-flash` (35 calls, with `thinking_budget=0`) and `gemini-3.1-flash-lite` (40 calls, after hitting the Free Tier `GenerateRequestsPerDayPerProjectPerModel-FreeTier` daily cap of 20 requests/run on `gemini-2.5-flash`).

---

## 1. Token & Cost Math (`W1.6`)

### 1.1 Cost Formula (Module 1, Slide 49)
For an LLM request with $n_{\text{in}}$ input tokens, $n_{\text{out}}$ visible output tokens, and $n_{\text{think}}$ thinking tokens, where the provider charges $c_{\text{in}}$ USD per $10^6$ input tokens and $c_{\text{out}}$ USD per $10^6$ output tokens, the cost of a single request is:

$$\text{cost}_{\text{request}} = \frac{n_{\text{in}} \cdot c_{\text{in}} + (n_{\text{out}} + n_{\text{think}}) \cdot c_{\text{out}}}{10^6}$$

And the projected cost per $1,000$ requests is:

$$\text{cost}_{1000} = 1000 \times \text{cost}_{\text{request}} = \frac{n_{\text{in}} \cdot c_{\text{in}} + (n_{\text{out}} + n_{\text{think}}) \cdot c_{\text{out}}}{10^3}$$

### 1.2 Official Google AI Studio Paid-Tier Pricing Parameters
- **Free Tier (Google AI Studio):** $\$0.00$ actual billed spend up to per-model quota thresholds (on our project key, `gemini-2.5-flash` enforced `GenerateRequestsPerDayPerProjectPerModel-FreeTier = 20`, after which `src/llm.py` routed remaining calls to `gemini-3.1-flash-lite`; 32 calls from the initial run — all 13 `gemini-3.5-flash` fallback calls plus 19 `W1-003`–`W1-011` calls — were re-run with the identical baseline prompt `prompts/v1_baseline.txt` due to quota limits to eliminate `3.5-flash` thinking tokens and maximize `gemini-2.5-flash` coverage).
- **Official Paid-Tier Unit Prices (used to calculate production unit economics and scoreboard `cost_per_task_usd` / `spend_week_usd`):**
  - **`gemini-2.5-flash` (35/75 calls):** Input $c_{\text{in}} = \$0.30 / 10^6$ tokens; Output $c_{\text{out}} = \$2.50 / 10^6$ tokens (`thinking_budget=0` applied to all `gemini-2.5-flash` calls, verified $n_{\text{think}} = 0$).
  - **`gemini-3.1-flash-lite` (40/75 calls):** Input $c_{\text{in}} = \$0.25 / 10^6$ tokens; Output $c_{\text{out}} = \$1.50 / 10^6$ tokens (non-thinking Flash-Lite model, verified $n_{\text{think}} = 0$).
  - *(Reference rates also configured in `src/llm.py`: `gemini-2.5-flash-lite` at $\$0.10 / \$0.40$ per $10^6$ tokens; `gemini-3.5-flash` at $\$1.50 / \$9.00$ per $10^6$ tokens).*

### 1.3 Week 1 Measured Baseline Token & Cost Breakdown (`data/w1_inputs.jsonl`, `n = 25`)
Reproducibly computed via `python3 eval/run_w1_baseline.py --recompute` (`reports/scoreboard_w1.json`):
- **Mean Input Tokens ($\bar{n}_{\text{in}}$):** $528.16\text{ tokens/request}$ across all temperatures ($T \in \{0.0, 0.7, 1.2\}$).
- **Mean Output Tokens ($\bar{n}_{\text{out}}$):** $126.00\text{ tokens}$ at $T=0.0$, $132.56\text{ tokens}$ at $T=0.7$, and $131.64\text{ tokens}$ at $T=1.2$ (with $n_{\text{think}} = 0$ across all 75 calls).
- **Measured Mean Cost by Temperature:**
  - **At $T=0.0$ (11 `gemini-2.5-flash`, 14 `gemini-3.1-flash-lite` calls):**
    - Mean Single-Request Cost ($\text{cost}_{\text{request}}$): **$\$0.000362\text{ USD/task}$**
    - Cost per 1,000 Requests ($\text{cost}_{1000}$): **$\$0.3618\text{ USD per 1,000 requests}$** (total spend across 25 calls at $T=0.0$: $\$0.009044$).
  - **At $T=0.7$ (11 `gemini-2.5-flash`, 14 `gemini-3.1-flash-lite` calls):** $\$0.000378\text{ USD/task}$ ($\$0.3779 / 1\text{k}$ requests; total $\$0.009448$).
  - **At $T=1.2$ (13 `gemini-2.5-flash`, 12 `gemini-3.1-flash-lite` calls):** $\$0.000382\text{ USD/task}$ ($\$0.3820 / 1\text{k}$ requests; total $\$0.009551$).
  - **Total Week 1 Spend Across All 75 Calls (`spend_week_usd`):** **$\$0.0280\text{ USD}$**.
- **Pure Single-Model Reference Comparison (at $\bar{n}_{\text{in}} = 528.16, \bar{n}_{\text{out}} = 126.00$):**
  - If run 100% on `gemini-2.5-flash` ($\$0.30 / \$2.50$): $\frac{528.16 \times 0.30 + 126.00 \times 2.50}{10^6} = \$0.000473/\text{task}$ ($\$0.4734 / 1\text{k}$ requests).
  - If run 100% on `gemini-3.1-flash-lite` ($\$0.25 / \$1.50$): $\frac{528.16 \times 0.25 + 126.00 \times 1.50}{10^6} = \$0.000321/\text{task}$ ($\$0.3210 / 1\text{k}$ requests).

### 1.4 Projection to Week 4 Multi-Step Agent + RAG Architecture
When we add Hybrid RAG (5 retrieved chunks $\approx 1,250\text{ tokens}$) and a 3-step agent loop in Weeks 3–4 (accounting for Module 4 context growth across steps, $\bar{n}_{\text{in, agent}} \approx 4,800\text{ tokens}$, $\bar{n}_{\text{out, agent}} \approx 540\text{ tokens}$):
- On `gemini-2.5-flash` ($\$0.30 / \$2.50$): $\frac{4800 \times 0.30 + 540 \times 2.50}{10^6} = \mathbf{\$0.00279\text{ USD/task}}$ (**$\$2.79\text{ per 1,000 tasks}$**).
- On `gemini-3.1-flash-lite` ($\$0.25 / \$1.50$): $\frac{4800 \times 0.25 + 540 \times 1.50}{10^6} = \mathbf{\$0.00201\text{ USD/task}}$ (**$\$2.01\text{ per 1,000 tasks}$**).

---

## 2. Seven Predicted Failure Modes Linked to Module 1 Concepts (`W1.7`)

Below are **7 specific failure modes** we predict for `UC1`, each linked to a core **Module 1** mechanism:

### Failure 1: Confident Fabrication of Store Policy Clauses & Order Status
- **Module 1 Concept:** *Next-token probability maximization & lack of built-in truth/epistemic state (Hallucination).*
- **Mechanism:** An LLM trained on cross-entropy loss $L = -\ln P(t_{\text{true}} \mid \text{context})$ models *plausible text continuation*, not verified truth. When a user asks a policy detail not explicitly covered in the system prompt (such as who pays courier fees on a hydration vest size exchange in `W1-003`), the model generates plausible-sounding e-commerce boilerplate claiming exchange shipping is free rather than abstaining.
- **Mitigation (Weeks 3–4):** Connect hybrid RAG with numbered citations (`W3.3`, `W3.4`) and a fixed abstention response when retrieved documents do not contain the answer.

### Failure 2: Subword Tokenization & High-Temperature Dropping of Alphanumeric SKUs
- **Module 1 Concept:** *Byte-Pair Encoding (BPE) subword tokenization boundaries & sampling entropy.*
- **Mechanism:** BPE tokenizers split rare alphanumeric identifiers like `SKU-LKI-ULTZ-120`, `SKU-SAL-SPDC6-42`, or `ORD-2026-8841` into 6–9 arbitrary subword tokens. Under higher temperature sampling ($T=1.2$), lower-probability subword transitions cause the model to paraphrase an exact SKU into a generic noun phrase (e.g., replacing `SKU-LKI-ULTZ-120` with `"the defective pole"` in `W1-011`) or corrupt characters during tool calls.
- **Mitigation (Weeks 2–4):** Lock $T = 0.0$ for entity extraction (`W2.1`), use BM25 lexical matching in hybrid retrieval (`W3.3`), and validate tool arguments against input substrings (`W4.1`).

### Failure 3: Knowledge Cutoff & Private Store Blindness
- **Module 1 Concept:** *Static pre-training corpus & knowledge cutoff.*
- **Mechanism:** Pre-training freezes the model's parametric weights $\theta$ at its cutoff date and only includes public web text. The model has zero parametric knowledge of *TrailRun TR*'s private 2026 inventory, live stock counts, or specific return clauses (`POL-001`–`SOP-004`).
- **Mitigation (Weeks 3–4):** Inject dynamic non-parametric knowledge at inference time via Hybrid RAG (`W3`) and live database query tools (`W4.1`).

### Failure 4: Statelessness & False Claims of Tool Capability Without Connected Tools
- **Module 1 Concept:** *Statelessness of LLM inference calls & lack of environment awareness.*
- **Mechanism:** Each API call to `generate_content` is a stateless text transformation with no intrinsic awareness of whether external tools exist unless constrained. When asked to look up an order or initiate a return (`W1-010`, `W1-024`), a stateless model can offer to *"look it up if you grant me permission"* even when no database tool is wired to the runtime.
- **Mitigation (Week 4):** Connect explicit typed tools (`search_policy_docs`, `lookup_order`, `create_return_request`) inside a bounded agent loop (`W4.1`, `W4.2`).

### Failure 5: "No Going Back" Commitment to Premature Refund Approvals
- **Module 1 Concept:** *Autoregressive left-to-right generation ("No Going Back").*
- **Mechanism:** Because tokens are sampled sequentially $t_1, t_2, \dots, t_k$ and appended to the context, if the model begins its reply with an accommodating opening before checking whether an order is within the 30-day window or marked `FINAL-SALE`, attention weights condition subsequent tokens to justify that initial commitment.
- **Mitigation (Weeks 2 & 4):** Enforce structured classification (`W2.1`) and tool verification before generating customer-facing responses.

### Failure 6: Sycophancy Under Aggressive Customer Authority Claims
- **Module 1 Concept:** *RLHF Sycophancy (reward modeling favoring agreeable responses).*
- **Mechanism:** Preference-tuned models are trained to be helpful and accommodating. When an assertive user claims that store manager "Mert Demir" verbally authorized a 60-day return on a `FINAL-SALE` jacket (`W1-023`), an unguarded model risks validating the user's premise unless strictly constrained by policy rules and human-escalation boundaries.
- **Mitigation (Weeks 2 & 5):** Explicit anti-sycophancy constraints in the 6-block main prompt (`W2.2`) and a deterministic confirmation/eligibility gate on write actions (`W5.4`).

### Failure 7: High-Temperature Sampling Entropy Degrading Determinism
- **Module 1 Concept:** *Temperature scaling of logits ($z_i / T$) before softmax.*
- **Mechanism:** Dividing logits by $T = 1.2$ flattens the probability distribution $P(t_i) = \frac{\exp(z_i/T)}{\sum_j \exp(z_j/T)}$, shifting probability mass into the tail of lower-probability tokens. In our Week 1 experiment (`W1.5`), increasing $T$ from $0.0$ to $1.2$ reduced lexical Jaccard similarity against $T=0.0$ from $0.5870$ ($T=0.7$) to $0.4733$ ($T=1.2$) and dropped exact ID preservation from $100.0\%$ ($15/15$) to $93.3\%$ ($14/15$).
- **Mitigation (Weeks 2–6):** Lock $T = 0.0$ for classification (`W2.1`), tool calling (`W4.1`), and policy enforcement.
