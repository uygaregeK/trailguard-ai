"""Retrieval metrics: hit@k and MRR (W3.3 / W3.5 / W3.7). Owner: Dilara.

For every question with a gold answer location, run the retriever and find
the rank of the first chunk that matches the gold:

  hit@k : share of questions with a matching chunk in the top k
  MRR   : mean of 1 / rank of the first matching chunk (0 if none in the top 10)

Two kinds of test set are read:

  * W3.5 retrieval set (Arda): rows with "gold_doc" and optional
    "gold_section" (for example "POL-004" and "§3"). With a gold_section, a
    chunk matches only if it is from gold_doc AND covers that clause, so
    section and window chunks are scored the same way.
  * W2 test set (default, until the W3.5 set exists): rows with "must_cite".
    A chunk matches if it comes from any must_cite document (document level).

    python3 eval/eval_retrieval.py                        # W2 set, both chunking strategies
    python3 eval/eval_retrieval.py --test-set data/w3_retrieval_test_set.jsonl
    python3 eval/eval_retrieval.py --out reports/w3_retrieval_bm25.json
"""

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from retriever import HybridRetriever

DEFAULT_TEST_SET = ROOT_DIR / "data" / "w2_test_set.jsonl"
CUTOFFS = (1, 3, 5, 10)
MAX_K = max(CUTOFFS)


def load_questions(path):
    """Return a list of {id, query, language, gold_docs, gold_section}."""
    questions = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("gold_doc"):
            gold_docs, gold_section = [row["gold_doc"]], row.get("gold_section")
        elif row.get("must_cite"):
            gold_docs, gold_section = list(row["must_cite"]), None
        else:
            continue  # no gold location (unanswerable or database-only question)
        questions.append({
            "id": row["id"],
            "query": row.get("query") or row["input"],
            "language": row.get("language", "en"),
            "gold_docs": gold_docs,
            "gold_section": gold_section,
        })
    return questions


def is_match(chunk, question):
    if chunk["doc_id"] not in question["gold_docs"]:
        return False
    return question["gold_section"] is None or question["gold_section"] in chunk["sections"]


def first_hit_rank(chunks, question):
    for rank, chunk in enumerate(chunks, start=1):
        if is_match(chunk, question):
            return rank
    return None


def summarize(ranks):
    n = len(ranks)
    if n == 0:
        return {"n": 0}
    summary = {"n": n}
    for k in CUTOFFS:
        summary[f"hit_at_{k}"] = round(sum(1 for r in ranks if r and r <= k) / n, 3)
    summary["mrr"] = round(sum(1 / r for r in ranks if r) / n, 3)
    return summary


def evaluate(retriever, questions):
    per_question, ranks = [], []
    for q in questions:
        chunks = retriever.search(q["query"], k=MAX_K)
        rank = first_hit_rank(chunks, q)
        ranks.append(rank)
        per_question.append({
            "id": q["id"],
            "language": q["language"],
            "gold": q["gold_docs"] if q["gold_section"] is None else f"{q['gold_docs'][0]}#{q['gold_section']}",
            "rank": rank,
            "top_3": [c["chunk_id"] for c in chunks[:3]],
        })
    by_language = {}
    for lang in sorted({q["language"] for q in questions}):
        by_language[lang] = summarize([r for r, q in zip(ranks, questions) if q["language"] == lang])
    return {"overall": summarize(ranks), "by_language": by_language, "per_question": per_question}


def main():
    parser = argparse.ArgumentParser(description="hit@k and MRR for the retriever")
    parser.add_argument("--test-set", type=Path, default=DEFAULT_TEST_SET)
    parser.add_argument("--strategy", choices=["section", "window", "both"], default="both")
    parser.add_argument("--out", type=Path, help="Write the full results as JSON")
    parser.add_argument("--show-misses", action="store_true", help="List questions with no hit in the top 5")
    args = parser.parse_args()

    questions = load_questions(args.test_set)
    strategies = ["section", "window"] if args.strategy == "both" else [args.strategy]
    mode = "bm25"  # becomes "hybrid" once the dense retriever and reranker are plugged in

    print(f"Test set: {args.test_set.name} | questions with a gold location: {len(questions)} | mode: {mode}\n")
    print(f"{'strategy':9s} {'n':>3s} " + " ".join(f"{'hit@' + str(k):>6s}" for k in CUTOFFS) + f" {'MRR':>6s}")

    results = {"test_set": args.test_set.name, "mode": mode, "strategies": {}}
    for strategy in strategies:
        result = evaluate(HybridRetriever(strategy=strategy), questions)
        results["strategies"][strategy] = result
        rows = [(strategy, result["overall"])] + [(f"  {lang}", s) for lang, s in result["by_language"].items()]
        for label, s in rows:
            print(f"{label:9s} {s['n']:3d} " + " ".join(f"{s[f'hit_at_{k}']:6.3f}" for k in CUTOFFS) + f" {s['mrr']:6.3f}")
        if args.show_misses:
            for p in result["per_question"]:
                if not p["rank"] or p["rank"] > 5:
                    print(f"    miss@5 {p['id']} ({p['language']}) gold={p['gold']} rank={p['rank']} top={p['top_3']}")
        print()

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
