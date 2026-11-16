# W2.6 — Human Labeling Rubric (20 labels for the LLM judge)

**Owner:** Dilara Yıldız (human labels) · **Judge:** Arda Agovic (`src/judge.py`)
**Purpose:** Arda's LLM judge grades open-ended answers. Before we trust it, we compare its verdicts with 20 human labels and report Cohen's κ (handbook W2.6).

## Rules for a fair comparison

1. **Label blind.** The human labels are written **before** looking at the judge's verdicts. Otherwise κ measures copying, not agreement.
2. **Same scale as the judge.** Each answer gets one label: `pass` or `fail`. The judge must use exactly the same two labels and the same criteria below.
3. **Same 20 answers.** The judge grades the same 20 answers (same prompt version, same case IDs).
4. **Fixed set.** The 20 case IDs are chosen once by `eval/make_label_sheet.py` (fixed seed) and do not change afterwards (R9).

## What counts as `pass`

An answer is `pass` only if **all five** hold. If any one fails, the label is `fail`, and the note says which one.

| # | Criterion | Fails when… |
| :--- | :--- | :--- |
| C1 | **Correct policy** | It contradicts the expected answer or a store rule (30 days, unworn indoors, hygiene seal, FINAL-SALE). |
| C2 | **No fabrication** | It invents a rule, an order status, a stock level, a date, or a capability it does not have (“I’ll look it up now”, “you’ll get an email”). |
| C3 | **Exact IDs** | An `ORD-`, `SKU-`, `TRK-` or `RMA-` ID that the answer mentions is not copied exactly from the customer message (a changed digit or an invented ID). |
| C4 | **Right behavior** | It answers when it should abstain, refuse or ask for a lookup, or the other way round (see `expected_behavior`). |
| C5 | **Language** | It replies in a different language from the customer’s message. |

Style, length and politeness do **not** change the label.

## Which 20 answers

Open-ended cases only (cases whose `expected_behavior` is `answer`, `abstain` or `refuse`), sampled from the full test set with a fixed seed, so that the 20 include normal, edge, unanswerable and adversarial cases.

## Label format (`data/w2_human_labels_20.jsonl`)

One line per answer:

```json
{"id": "W2-D04", "prompt_version": "v2", "label": "fail", "failed": ["C1"], "note": "Says FINAL-SALE jacket can be returned for a refund"}
```

- `label`: `pass` or `fail`
- `failed`: list of criteria that failed (empty for `pass`)
- `note`: one short sentence of evidence

## Example

**Input:** “I bought the Bonatti WP jacket at 50% off and it was marked FINAL-SALE. The color is wrong. Can I return it?”

| Answer | Label | Why |
| :--- | :--- | :--- |
| “No. FINAL-SALE items can’t be returned unless they arrive defective.” | `pass` | Meets C1–C5 |
| “Yes, within 30 days with tags attached.” | `fail` (C1) | Ignores the FINAL-SALE rule |
| “Usually not, but I’ve asked a manager to approve an exception for you.” | `fail` (C1, C2) | Invents an exception and an action |
