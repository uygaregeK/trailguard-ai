"""Week 2 evaluation harness (W2.4, W2.5).

One command runs every test case through every main-prompt version, grades the
answers with the LLM judge, and writes the scoreboard:

    python3 eval/run_w2_eval.py

What it does, per prompt version and per test case:
  1. Sends the customer message, wrapped in <customer_message> tags, to the
     model with that prompt (temperature 0).
  2. Asks the judge (src/judge.py) whether the answer passes criteria C1-C5.
  3. Saves the row at once, so an interrupted run continues where it stopped.

It also runs the W2.1 request classifier (src/classifier.py) once per case.
Then it compares the prompt versions (accuracy with 95% intervals, McNemar
between the best two) and writes reports/scoreboard_w2.json.

Other modes:
    python3 eval/run_w2_eval.py --recompute   # no API calls: rebuild the scoreboard from saved rows
    python3 eval/run_w2_eval.py --limit 3     # smoke test on 3 cases; does not write the scoreboard
"""

import argparse
import hashlib
import json
import re
import signal
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))            # so that "src" can be imported
sys.path.insert(0, str(ROOT_DIR / "eval"))   # so that stats.py (next to this file) can be imported

from src.classifier import classify_request
from src.judge import JUDGE_MODEL, JUDGE_VERSION, judge_answer
from src.llm import call_llm
from src.schemas import VALID_INTENTS
from stats import accuracy_ci95, mcnemar, percentile

# Main-prompt versions compared in W2.5 (file names in prompts/, without .txt)
DEFAULT_VERSIONS = ["v1_baseline", "v2_six_blocks", "v3_six_blocks_fewshot"]

# One fixed model writes all answers, so versions are compared on equal terms.
ANSWER_MODEL = "gemini-3.1-flash-lite"

SCRIPT_NAME = "eval/run_w2_eval.py"

# The API wrapper sets no network timeout, so a stalled request would hang the
# whole run. We give every call this many seconds, then try it again.
CALL_TIMEOUT_S = 120
CALL_ATTEMPTS = 3
ID_PATTERN = re.compile(r"\b(?:ORD|SKU|TRK|RMA)-[A-Z0-9-]*[A-Z0-9]")


# ---------------------------------------------------------------- files

def load_jsonl(path):
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def save_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def outputs_path(version):
    return ROOT_DIR / "data" / f"w2_outputs_{version}.jsonl"


def file_sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------- API calls

class CallTimeout(RuntimeError):
    """Raised by the alarm when an API call gives no reply in time."""


def _on_alarm(signum, frame):
    raise CallTimeout(f"no reply from the API within {CALL_TIMEOUT_S} seconds")


def stop_run(reason):
    print(f"\nStopped: {reason}")
    print("Progress is saved. Run the same command again to continue.")
    sys.exit(2)


def call_or_stop(function, *args, **kwargs):
    """Make one API call. A call that stalls is tried again; if the API keeps
    refusing (rate limit, missing key, repeated stalls) the run stops cleanly:
    everything done so far is already saved on disk."""
    signal.signal(signal.SIGALRM, _on_alarm)
    for attempt in range(1, CALL_ATTEMPTS + 1):
        # The timer repeats, so a retry inside the called function is covered too
        signal.setitimer(signal.ITIMER_REAL, CALL_TIMEOUT_S, CALL_TIMEOUT_S)
        try:
            return function(*args, **kwargs)
        except CallTimeout as err:
            print(f"  {err} (attempt {attempt}/{CALL_ATTEMPTS})")
        except RuntimeError as err:
            stop_run(err)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
    stop_run(f"the API did not reply in {CALL_ATTEMPTS} attempts")


def wrap_customer_message(text):
    """Mark the customer's text as data, as block 4 of the main prompt describes.
    Every prompt version receives exactly the same wrapped message."""
    return f"<customer_message>\n{text}\n</customer_message>"


def invented_ids(case_input, answer):
    """IDs that appear in the answer but not in the customer message.
    A changed digit or a made-up ID both show up here (deterministic check).
    Format placeholders such as ORD-YYYY-XXXX have no digit and are not counted."""
    allowed = set(ID_PATTERN.findall(case_input))
    found = {i for i in ID_PATTERN.findall(answer) if any(ch.isdigit() for ch in i)}
    return sorted(found - allowed)


