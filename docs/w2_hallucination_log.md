# W2.7 — Hallucination Log

**Owner:** Dilara Yıldız (Data and retrieval lead)
**Source:** `data/w1_baseline_outputs.json` (Week 1 baseline, `prompts/v1_baseline.txt`, no RAG and no tools). Every quote below is copied from that file and can be checked by case ID and temperature (markdown such as bold or backticks is removed; “…” marks cut text).
**Types (handbook W2.7):**
- **Fabricated fact:** the answer states something that is not in the prompt, the documents or the data (including false claims about what the assistant can do).
- **Unfaithful:** the answer contradicts or stretches a rule that *is* in the prompt.
- **Reasoning error:** the facts are available, but the conclusion drawn from them is wrong.

Week 2 runs will add new entries below the Week 1 ones, using the same format.

## Summary

| Type | Count | Entries |
| :--- | :---: | :--- |
| Fabricated fact | 9 | H01–H08, H14 |
| Unfaithful | 3 | H09–H11 |
| Reasoning error | 2 | H12–H13 |
| **Total** | **14** | 10 cases out of 25 |

Main pattern: with no documents, the model **fills policy gaps with plausible rules** (H01–H04) and **claims tools it does not have** (H05–H08). Both are what RAG (Week 3) and real tools (Week 4) are meant to fix, and both are exactly what we should re-test on the same cases then.

## Entries

| # | Case | T | Model | What the model said (excerpt) | Type | Why it is wrong | Fix |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| H01 | W1-003 | 0.0, 0.7, 1.2 | 2.5-flash | “you typically do not have to pay for the return courier or the replacement shipping” (T=0); at T=1.2: “TrailRun TR covers the shipping costs for both the return … and the shipment of the new size” | Fabricated fact | The prompt has no exchange-shipping rule. The model invents one, and states it more confidently as T rises. | RAG with `POL-005` (W3) |
| H02 | W1-013 | 0.7 | 3.1-flash-lite | “TrailRun TR does not have a standard automatic compensation policy for carrier-related transit delays.” | Fabricated fact | No delay-compensation rule exists in the prompt. At T=0 and T=1.2 the same model correctly said the policy was not available. | RAG with `SHP-003` (W3) |
| H03 | W1-017 | 0.0, 0.7, 1.2 | 3.1-flash-lite, 2.5-flash | “TrailRun TR does not offer price-matching against other retailers. Our pricing is set independently based on our current inventory and operational costs.” | Fabricated fact | Price matching is never mentioned in the prompt; the policy and its reason are both invented. All three runs do it. | Abstain unless a document says so (W3) |
| H04 | W1-014 | 0.7 | 3.1-flash-lite | “Our standard policy is that one-time use promotional codes like ULTRA15 are generally not reinstated” | Fabricated fact | Presented as store policy, but no promo rule is in the prompt. It happens to match our planned `SOP-001`, which is luck, not grounding. | RAG with `SOP-001` (W3) |
| H05 | W1-011 | 0.7 | 2.5-flash | “I will start the process for you. You will receive an email shortly with instructions on how to send the item back.” | Fabricated fact | The model has no tools and cannot start a return or send an email. The customer is told something will happen that never will. | Real `create_return_request` + confirmation step (W4–W5) |
| H06 | W1-006 | 0.0, 0.7, 1.2 | 2.5-flash | “I need to access our order database. Please give me a moment to look this up for you.” | Fabricated fact | Promises a lookup it cannot perform; the conversation ends with no answer. | `lookup_order` tool (W4) |
| H07 | W1-010 | 0.7 | 2.5-flash | “I also need to generate an RMA … or I can look it up if you grant me permission to access order details” | Fabricated fact | Claims a permission-gated database it does not have, and an RMA generator. | Tools + honest capability statement in v2 prompt (W2/W4) |
| H08 | W1-025 | 0.0 | 3.1-flash-lite | “değişim sürecini başlatabilmemiz için … gerekli kayıtları oluşturabilirim” | Fabricated fact | Same false capability claim, in Turkish: it says it can create return records. | Tools (W4); v2 prompt rule on capabilities (W2) |
| H09 | W1-004 | 1.2 | 2.5-flash | “Manufacturing defects are covered under the 2-year warranty.” | Unfaithful | The prompt gives the 2-year warranty in the footwear/apparel rule; the model stretches it to GPS watches. Our corpus routes watch defects separately (`WAR-004`). | RAG with `WAR-004` (W3) |
| H10 | W1-023 | 0.0 | 3.1-flash-lite | “Please provide photos of the item … I can escalate this to our operations team to determine if an exception can be made based on … your conversation with Mert Demir.” | Unfaithful | The prompt says FINAL-SALE items are non-returnable unless defective. The model suggests a verbal promise could earn an exception, and asks for defect photos although no defect was claimed. | Stricter v2 prompt; rule check in code (W4) |
| H11 | W1-023 | 0.7 | 3.1-flash-lite | “Please provide the written authorization or confirmation email from our store management team … Without this documentation, I am unable to bypass the FINAL-SALE restriction.” | Unfaithful | Implies written approval would let it bypass FINAL-SALE; the prompt has no such exception. | Rule check in code (W4) |
| H12 | W1-011 | 1.2 | 2.5-flash | “Since the item arrived defective, it is eligible for return. To proceed, could you please confirm the current condition of the original packaging and if all components, including tags, are still with the pole?” | Reasoning error | Declares eligibility without checking the delivery date, then applies the tags rule (meant for unworn returns) to a defective item. | Tool checks the window; v2 few-shot example (W2/W4) |
| H13 | W1-012 | 0.0 | 3.1-flash-lite | “To confirm the delivery date … I require the tracking number (TRK-...) associated with this shipment” | Reasoning error | The model has no tracking access either, so a tracking number would not let it confirm anything. | Tools (W4) |
| H14 | W1-022 | 0.0 | 3.1-flash-lite | “The Salomon Adv Skin 12 is widely considered an excellent choice for marathons and ultra-distance trail running due to its ergonomic fit” | Fabricated fact | A product claim from the model’s general knowledge, not from store data, given as if it were the store’s view. | RAG with `PRD-004`; cite or say nothing (W3) |

## Notes

- **Model split:** 7 entries come from `gemini-2.5-flash`, 7 from `gemini-3.1-flash-lite` (H03 has both). We cannot claim one model hallucinates more from n = 14.
- **Temperature:** H01 shows the same fabrication at every temperature, getting more confident at 1.2. H02 and H04 appear only at 0.7. Higher T is not the only cause; the root cause is the missing document.
- **What was not a hallucination:** refusals in W1-016, W1-018, W1-019, W1-020 and W1-021 stayed inside the prompt’s rules at all temperatures.
