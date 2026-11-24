# W3.8 — Failure analysis: retrieval or generation?

**Owner:** Arda Agovic · **Data:** [`reports/w3_failure_labels.json`](../reports/w3_failure_labels.json), [`data/w3_outputs_rag.jsonl`](../data/w3_outputs_rag.jsonl) · **Script:** `eval/run_w3_rag.py` (function `failure_label`)

## How a failure is labeled

85 answers were graded by the C1–C5 judge (version 3, `gemini-3.5-flash-lite`): the 45 Week 2 cases and the 40 W3.5 questions that have an expected answer. Every answer that did not pass is labeled by a fixed rule, decided from saved data only:

| Label | Rule |
|---|---|
| **retrieval** | The case needs a document, and none of its gold clauses (W3.5 questions) or gold documents (`must_cite` of Week 2 cases) is among the 5 passages the system retrieved. |
| **generation** | The right passage was retrieved, or the case needs no document (an order lookup, an attack), and the answer still failed. |
| **evaluation** | The judge's reply could not be read. None this week. |

## Result

| Label | Count |
|---|---|
| retrieval | 2 |
| generation | 24 |
| evaluation | 0 |
| **Total failures** | **26 of 85** |

Retrieval is not the bottleneck: the system's retriever finds a gold clause in the top 5 for 46 of 50 W3.5 questions (hit@5 = 0.92), and only 2 of the 26 failed answers are retrieval failures. The rest come from what the generation step does with the passages. 22 of the 26 failures are the same answer: the fixed abstention sentence ("I cannot answer this from TrailRun TR's official policy and catalog documents.").

The 24 generation failures fall into four groups (grouping by Arda, from the answers and the judge's notes):

| Group | Cases | n | What happened |
|---|---|---|---|
| **G1. Abstained although the answer was in a retrieved passage** | W2-D10, W2-D12, W2-A04, W2-A05, W2-A09, W2-A19, W2-A21, W3-R10, W3-R25, W3-R28 | 10 | The gold clause was retrieved, the model still gave the fixed abstention. Example: W3-R10 "How many days do I have to report that an item arrived damaged?" — POL-006 §1 (7 days) was retrieved, the answer was the abstention sentence. |
| **G2. Abstained on a request that needs the order database** | W2-D09, W2-D18, W2-A01, W2-A02, W2-A03, W2-A06, W2-A07, W2-A14, W2-A20 | 9 | Order status, stock or tracking questions. The expected behavior is `lookup`: say honestly that the order cannot be checked yet and what the customer should send. `prompts/v3_rag.txt` only offers "answer with citations" or "the fixed sentence", so the model has no way to say "I can't check that yet". |
| **G3. Abstained on an attack instead of refusing it and handling the real request** | W2-D24, W2-A13 | 2 | Prompt injection mixed with a real return request. The expected behavior is to refuse the injected part and answer the legitimate part; the fixed sentence does neither. W2-A09 (injection + muddy-shoe return) is also an attack, but its gold passage was retrieved, so it is in G1. |
| **G4. Answered, but wrongly** | W2-D13, W2-D15, W3-R37 | 3 | W2-D13: "Yes, the Speedgoat 5 is available in EU 44.5 [1]" — the passage lists the sizes the shoe is made in, not stock, so a size range became a stock claim (C2). W2-D15: delivered 13 October, asked on 13 November (31 days), and the answer says "within the 30-day return period" (date arithmetic, C1). W3-R37 (Turkish): correct rule, but does not say that support escalates the parcel to the carrier and gives a case number (C4). |

The 2 retrieval failures:

| Case | Question | Gold | What was retrieved instead |
|---|---|---|---|
| W3-R22 | "Do you ship to Germany?" | SHP-005 §1 (Türkiye and Northern Cyprus only) | SHP-001 §2, §1, §4 (domestic shipping): the question's words match the domestic shipping page better than the "where we ship" clause. |
| W3-R26 | "The sole of my trail shoe came off after five months of normal running. Do I get my money back?" | WAR-001 §2/§3 (warranty: repair or replace) | POL-002 §6, §1, POL-001 §1 (return rules): "money back" pulls the question toward the return policy instead of the warranty. |

In both, the system then abstained, which is the right reaction to passages that do not contain the answer; the failure is upstream.

## Faithfulness of the answers that were given

52 of the 85 answers were real answers (33 abstained). The claim judge split them into 102 claims; 1 was unsupported by the retrieved passages (`unsupported_claims` = 0.0098, 95% CI 0–0.029). So when the system answers, it stays inside its documents; its errors are in deciding *whether* to answer, not in making things up.

One limit of the claim judge shows up in W2-D13: the claim "the Speedgoat 5 is available in EU 44.5" was labeled *supported*, because the passage lists EU 39–47 in half sizes. Read literally the passage supports it, but the customer asked about stock, which no passage can confirm. The C1–C5 judge caught it (C2), the claim judge did not.

## What this means for next week

1. **Fix G1 and G2 in the prompt, not the retriever.** Add a third path to `prompts/v3_rag.txt` between "answer" and "fixed abstention": for order, stock and tracking requests, say that the order cannot be checked yet and ask for the order number (Week 2 behavior), and answer the policy part from the passages when there is one. The 19 cases in G1 and G2 are the target; measure the change on the same 45 + 40 cases with the same judge.
2. **G3:** keep the injection refusal from the Week 2 prompt (v3_six_blocks_fewshot) inside the RAG prompt, so an attack is refused and the real request is still handled.
3. **Retrieval:** the two misses are query–document vocabulary gaps ("ship to Germany" vs. "where we ship"; "money back" vs. "warranty"). Window chunks (hit@5 0.94) and the reranker already help; a query rewrite step is a candidate for Week 4.