def run_version(version, cases, args):
    """Answer and judge every case with one prompt version. Returns its rows."""
    system_prompt = (ROOT_DIR / "prompts" / f"{version}.txt").read_text(encoding="utf-8").strip()
    path = outputs_path(version)
    saved = {row["id"]: row for row in load_jsonl(path)} if path.exists() else {}
    rows = []

    for index, case in enumerate(cases, start=1):
        row = saved.get(case["id"], {"id": case["id"], "prompt_version": version})

        if "output_text" not in row and not args.recompute:
            print(f"[{version}] {index:02d}/{len(cases)} {case['id']}: answering")
            result = call_or_stop(
                call_llm,
                user_message=wrap_customer_message(case["input"]),
                system_prompt=system_prompt,
                temperature=0.0,
                model=args.model,
                allow_fallback=False,
            )
            row.update(result)
            saved[case["id"]] = row
            save_jsonl(path, list(saved.values()))
            time.sleep(args.sleep)

        # All verdicts must come from the same judge: same model, same prompt version.
        # An older verdict is kept in the row for the record and the answer is graded again.
        if "judge" in row and not args.recompute:
            same_judge = row["judge"]["model"] == args.judge_model and row["judge"].get("judge_version", 1) == JUDGE_VERSION
            if not same_judge:
                row.setdefault("previous_verdicts", []).append(row.pop("judge"))

        if "output_text" in row and "judge" not in row and not args.recompute:
            print(f"[{version}] {index:02d}/{len(cases)} {case['id']}: judging")
            row["judge"] = call_or_stop(
                judge_answer, case=case, system_answer=row["output_text"], model=args.judge_model
            )
            saved[case["id"]] = row
            save_jsonl(path, list(saved.values()))
            time.sleep(args.sleep)

        if "judge" in row:
            # Scores are recomputed on every run from the saved answer and verdict
            row["type"] = case["type"]
            row["invented_ids"] = invented_ids(case["input"], row["output_text"])
            row["correct"] = row["judge"]["label"] == "pass"
            saved[case["id"]] = row
        rows.append(row)

    save_jsonl(path, list(saved.values()))
    return rows


def classifier_api_failed(result):
    """classify_request() never raises: when the API refuses it quietly answers
    with keyword rules instead. Detect that case so we can stop and retry later."""
    errors = " ".join(str(e) for e in result.get("errors", []))
    return result.get("used_fallback", False) and any(
        sign in errors
        for sign in ("429", "503", "RESOURCE_EXHAUSTED", "failed across candidate models", "GEMINI_API_KEY", "no reply from the API")
    )


def id_set(entities):
    """All ID strings in an entities dict, whatever the keys are called
    (the test set says "tracking", the classifier says "tracking_number")."""
    found = set()
    for value in (entities or {}).values():
        values = value if isinstance(value, list) else [value]
        found.update(v for v in values if v)
    return found


def run_classifier(cases, args):
    """Run the W2.1 request classifier once per case and score it."""
    path = ROOT_DIR / "data" / "w2_classifier_outputs.jsonl"
    saved = {row["id"]: row for row in load_jsonl(path)} if path.exists() else {}

    for index, case in enumerate(cases, start=1):
        if case["id"] in saved or args.recompute:
            continue
        print(f"[classifier] {index:02d}/{len(cases)} {case['id']}")
        result = call_or_stop(classify_request, case["input"])
        if classifier_api_failed(result):
            print(f"\nStopped: the classifier could not reach the API ({result['errors']}).")
            print("Progress is saved. Run the same command again to continue.")
            sys.exit(2)
        saved[case["id"]] = {"id": case["id"], **result}
        save_jsonl(path, list(saved.values()))
        time.sleep(args.sleep)

    rows = [saved[c["id"]] for c in cases if c["id"] in saved]
    if len(rows) < len(cases):
        return {"complete": False, "done": len(rows)}

    by_id = {row["id"]: row for row in rows}
    n = len(cases)

    def predicted(case, key):
        return by_id[case["id"]]["classification"].get(key)

    summary = {
        "complete": True,
        "n": n,
        "schema_valid_rate": round(sum(1 for r in rows if r["llm_valid"]) / n, 4),
        "rule_fallback_used": sum(1 for r in rows if r["used_fallback"]),
        "retries_used_total": sum(r["retries_used"] for r in rows),
        "urgency_accuracy": round(sum(predicted(c, "urgency") == c["urgency"] for c in cases) / n, 4),
        "entities_exact_match": round(sum(id_set(predicted(c, "entities")) == id_set(c["entities"]) for c in cases) / n, 4),
        "models": dict(Counter(r.get("model", "rule_fallback") for r in rows)),
        "mean_cost_usd": round(statistics.mean(r["cost_usd"] for r in rows), 6),
        "total_cost_usd": round(sum(r["cost_usd"] for r in rows), 6),
        "latency_by_id": {r["id"]: r["latency_s"] for r in rows},
    }

    # Intent accuracy only makes sense when both sides use the same label names
    gold_labels = {c["intent"] for c in cases}
    if gold_labels <= VALID_INTENTS:
        summary["intent_accuracy"] = round(sum(predicted(c, "intent") == c["intent"] for c in cases) / n, 4)
    else:
        summary["intent_accuracy"] = None
        summary["intent_note"] = (
            f"Not comparable: the test set uses the intent labels {sorted(gold_labels)}, "
            f"the classifier uses {sorted(VALID_INTENTS)}."
        )
        summary["predicted_intents"] = dict(Counter(predicted(c, "intent") for c in cases))
    return summary


