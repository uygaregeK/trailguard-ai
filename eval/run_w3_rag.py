"""Week 3 evaluation harness (W3.5–W3.8). Owner: Arda.

One command measures the team's retrieval and RAG system and writes the scoreboard:

    python3 eval/run_w3_rag.py

It uses the team's code as it is:
  src/retriever.py   (Dilara, W3.3)  BM25, multilingual dense, RRF, cross-encoder reranker
  eval/eval_retrieval.py (Dilara)    hit@k / MRR matching rule
  src/rag_chain.py   (Uygar, W3.4)   cited answers with [1]..[N], fixed abstention

Stages (each saves its rows; an interrupted run continues where it stopped):
  1. retrieval  W3.5 + W3.7  50 questions with gold clauses (data/w3_retrieval_test.jsonl)
                             × 4 modes (bm25, dense, hybrid, hybrid_rerank) × 2 chunkings.
                             Local models only: no API calls. Public chunks only, as the
                             customer-facing system searches.
                             The system configuration for stage 2 is the section-chunk mode
                             with the highest MRR (ties: hit@5), as the team agreed to pick
                             the default with this set.
  2. answers    W3.4 + W3.6  answer_with_rag on the 45 Week 2 cases and the 40 W3.5
                             questions that have an expected answer. Each answer gets the
                             C1–C5 judge (version 3) and, unless it abstained, the
                             claim-by-claim faithfulness judge.
  3. baseline                the saved Week 2 v3 answers (no documents) re-graded with the
                             same judge version 3, so "with RAG" and "without RAG" use one judge.
  4. report     W3.8         failure labels, the blind label sheet for the faithfulness
                             check, reports/scoreboard_w3.json.

    python3 eval/run_w3_rag.py --recompute    # no model or API calls: rebuild from saved rows
    python3 eval/run_w3_rag.py --limit 3      # smoke test on 3 cases per set; no scoreboard

Judge model: gemini-3.1-flash-lite (the Week 2 judge) unless TRAILGUARD_MODEL is set.
"""

import argparse
import hashlib
import json
import os
import random
import signal
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "eval"))

import src.llm as llm  # noqa: E402
from eval_retrieval import evaluate, load_questions  # noqa: E402  (Dilara)
from src.faithfulness import FAITH_VERSION, check_faithfulness  # noqa: E402
from src.judge import JUDGE_VERSION_W3, judge_answer_v3  # noqa: E402
from stats import accuracy_ci95, mcnemar, percentile  # noqa: E402

SCRIPT = "eval/run_w3_rag.py"
DATA = ROOT_DIR / "data"
REPORTS = ROOT_DIR / "reports"

RETRIEVAL_TEST = DATA / "w3_retrieval_test.jsonl"
W2_TEST = DATA / "w2_test_set.jsonl"
W2_BASELINE_OUTPUTS = DATA / "w2_outputs_v3_six_blocks_fewshot.jsonl"

RETRIEVAL_FILE = REPORTS / "w3_retrieval.json"
ANSWER_ROWS = DATA / "w3_outputs_rag.jsonl"
BASELINE_ROWS = DATA / "w3_baseline_v3_rejudged.jsonl"
LABEL_SHEET = DATA / "w3_claim_label_sheet.jsonl"
HUMAN_LABELS = DATA / "w3_claim_labels_human.jsonl"
KAPPA_FILE = REPORTS / "w3_faithfulness_kappa.json"
FAILURES_FILE = REPORTS / "w3_failure_labels.json"
SCOREBOARD = REPORTS / "scoreboard_w3.json"

MODES = ["bm25", "dense", "hybrid", "hybrid_rerank"]
STRATEGIES = ["section", "window"]
TOP_K = 5
PUBLIC = ("public",)
JUDGE_MODEL_W3 = os.getenv("TRAILGUARD_MODEL", "gemini-3.1-flash-lite")
W2_ANSWER_MODEL = "gemini-3.1-flash-lite"
LABEL_SAMPLE_SIZE = 30
LABEL_SEED = 390
SPEND_BEFORE_W3 = 0.1777          # spend_total_usd in reports/scoreboard_w2.json

