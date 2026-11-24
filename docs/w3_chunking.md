# W3.2 — Chunking Choice

**Owner:** Dilara Yıldız · **Code:** `src/chunker.py` · **Corpus:** `data/corpus/` (32 documents, about 6,000 words)

Reproduce the counts below with:

```bash
python3 src/chunker.py
```

## Two strategies

| Strategy | How it splits | Chunks | Words per chunk (mean, min–max) | Chunks that span more than one clause |
| :--- | :--- | :---: | :---: | :---: |
| **section** (main) | One chunk per numbered clause (`## §1 …`) | 172 | 40 (14–94) | 0 |
| **window** (baseline) | 120-word windows, 30-word overlap, ignoring structure | 71 | 103 (40–131) | 70 of 71 |

Every chunk keeps its document's `doc_id`, `title`, `category`, `access_level` and `version`, plus the clause IDs it covers (`sections`). Chunk IDs look like `POL-001#§1` (section) or `POL-001#w0` (window).

## Why section is our main choice

1. **Our documents are written as numbered clauses, one rule per clause.** A section chunk holds exactly one rule, so the model sees the whole rule and nothing it has to ignore.
2. **The agent cites clauses.** A chunk that is a clause can be cited directly (`[POL-001 §1]`); a window that covers §2–§5 cannot point to one rule.
3. **Windows cut rules in half.** 70 of 71 window chunks span two or more clauses, so a rule and its exception can land in different chunks (for example `POL-004` §2 "non-returnable" and §3 "unless defective on arrival").
4. **Each chunk makes sense alone.** The document title and the clause heading are added to the chunk text, so "§2 The rule" is never retrieved without saying which policy it belongs to.

## Known weakness of section chunks

Some clauses are short (14 words minimum), and a few answers need two neighbouring clauses (a rule and its example table). If that hurts answers, we can return the matched clause together with its neighbours, or retrieve more chunks (`k`).

## How we will test the choice (W3.7)

The retrieval test set (W3.5) marks the gold document and clause for each question. One ablation changes **only** the chunking strategy (section vs window) and reports hit@1, 3, 5, 10 and MRR for both. A hit counts when a retrieved chunk is from the gold document and covers the gold clause, so both strategies are scored the same way.

## First measurement (W2 test set, document level)

Until the W3.5 set is ready, we scored both strategies on the 23 questions of `data/w2_test_set.jsonl` that have a `must_cite` list. A hit here means a retrieved chunk comes from one of the `must_cite` documents (document level, not clause level). Reproduce with:

```bash
python eval/eval_retrieval.py --mode all --show-misses
```

| Retriever | Chunking | hit@1 | hit@3 | hit@5 | hit@10 | MRR |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| BM25 | **section** | **0.739** | **0.870** | **0.913** | 0.913 | **0.813** |
| BM25 | window | 0.696 | 0.826 | 0.870 | 0.957 | 0.769 |
| Hybrid + reranker | **section** | 0.696 | 0.783 | 0.913 | 0.957 | 0.770 |
| Hybrid + reranker | window | 0.652 | 0.870 | 0.957 | 1.000 | 0.768 |

With BM25, section chunks rank the right document higher (MRR 0.813 vs 0.769): a clause-sized chunk is short and about one rule, so its key terms carry more weight than in a 120-word window that mixes several rules. Windows catch more at k = 10, because each window covers more text. With the hybrid retriever and reranker, the two strategies are close (MRR 0.770 vs 0.768).

**Limits:** n = 23, so one question moves a hit rate by about 0.04, and most differences above are one or two questions. Only 1 of the 23 questions is in Turkish, and most were written with the documents' own words, which favours BM25. We keep section chunking as the main choice for the reasons above (whole rules, clause citations) and repeat this comparison on the W3.5 set, which adds Turkish and paraphrased questions and gold clauses.