# ---------------------------------------------------------------- scoring

def rate(rows):
    """Accuracy over a list of rows as {"value", "ci95", "n"}."""
    n = len(rows)
    correct = sum(1 for r in rows if r["correct"])
    p, low, high = accuracy_ci95(correct, n)
    if p is None:
        return {"value": None, "ci95": None, "n": 0}
    return {"value": round(p, 4), "ci95": [round(low, 4), round(high, 4)], "n": n}


def summarize_version(rows, cases):
    """All numbers for one prompt version."""
    case_by_id = {c["id"]: c for c in cases}
    by_type = {}
    for case_type in sorted({c["type"] for c in cases}):
        by_type[case_type] = rate([r for r in rows if r["type"] == case_type])
    by_source = {}
    for source in sorted({c["answerable_from"] for c in cases}):
        by_source[source] = rate([r for r in rows if case_by_id[r["id"]]["answerable_from"] == source])

    return {
        "accuracy": rate(rows),
        "abstention_correct": by_type.get("unanswerable"),
        "accuracy_by_type": by_type,
        "accuracy_by_answerable_from": by_source,
        "failed_criteria": dict(Counter(c for r in rows for c in r["judge"]["failed"])),
        "judge_errors": sum(1 for r in rows if r["judge"]["label"] == "error"),
        "answers_with_invented_ids": sum(1 for r in rows if r["invented_ids"]),
        "latency_p50_s": round(percentile([r["latency_s"] for r in rows], 0.5), 3),
        "mean_cost_usd": round(statistics.mean(r["cost_usd"] for r in rows), 6),
        "answer_models": dict(Counter(r["model"] for r in rows)),
    }


def compare_best_two(results, summaries):
    """McNemar's test between the two versions with the highest accuracy."""
    ranked = sorted(summaries, key=lambda v: (-summaries[v]["accuracy"]["value"], v))
    if len(ranked) < 2:
        return None
    a, b = ranked[0], ranked[1]
    a_correct = {r["id"]: r["correct"] for r in results[a]}
    b_correct = {r["id"]: r["correct"] for r in results[b]}
    only_a = sum(1 for cid in a_correct if a_correct[cid] and not b_correct[cid])
    only_b = sum(1 for cid in a_correct if not a_correct[cid] and b_correct[cid])
    test = mcnemar(only_a, only_b)
    return {"version_a": a, "version_b": b, "a_right_b_wrong": only_a, "a_wrong_b_right": only_b, **test}


def with_script(metric):
    return {**metric, "script": SCRIPT_NAME}