CALL_TIMEOUT_S = 180
CALL_ATTEMPTS = 3

# src/llm.py lists gemini-3.5-flash-lite at $0.25 / $1.50; the published price is
# $0.30 input / $2.50 output per 1M tokens (ai.google.dev/gemini-api/docs/pricing).
# rag_chain may fall back to this model, so the correct price is used here.
llm.MODEL_PRICING_PER_1M_USD["gemini-3.5-flash-lite"] = {"input": 0.30, "output": 2.50}


def offline():
    return os.getenv("TRAILGUARD_OFFLINE") == "1"


# ---------------------------------------------------------------- files

def load_jsonl(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def save_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------- API calls

class CallTimeout(RuntimeError):
    pass


def _on_alarm(signum, frame):
    raise CallTimeout(f"no reply from the API within {CALL_TIMEOUT_S} seconds")


def stop_run(reason):
    print(f"\nStopped: {reason}")
    print("Progress is saved. Run the same command again to continue.")
    sys.exit(2)


def call_or_stop(function, *args, **kwargs):
    """One step that may call the API. A stalled call is retried; a refused call
    (overload, rate limit, missing key) stops the run cleanly, with progress saved."""
    signal.signal(signal.SIGALRM, _on_alarm)
    for attempt in range(1, CALL_ATTEMPTS + 1):
        signal.setitimer(signal.ITIMER_REAL, CALL_TIMEOUT_S, CALL_TIMEOUT_S)
        try:
            return function(*args, **kwargs)
        except CallTimeout as err:
            print(f"  {err} (attempt {attempt}/{CALL_ATTEMPTS})")
        except (RuntimeError, KeyError) as err:
            stop_run(err)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
    stop_run(f"the API did not reply in {CALL_ATTEMPTS} attempts")


# ---------------------------------------------------------------- models (loaded once)

_MODELS = {}


def local_models():
    """Dilara's multilingual embedding model and reranker, loaded once.
    Offline: small deterministic stand-ins with the same interface (code test only)."""
    if "dense" not in _MODELS:
        from retriever import DenseRetriever, Reranker
        if offline():
            from offline_standins import FakeCrossEncoder, FakeSentenceModel
            _MODELS["dense"] = DenseRetriever(model_name="offline-hash", model=FakeSentenceModel())
            _MODELS["reranker"] = Reranker(model_name="offline-overlap", model=FakeCrossEncoder())
        else:
            print("  loading the embedding model and the reranker (first time: download about 0.5 GB)")
            _MODELS["dense"] = DenseRetriever()
            _MODELS["reranker"] = Reranker()
    return _MODELS["dense"], _MODELS["reranker"]


class PublicOnly:
    """Wraps a HybridRetriever so every search is limited to public chunks, as the
    customer-facing system searches (eval_retrieval.py searches internal chunks too)."""

    def __init__(self, retriever):
        self.retriever = retriever

    def search(self, query, k=5, allowed_access=PUBLIC):
        return self.retriever.search(query, k=k, allowed_access=PUBLIC)


def build_retriever(mode, strategy):
    from retriever import HybridRetriever
    dense, reranker = local_models() if mode != "bm25" else (None, None)
    return HybridRetriever.from_mode(mode, strategy=strategy, dense=dense, reranker=reranker)


# ---------------------------------------------------------------- stage 1: retrieval

def run_retrieval(args):
    if args.recompute or (RETRIEVAL_FILE.exists() and not args.limit):
        if RETRIEVAL_FILE.exists():
            out = json.loads(RETRIEVAL_FILE.read_text(encoding="utf-8"))
            add_statistics(out)          # recomputed from the saved per-question ranks
            RETRIEVAL_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return out
        return None
    questions = load_questions(RETRIEVAL_TEST)
    if args.limit:
        questions = questions[:args.limit]
    styles = {json.loads(l)["id"]: json.loads(l).get("style") for l in RETRIEVAL_TEST.read_text(encoding="utf-8").splitlines() if l.strip()}
    out = {"test_set": RETRIEVAL_TEST.name, "n_questions": len(questions), "access_levels": list(PUBLIC), "runs": {}}
    for mode in MODES:
        for strategy in STRATEGIES:
            t0 = time.perf_counter()
            res = evaluate(PublicOnly(build_retriever(mode, strategy)), questions)
            res["seconds"] = round(time.perf_counter() - t0, 2)
            for p in res["per_question"]:
                p["style"] = styles.get(p["id"])
            out["runs"][f"{mode}/{strategy}"] = res
            o = res["overall"]
            print(f"  {mode:14s} {strategy:8s} n={o['n']}  hit@1 {o['hit_at_1']:.3f}  hit@5 {o['hit_at_5']:.3f}  MRR {o['mrr']:.3f}")
    if not args.limit:
        dense, reranker = local_models()
        out["embedding_model"], out["reranker_model"] = dense.model_name, reranker.model_name
        add_statistics(out)
        RETRIEVAL_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def hit(p, k=5):
    return bool(p["rank"] and p["rank"] <= k)


def add_statistics(out):
    """95% intervals, hit@5 by query style, McNemar between modes, and the system choice."""
    for name, res in out["runs"].items():
        pq = res["per_question"]
        n = len(pq)
        k5 = sum(hit(p) for p in pq)
        _, lo, hi = accuracy_ci95(k5, n)
        rr = [1 / p["rank"] if p["rank"] else 0.0 for p in pq]
        se = statistics.stdev(rr) / n ** 0.5 if n > 1 else 0.0
        res["ci95"] = {"hit_at_5": [round(lo, 4), round(hi, 4)],
                       "mrr": [round(max(0.0, statistics.mean(rr) - 1.96 * se), 4), round(min(1.0, statistics.mean(rr) + 1.96 * se), 4)]}
        by_style = defaultdict(list)
        for p in pq:
            by_style[p["style"]].append(hit(p))
        res["hit_at_5_by_style"] = {s: {"value": round(sum(v) / len(v), 3), "n": len(v)} for s, v in sorted(by_style.items())}

    def paired(a, b):
        A = {p["id"]: hit(p) for p in out["runs"][a]["per_question"]}
        B = {p["id"]: hit(p) for p in out["runs"][b]["per_question"]}
        bb = sum(1 for i in A if A[i] and not B[i])
        cc = sum(1 for i in A if not A[i] and B[i])
        return {**mcnemar(bb, cc), "system_a": a, "system_b": b, "metric": "hit_at_5", "n": len(A),
                "a_hit_b_miss": bb, "a_miss_b_hit": cc}

    out["mcnemar_hit_at_5"] = [
        paired("hybrid_rerank/section", "bm25/section"),
        paired("hybrid/section", "bm25/section"),
        paired("dense/section", "bm25/section"),
        paired("hybrid_rerank/section", "hybrid/section"),
        paired("hybrid_rerank/section", "hybrid_rerank/window"),
        paired("bm25/section", "bm25/window"),
    ]
    section = {m: out["runs"][f"{m}/section"]["overall"] for m in MODES}
    best = max(MODES, key=lambda m: (section[m]["mrr"], section[m]["hit_at_5"]))
    out["system_choice"] = {"mode": best, "strategy": "section",
                            "rule": "section-chunk mode with the highest MRR on this set (ties: hit@5)"}


# ---------------------------------------------------------------- test cases

def load_cases(limit=None):
    w2 = [{
        "id": c["id"], "set": "w2", "input": c["input"], "type": c["type"], "language": c.get("language", "en"),
        "expected_behavior": c["expected_behavior"], "expected_answer": c["expected_answer"],
        "answerable_from": c.get("answerable_from"), "gold_docs": c.get("must_cite") or [], "gold_passages": [],
    } for c in load_jsonl(W2_TEST)]
    w3 = [{
        "id": c["id"], "set": "w3", "input": c["query"], "type": "normal", "language": c["language"],
        "style": c.get("style"), "expected_behavior": c["expected_behavior"], "expected_answer": c["expected_answer"],
        "answerable_from": "corpus", "gold_docs": sorted({g.split("#")[0] for g in c["gold_passages"]}),
        "gold_passages": c["gold_passages"],
    } for c in load_jsonl(RETRIEVAL_TEST) if c.get("expected_answer")]
    if limit:
        w2, w3 = w2[:limit], w3[:limit]
    return w2, w3


# ---------------------------------------------------------------- stage 2: answers

def passage_view(passages):
    """The public passages as the answer model saw them: numbered [1]..[N] in order."""
    public = [p for p in passages if p.get("access_level", "public") != "internal"]
    return [{"n": i, "chunk_id": p["chunk_id"], "doc_id": p["doc_id"], "sections": p["sections"],
             "label": f"{i}] [{p['doc_id']} {', '.join(p['sections'])}", "text": p["text"]}
            for i, p in enumerate(public, start=1)]


def rag_answer(system, query):
    from src.rag_chain import answer_with_rag
    return answer_with_rag(query, k=TOP_K, retriever=system, allowed_access=PUBLIC, use_llm=not offline())


def judge_model_now():
    return "offline" if offline() else JUDGE_MODEL_W3


def grade(case, answer, passages):
    if offline():
        ok = "cannot answer" not in answer.lower() or case["expected_behavior"] == "abstain"
        return {"label": "pass" if ok else "fail", "failed": [] if ok else ["C1"], "evidence": "", "note": "offline stand-in",
                "model": "offline", "judge_version": JUDGE_VERSION_W3, "cost_usd": 0.0}
    return judge_answer_v3(case, answer, passages, model=JUDGE_MODEL_W3)


def faithfulness(row):
    if row["abstained"]:
        return {"claims": [], "n_claims": 0, "n_unsupported": 0, "error": False, "skipped": "abstained",
                "model": None, "faith_version": FAITH_VERSION, "cost_usd": 0.0}
    return check_faithfulness(row["answer"], row["passages"], model=JUDGE_MODEL_W3)


def needs_work(row):
    v, f = row.get("verdict"), row.get("faithfulness")
    return (v is None or v["label"] == "error" or v.get("judge_version") != JUDGE_VERSION_W3 or v.get("model") != judge_model_now()
            or f is None or f.get("error") or f.get("faith_version") != FAITH_VERSION)


def run_answers(cases, system_cfg, args):
    cfg_key = f"{system_cfg['mode']}/{system_cfg['strategy']}"
    saved = {r["id"]: r for r in load_jsonl(ANSWER_ROWS) if r.get("system") == cfg_key or args.recompute}
    todo = [c for c in cases if c["id"] not in saved or needs_work(saved[c["id"]])]
    if args.recompute or not todo:
        return [saved[c["id"]] for c in cases if c["id"] in saved]
    print(f"  answers: {len(todo)} cases to answer or grade (system {cfg_key}, judge {judge_model_now()})")
    system = PublicOnly(build_retriever(system_cfg["mode"], system_cfg["strategy"]))
    for i, case in enumerate(todo, 1):
        row = saved.get(case["id"])
        if row is None:
            t0 = time.perf_counter()
            out = call_or_stop(rag_answer, system, case["input"])
            passages = passage_view(out["retrieved_passages"])
            cited = [passages[n - 1]["doc_id"] for n in out.get("citations", []) if 1 <= n <= len(passages)]
            row = {
                "id": case["id"], "set": case["set"], "system": cfg_key, "prompt": "prompts/v3_rag.txt",
                "answer": out["answer"], "language": out.get("language"), "abstained": out["abstained"],
                "abstention_reason": out.get("abstention_reason"), "citations": out.get("citations", []),
                "cited_docs": cited, "citation_validation_failed": out.get("citation_validation_failed", False),
                "retries_used": out.get("retries_used", 0), "passages": passages,
                "answer_model": out.get("model") or ("offline" if offline() else None),
                "cost_usd": round(float(out.get("cost_usd", 0.0) or 0.0), 8),
                "latency_s": round(float(out.get("latency_s", 0.0) or 0.0), 4),
                "wall_latency_s": round(time.perf_counter() - t0, 4),
            }
        if row.get("verdict") is None or row["verdict"]["label"] == "error" or row["verdict"].get("judge_version") != JUDGE_VERSION_W3 \
                or row["verdict"].get("model") != judge_model_now():
            row["verdict"] = call_or_stop(grade, case, row["answer"], row["passages"])
        f = row.get("faithfulness")
        if f is None or f.get("error") or f.get("faith_version") != FAITH_VERSION:
            row["faithfulness"] = call_or_stop(faithfulness, row)
        saved[case["id"]] = row
        save_jsonl(ANSWER_ROWS, list(saved.values()))
        print(f"    [{i}/{len(todo)}] {case['id']}: {row['verdict']['label']}"
              f"{' (abstained)' if row['abstained'] else ''}, {row['faithfulness']['n_unsupported']}/{row['faithfulness']['n_claims']} unsupported")
    return [saved[c["id"]] for c in cases if c["id"] in saved]


# ---------------------------------------------------------------- stage 3: baseline

def run_baseline(w2_cases, args):
    old = {r["id"]: r for r in load_jsonl(W2_BASELINE_OUTPUTS)}
    saved = {r["id"]: r for r in load_jsonl(BASELINE_ROWS)}
    todo = [c for c in w2_cases if c["id"] in old and (c["id"] not in saved or saved[c["id"]]["verdict"]["label"] == "error"
                                                       or saved[c["id"]]["verdict"].get("model") != judge_model_now())]
    if todo and not args.recompute:
        print(f"  baseline: re-grading {len(todo)} saved Week 2 v3 answers with judge version {JUDGE_VERSION_W3}")
        for case in todo:
            v = call_or_stop(grade, case, old[case["id"]]["output_text"], [])
            saved[case["id"]] = {"id": case["id"], "prompt_version": "v3_six_blocks_fewshot", "answer_model": W2_ANSWER_MODEL,
                                 "answer": old[case["id"]]["output_text"], "verdict": v}
            save_jsonl(BASELINE_ROWS, list(saved.values()))
    return [saved[c["id"]] for c in w2_cases if c["id"] in saved]


# ---------------------------------------------------------------- stage 4: report

def acc(rows):
    n = len(rows)
    k = sum(r["verdict"]["label"] == "pass" for r in rows)
    p, lo, hi = accuracy_ci95(k, n)
    if p is None:
        return {"value": None, "ci95": None, "n": 0, "correct": 0}
    return {"value": round(p, 4), "ci95": [round(lo, 4), round(hi, 4)], "n": n, "correct": k}


def failure_label(case, row):
    """W3.8 rule, from saved data only:
         evaluation  the judge reply could not be read
         retrieval   the case needs a document and no gold clause (W3.5) / gold document (W2) was retrieved
         generation  the right passage was retrieved (or none was needed) and the answer still failed"""
    if row["verdict"]["label"] == "error":
        return "evaluation"
    ids = {p["chunk_id"] for p in row["passages"]}
    docs = {p["doc_id"] for p in row["passages"]}
    if case["gold_passages"] and not any(g in ids for g in case["gold_passages"]):
        return "retrieval"
    if not case["gold_passages"] and case["gold_docs"] and not (set(case["gold_docs"]) & docs):
        return "retrieval"
    return "generation"


def build_failures(cases, rows):
    by_id = {c["id"]: c for c in cases}
    failures = []
    for r in rows:
        if r["verdict"]["label"] == "pass":
            continue
        c = by_id[r["id"]]
        failures.append({
            "id": r["id"], "set": r["set"], "input": c["input"], "expected_behavior": c["expected_behavior"],
            "expected_answer": c["expected_answer"], "answer": r["answer"], "abstained": r["abstained"],
            "abstention_reason": r["abstention_reason"], "failed_criteria": r["verdict"]["failed"],
            "judge_note": r["verdict"]["note"], "judge_evidence": r["verdict"]["evidence"],
            "gold": c["gold_passages"] or c["gold_docs"], "retrieved": [p["chunk_id"] for p in r["passages"]],
            "label": failure_label(c, r),
            "unsupported_claims": [x["claim"] for x in (r["faithfulness"]["claims"] or []) if x["verdict"] == "unsupported"],
        })
    passed_unfaithful = [
        {"id": r["id"], "answer": r["answer"],
         "unsupported_claims": [x["claim"] for x in (r["faithfulness"]["claims"] or []) if x["verdict"] == "unsupported"]}
        for r in rows if r["verdict"]["label"] == "pass" and r["faithfulness"]["n_unsupported"] > 0]
    return {"n_answers": len(rows), "n_failures": len(failures), "by_label": dict(Counter(f["label"] for f in failures)),
            "failures": failures, "passed_but_unsupported": passed_unfaithful}


def write_label_sheet(rows):
    """Fixed random sample of claims for a blind human check; no judge verdicts on the sheet."""
    if LABEL_SHEET.exists():
        return load_jsonl(LABEL_SHEET)
    pool = [{"claim_id": f"{r['id']}#c{j}", "case_id": r["id"], "claim": cl["claim"], "answer": r["answer"],
             "passages": [{"label": p["label"], "text": p["text"]} for p in r["passages"]]}
            for r in rows for j, cl in enumerate(r["faithfulness"]["claims"] or [])]
    sample = random.Random(LABEL_SEED).sample(pool, min(LABEL_SAMPLE_SIZE, len(pool)))
    save_jsonl(LABEL_SHEET, sample)
    return sample


def faithfulness_summary(rows):
    claims = [c for r in rows for c in (r["faithfulness"]["claims"] or [])]
    n, bad = len(claims), sum(c["verdict"] == "unsupported" for c in claims)
    p, lo, hi = accuracy_ci95(bad, n)
    answered = [r for r in rows if not r["abstained"]]
    return {"value": round(p, 4) if p is not None else None, "ci95": [round(lo, 4), round(hi, 4)] if p is not None else None,
            "n": n, "unsupported": bad, "answers_checked": len(answered),
            "answers_with_any_unsupported": sum(r["faithfulness"]["n_unsupported"] > 0 for r in answered),
            "judge_errors": sum(bool(r["faithfulness"].get("error")) for r in rows)}


def citation_summary(cases, rows):
    by_id = {c["id"]: c for c in cases}
    answered = [r for r in rows if not r["abstained"]]
    gold_rows = [r for r in answered if by_id[r["id"]]["gold_docs"]]
    cites_gold = sum(1 for r in gold_rows if set(r["cited_docs"]) & set(by_id[r["id"]]["gold_docs"]))
    return {"answers": len(rows), "abstained": len(rows) - len(answered),
            "abstention_reasons": dict(Counter(r["abstention_reason"] for r in rows if r["abstained"])),
            "answered_with_citation": sum(bool(r["citations"]) for r in answered),
            "citation_validation_failed": sum(bool(r["citation_validation_failed"]) for r in rows),
            "gold_doc_cited_when_answered": {"value": round(cites_gold / len(gold_rows), 4) if gold_rows else None, "n": len(gold_rows)}}


def total_spend():
    spend = 0.0
    for r in load_jsonl(ANSWER_ROWS):
        spend += r.get("cost_usd", 0.0) + r.get("verdict", {}).get("cost_usd", 0.0) + r.get("faithfulness", {}).get("cost_usd", 0.0)
    for r in load_jsonl(BASELINE_ROWS):
        spend += r["verdict"].get("cost_usd", 0.0)
    return spend


def main():
    p = argparse.ArgumentParser(description="Week 3 evaluation (W3.5–W3.8)")
    p.add_argument("--recompute", action="store_true", help="no model or API calls; rebuild from saved rows")
    p.add_argument("--limit", type=int, help="smoke test on N cases per set; no scoreboard")
    args = p.parse_args()

    w2_cases, w3_cases = load_cases(args.limit)
    all_cases = w2_cases + w3_cases
    print(f"Week 3 evaluation{' (offline stand-ins)' if offline() else ''}")
    print("Stage 1/4: retrieval, 4 modes x 2 chunkings (W3.5, W3.7) - local models, no API")
    retrieval = run_retrieval(args)
    system_cfg = retrieval["system_choice"] if retrieval and "system_choice" in retrieval else {"mode": "hybrid_rerank", "strategy": "section"}
    print(f"  system for the answers: {system_cfg['mode']}/{system_cfg['strategy']}")
    print(f"Stage 2/4: answers with rag_chain on {len(w2_cases)} Week 2 cases + {len(w3_cases)} W3.5 questions (W3.4, W3.6)")
    rows = run_answers(all_cases, system_cfg, args)
    print("Stage 3/4: Week 2 v3 answers re-graded with the same judge")
    base = run_baseline(w2_cases, args)
    if args.limit:
        print("\nSmoke test finished; scoreboard not written (--limit).")
        return

    print("Stage 4/4: summaries, failure labels, scoreboard (W3.8)")
    by_id = {c["id"]: c for c in all_cases}
    w2_rows = [r for r in rows if r["set"] == "w2"]
    w3_rows = [r for r in rows if r["set"] == "w3"]
    sys_run = retrieval["runs"][f"{system_cfg['mode']}/{system_cfg['strategy']}"]

    rag = {r["id"]: r["verdict"]["label"] == "pass" for r in w2_rows}
    bas = {r["id"]: r["verdict"]["label"] == "pass" for r in base}
    ids = sorted(set(rag) & set(bas))
    b = sum(1 for i in ids if rag[i] and not bas[i])
    c = sum(1 for i in ids if not rag[i] and bas[i])
    corpus = [i for i in ids if by_id[i]["answerable_from"] == "corpus"]
    types = sorted({by_id[r["id"]]["type"] for r in w2_rows})
    rag_vs_base = {
        "judge_model": judge_model_now(), "judge_version": JUDGE_VERSION_W3,
        "with_rag": acc(w2_rows), "without_rag_w2_v3": acc(base),
        "corpus_cases": {"with_rag": sum(rag[i] for i in corpus), "without_rag": sum(bas[i] for i in corpus), "n": len(corpus)},
        "by_type_with_rag": {t: acc([r for r in w2_rows if by_id[r["id"]]["type"] == t]) for t in types},
        "by_type_without_rag": {t: acc([r for r in base if by_id[r["id"]]["type"] == t]) for t in types},
        "mcnemar": {**mcnemar(b, c), "system_a": "rag", "system_b": "w2_v3", "a_right_b_wrong": b, "a_wrong_b_right": c},
        "note": f"without-RAG answers are the saved Week 2 answers ({W2_ANSWER_MODEL}); with-RAG answers come from rag_chain's model chain",
    }

    failures = build_failures(all_cases, rows)
    FAILURES_FILE.write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
    sheet = write_label_sheet(rows)
    kappa = json.loads(KAPPA_FILE.read_text(encoding="utf-8")) if KAPPA_FILE.exists() else None
    faith = faithfulness_summary(rows)
    unans = [r for r in w2_rows if by_id[r["id"]]["type"] == "unanswerable"]
    latencies = [r["wall_latency_s"] for r in rows]
    spend = total_spend()
    ws = lambda d: {**d, "script": SCRIPT}  # noqa: E731

    scoreboard = {
        "week": 3,
        "test_set_size": len(w2_cases),
        "e2e_accuracy": ws({k: v for k, v in acc(w2_rows).items() if k != "correct"}),
        "abstention_correct": ws({k: v for k, v in acc(unans).items() if k != "correct"}),
        "unsupported_claims": ws({"value": faith["value"], "ci95": faith["ci95"], "n": faith["n"]}),
        "hit_at_5": ws({"value": sys_run["overall"]["hit_at_5"], "ci95": sys_run["ci95"]["hit_at_5"], "n": sys_run["overall"]["n"]}),
        "mrr": ws({"value": sys_run["overall"]["mrr"], "ci95": sys_run["ci95"]["mrr"], "n": sys_run["overall"]["n"]}),
        "task_success": {"value": None, "n": None, "script": None},
        "pass_k": {"k": None, "value": None, "n": None, "script": None},
        "injection_success": {"value": None, "n": None, "script": None},
        "cost_per_task_usd": round(statistics.mean(r["cost_usd"] for r in rows), 6) if rows else None,
        "latency_p50_s": round(percentile(latencies, 0.5), 3) if latencies else None,
        "spend_week_usd": round(spend, 4),
        "spend_total_usd": round(SPEND_BEFORE_W3 + spend, 4),
        "use_case": "UC1",
        "system": {"retrieval_mode": system_cfg["mode"], "chunking": system_cfg["strategy"], "top_k": TOP_K,
                   "access_levels": list(PUBLIC), "embedding_model": retrieval.get("embedding_model"),
                   "reranker_model": retrieval.get("reranker_model"), "rag_prompt": "prompts/v3_rag.txt",
                   "answer_models_used": dict(Counter(r["answer_model"] for r in rows)), "choice_rule": retrieval["system_choice"]["rule"]},
        "judge_model": judge_model_now(), "judge_version": JUDGE_VERSION_W3, "faithfulness_version": FAITH_VERSION,
        "test_set_file": "data/w2_test_set.jsonl", "test_set_sha256": sha256(W2_TEST),
        "retrieval_test_file": "data/w3_retrieval_test.jsonl", "retrieval_test_sha256": sha256(RETRIEVAL_TEST),
        "retrieval_test_size": retrieval["n_questions"],
        "retrieval_ablation": "reports/w3_retrieval.json",
        "rag_vs_no_rag": rag_vs_base,
        "w3_questions_e2e": acc(w3_rows),
        "w3_questions_e2e_by_language": {l: acc([r for r in w3_rows if by_id[r["id"]]["language"] == l]) for l in ("en", "tr")},
        "faithfulness": faith,
        "faithfulness_judge_check": kappa,
        "citations": citation_summary(all_cases, rows),
        "failure_labels": {k: failures[k] for k in ("n_answers", "n_failures", "by_label")},
        "judge_errors": sum(r["verdict"]["label"] == "error" for r in rows),
        "offline_standins": offline(),
    }
    SCOREBOARD.write_text(json.dumps(scoreboard, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    for name, res in retrieval["runs"].items():
        o = res["overall"]
        print(f"   {name:22s} hit@1 {o['hit_at_1']:.3f}  hit@3 {o['hit_at_3']:.3f}  hit@5 {o['hit_at_5']:.3f}  hit@10 {o['hit_at_10']:.3f}  MRR {o['mrr']:.3f}")
    print(f"System: {system_cfg['mode']}/{system_cfg['strategy']}  hit@5 {sys_run['overall']['hit_at_5']}  MRR {sys_run['overall']['mrr']}")
    print(f"E2E on 45 Week 2 cases: with RAG {rag_vs_base['with_rag']['value']}, without RAG {rag_vs_base['without_rag_w2_v3']['value']}, "
          f"McNemar exact p {rag_vs_base['mcnemar']['p_exact']}; corpus cases {rag_vs_base['corpus_cases']}")
    print(f"W3.5 questions e2e: {acc(w3_rows)['value']} (n={len(w3_rows)})")
    print(f"Unsupported claims: {faith['unsupported']}/{faith['n']} = {faith['value']}")
    print(f"Failures: {failures['by_label']}")
    print(f"Label sheet: {len(sheet)} claims{'' if kappa else ' (not labeled yet)'}; spend this week ${spend:.4f}")
    print(f"Saved -> {SCOREBOARD.relative_to(ROOT_DIR)}, {RETRIEVAL_FILE.relative_to(ROOT_DIR)}, {FAILURES_FILE.relative_to(ROOT_DIR)}")


if __name__ == "__main__":
    main()