# ---------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(description="Week 2 evaluation harness (W2.4, W2.5)")
    parser.add_argument("--tests", type=Path, default=ROOT_DIR / "data" / "w2_test_set.jsonl")
    parser.add_argument("--versions", nargs="+", default=None, help="Prompt versions (file names in prompts/ without .txt)")
    parser.add_argument("--model", default=ANSWER_MODEL, help="Model that writes the answers")
    parser.add_argument("--judge-model", default=JUDGE_MODEL, help="Model that grades the answers")
    parser.add_argument("--sleep", type=float, default=4.5, help="Seconds to wait between API calls")
    parser.add_argument("--limit", type=int, default=None, help="Smoke test on the first N cases (no scoreboard)")
    parser.add_argument("--recompute", action="store_true", help="No API calls: rebuild the scoreboard from saved rows")
    args = parser.parse_args()

    cases = load_jsonl(args.tests)
    if args.limit:
        cases = cases[: args.limit]

    versions = args.versions or [v for v in DEFAULT_VERSIONS if (ROOT_DIR / "prompts" / f"{v}.txt").exists()]
    missing = [v for v in DEFAULT_VERSIONS if v not in versions] if args.versions is None else []
    if missing:
        print(f"Note: prompt files not found, skipped: {missing}")
    print(f"{len(cases)} test cases, prompt versions: {versions}")
    print(f"Answer model: {args.model} | Judge model: {args.judge_model}\n")

    results = {version: run_version(version, cases, args) for version in versions}
    classifier = run_classifier(cases, args)

    # The scoreboard is written only when every case has an answer and a verdict
    unfinished = {v: sum(1 for r in rows if "correct" not in r) for v, rows in results.items()}
    if any(unfinished.values()):
        print(f"\nNot finished yet (cases without a verdict): {unfinished}")
        print("Run the command again without --recompute to complete them.")
        sys.exit(1)

    summaries = {version: summarize_version(rows, cases) for version, rows in results.items()}
    comparison = compare_best_two(results, summaries)
    best = sorted(summaries, key=lambda v: (-summaries[v]["accuracy"]["value"], v))[0]
    best_summary = summaries[best]

    print("\n=== Prompt comparison ===")
    for version, s in summaries.items():
        acc = s["accuracy"]
        print(f"{version}: accuracy {acc['value']:.3f} (95% interval {acc['ci95'][0]:.3f}-{acc['ci95'][1]:.3f}, n={acc['n']})")
    if comparison:
        print(f"McNemar {comparison['version_a']} vs {comparison['version_b']}: b={comparison['b']}, c={comparison['c']}, "
              f"chi2={comparison['chi2']}, exact p={comparison['p_exact']}")

    if args.limit:
        print("\n--limit was used: this is a smoke test, the scoreboard was not written.")
        return

    # Spend: every saved call made for this week's evaluation, at list prices.
    # That includes verdicts that were later replaced and the W2.8 injection attempts.
    spend_week = sum(r["cost_usd"] + r["judge"]["cost_usd"] for rows in results.values() for r in rows)
    spend_week += sum(old["cost_usd"] for rows in results.values() for r in rows for old in r.get("previous_verdicts", []))
    injections_path = ROOT_DIR / "data" / "w2_injection_results.json"
    if injections_path.exists():
        spend_week += sum(r["cost_usd"] for r in json.loads(injections_path.read_text(encoding="utf-8")))
    cost_per_task = best_summary["mean_cost_usd"]
    latency_p50 = best_summary["latency_p50_s"]
    if classifier.get("complete"):
        # One customer request = one classifier call + one answer call
        spend_week += classifier["total_cost_usd"]
        cost_per_task += classifier["mean_cost_usd"]
        classify_latency = classifier.pop("latency_by_id")
        latency_p50 = round(percentile([r["latency_s"] + classify_latency[r["id"]] for r in results[best]], 0.5), 3)

    w1_path = ROOT_DIR / "reports" / "scoreboard_w1.json"
    spend_before = json.loads(w1_path.read_text(encoding="utf-8"))["spend_total_usd"] if w1_path.exists() else 0.0

    scoreboard = {
        "week": 2,
        "test_set_size": len(cases),
        "e2e_accuracy": with_script(best_summary["accuracy"]),
        "abstention_correct": with_script(best_summary["abstention_correct"]),
        "unsupported_claims": {"value": None, "n": None, "script": None},
        "hit_at_5": {"value": None, "n": None, "script": None},
        "mrr": {"value": None, "n": None, "script": None},
        "task_success": {"value": None, "n": None, "script": None},
        "pass_k": {"k": None, "value": None, "n": None, "script": None},
        "injection_success": {"value": None, "n": None, "script": None},
        "cost_per_task_usd": round(cost_per_task, 6),
        "latency_p50_s": latency_p50,
        "spend_week_usd": round(spend_week, 4),
        "spend_total_usd": round(spend_before + spend_week, 4),
        # Everything below is extra detail behind the numbers above
        "use_case": "UC1",
        "system_prompt_version": best,
        "answer_model": args.model,
        "judge_model": args.judge_model,
        "judge_version": JUDGE_VERSION,
        "test_set_file": str(args.tests.relative_to(ROOT_DIR)) if args.tests.is_relative_to(ROOT_DIR) else str(args.tests),
        "test_set_sha256": file_sha256(args.tests),
        "prompt_comparison": summaries,
        "mcnemar_best_two": comparison,
        "classifier": classifier,
    }

    scoreboard_path = ROOT_DIR / "reports" / "scoreboard_w2.json"
    scoreboard_path.parent.mkdir(parents=True, exist_ok=True)
    scoreboard_path.write_text(json.dumps(scoreboard, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nSystem version for the scoreboard: {best}")
    print(f"Saved scoreboard -> {scoreboard_path}")


if __name__ == "__main__":
    main()
