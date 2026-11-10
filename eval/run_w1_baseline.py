"""Week 1 Baseline Evaluation Script (Deliverables W1.5 & W1.6).

Runs prompts/v1_baseline.txt across all 25 inputs in data/w1_inputs.jsonl at
temperatures T in {0.0, 0.7, 1.2}, or recomputes summary metrics directly from
existing data/w1_baseline_outputs.json (--recompute), and writes:
  - data/w1_baseline_outputs.json
  - reports/scoreboard_w1.json
"""

import argparse
from collections import Counter
import json
import re
import statistics
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.llm import MODEL_PRICING_PER_1M_USD, call_llm, compute_cost_usd

# Matches exact store identifiers (ORD-..., SKU-..., TRK-..., RMA-...) without trailing punctuation
ID_PATTERN = re.compile(r"\b(?:ORD|SKU|TRK|RMA)-[A-Z0-9-]+\b")


def load_jsonl(path: Path) -> list:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def word_set(text: str) -> set:
    return set(re.findall(r"\w+", text.lower()))


def jaccard_similarity(a: str, b: str) -> float:
    sa, sb = word_set(a), word_set(b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / max(1, len(sa | sb))


def check_exact_ids_preserved(user_input: str, model_output: str) -> bool:
    expected_ids = set(ID_PATTERN.findall(user_input))
    if not expected_ids:
        return True
    return all(eid in model_output for eid in expected_ids)


def percentile(values: list, p: float) -> float:
    """Linearly interpolated percentile (matching standard numpy/scipy definition)."""
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (k - f) * (s[c] - s[f])


def evaluate_and_summarize(all_results: list, temperatures: list) -> tuple:
    """Recompute per-run costs, ID preservation, Jaccard similarity, and scoreboard stats."""
    temp_strs = [str(t) for t in temperatures]
    temp_metrics = {
        t: {
            "latencies": [],
            "costs": [],
            "in_tok": [],
            "out_tok": [],
            "think_tok": [],
            "id_ok": [],
            "models": Counter(),
        }
        for t in temp_strs
    }
    overall_models = Counter()
    jaccards_07 = []
    jaccards_12 = []

    for case_record in all_results:
        user_input = case_record["input"]
        for t_str in temp_strs:
            if t_str not in case_record["runs"]:
                continue
            run = case_record["runs"][t_str]
            model_name = run.get("model", "gemini-2.5-flash")
            in_tok = int(run.get("input_tokens", 0))
            out_tok = int(run.get("output_tokens", 0))
            think_tok = int(run.get("thinking_tokens", 0))

            # Recompute exact cost using official model pricing
            cost_usd = round(
                compute_cost_usd(
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    thinking_tokens=think_tok,
                    model_name=model_name,
                ),
                8,
            )
            run["thinking_tokens"] = think_tok
            run["total_tokens"] = in_tok + out_tok + think_tok
            run["cost_usd"] = cost_usd

            id_preserved = check_exact_ids_preserved(user_input, run["output_text"])
            run["exact_ids_preserved"] = id_preserved

            tm = temp_metrics[t_str]
            tm["latencies"].append(float(run["latency_s"]))
            tm["costs"].append(cost_usd)
            tm["in_tok"].append(in_tok)
            tm["out_tok"].append(out_tok)
            tm["think_tok"].append(think_tok)
            tm["id_ok"].append(1.0 if id_preserved else 0.0)
            tm["models"][model_name] += 1
            overall_models[model_name] += 1

        if "0.0" in case_record["runs"] and "0.7" in case_record["runs"]:
            j07 = round(
                jaccard_similarity(
                    case_record["runs"]["0.0"]["output_text"],
                    case_record["runs"]["0.7"]["output_text"],
                ),
                4,
            )
            case_record["jaccard_0.0_vs_0.7"] = j07
            jaccards_07.append(j07)

        if "0.0" in case_record["runs"] and "1.2" in case_record["runs"]:
            j12 = round(
                jaccard_similarity(
                    case_record["runs"]["0.0"]["output_text"],
                    case_record["runs"]["1.2"]["output_text"],
                ),
                4,
            )
            case_record["jaccard_0.0_vs_1.2"] = j12
            jaccards_12.append(j12)

    summary_by_temp = {}
    for t_str, tm in temp_metrics.items():
        if not tm["in_tok"]:
            continue
        mean_in = statistics.mean(tm["in_tok"])
        mean_out = statistics.mean(tm["out_tok"])
        mean_cost = statistics.mean(tm["costs"])
        summary_by_temp[t_str] = {
            "n_cases": len(tm["in_tok"]),
            "mean_input_tokens": round(mean_in, 2),
            "mean_output_tokens": round(mean_out, 2),
            "mean_thinking_tokens": round(statistics.mean(tm["think_tok"]), 2),
            "cost_per_task_usd": round(mean_cost, 6),
            "cost_per_1000_requests_usd": round(mean_cost * 1000, 4),
            "total_temp_spend_usd": round(sum(tm["costs"]), 6),
            "latency_p50_s": round(percentile(tm["latencies"], 0.50), 3),
            "latency_p95_s": round(percentile(tm["latencies"], 0.95), 3),
            "exact_id_preservation_rate": round(statistics.mean(tm["id_ok"]), 4),
            "model_distribution": dict(tm["models"]),
        }

    if jaccards_07 and "0.7" in summary_by_temp:
        summary_by_temp["0.7"]["mean_jaccard_vs_0.0"] = round(statistics.mean(jaccards_07), 4)
        summary_by_temp["0.7"]["min_jaccard_vs_0.0"] = round(min(jaccards_07), 4)
    if jaccards_12 and "1.2" in summary_by_temp:
        summary_by_temp["1.2"]["mean_jaccard_vs_0.0"] = round(statistics.mean(jaccards_12), 4)
        summary_by_temp["1.2"]["min_jaccard_vs_0.0"] = round(min(jaccards_12), 4)

    primary_temp = "0.0" if "0.0" in summary_by_temp else temp_strs[0]
    primary = summary_by_temp[primary_temp]
    total_spend_usd = round(sum(sum(tm["costs"]) for tm in temp_metrics.values()), 4)

    scoreboard = {
        "week": 1,
        "test_set_size": len(all_results),
        "e2e_accuracy": None,
        "abstention_correct": None,
        "unsupported_claims": None,
        "hit_at_5": None,
        "mrr": None,
        "task_success": None,
        "pass_k": None,
        "injection_success": None,
        "cost_per_task_usd": primary["cost_per_task_usd"],
        "latency_p50_s": primary["latency_p50_s"],
        "spend_week_usd": total_spend_usd,
        "spend_total_usd": total_spend_usd,
        "latency_p95_s": primary["latency_p95_s"],
        "use_case": "UC1",
        "model_distribution_75_calls": dict(overall_models),
        "temperature_comparison": summary_by_temp,
        "pricing_assumptions_usd_per_1m": MODEL_PRICING_PER_1M_USD,
    }
    return all_results, scoreboard


def main() -> None:
    parser = argparse.ArgumentParser(description="Run or recompute Week 1 Baseline Evaluation (W1.5 & W1.6)")
    parser.add_argument(
        "--temperatures",
        nargs="+",
        type=float,
        default=[0.0, 0.7, 1.2],
        help="Temperatures to test (default: 0.0 0.7 1.2)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit on number of inputs",
    )
    parser.add_argument(
        "--recompute",
        action="store_true",
        help="Recompute metrics and scoreboard from existing data/w1_baseline_outputs.json without making new API calls",
    )
    args = parser.parse_args()

    inputs_path = ROOT_DIR / "data" / "w1_inputs.jsonl"
    prompt_path = ROOT_DIR / "prompts" / "v1_baseline.txt"
    outputs_path = ROOT_DIR / "data" / "w1_baseline_outputs.json"
    scoreboard_path = ROOT_DIR / "reports" / "scoreboard_w1.json"

    if args.recompute:
        all_results = json.loads(outputs_path.read_text(encoding="utf-8"))
        print(f"Recomputing metrics from {len(all_results)} saved cases in {outputs_path.name}...")
    else:
        cases = load_jsonl(inputs_path)
        if args.limit:
            cases = cases[: args.limit]
        system_prompt = prompt_path.read_text(encoding="utf-8").strip()

        print(f"Loaded {len(cases)} cases from {inputs_path.name}")
        print(f"Running temperatures: {args.temperatures}\n")

        all_results = []
        for idx, case in enumerate(cases, start=1):
            case_record = {
                "id": case["id"],
                "category": case["category"],
                "ingredients": case["ingredients"],
                "input": case["input"],
                "expected_behavior": case["expected_behavior"],
                "runs": {},
            }
            print(f"[{idx:02d}/{len(cases):02d}] {case['id']} ({case['category']})")
            for temp in args.temperatures:
                res = call_llm(
                    user_message=case["input"],
                    system_prompt=system_prompt,
                    temperature=temp,
                )
                case_record["runs"][str(temp)] = res
            all_results.append(case_record)

    all_results, scoreboard = evaluate_and_summarize(all_results, args.temperatures)

    outputs_path.parent.mkdir(parents=True, exist_ok=True)
    scoreboard_path.parent.mkdir(parents=True, exist_ok=True)
    outputs_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
    scoreboard_path.write_text(json.dumps(scoreboard, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== Week 1 Baseline Evaluation Summary ===")
    for temp_str, stats in scoreboard["temperature_comparison"].items():
        j_str = (
            f", Jaccard vs T=0: {stats['mean_jaccard_vs_0.0']} (min {stats['min_jaccard_vs_0.0']})"
            if "mean_jaccard_vs_0.0" in stats
            else ""
        )
        print(
            f"T={temp_str}: in={stats['mean_input_tokens']} tok, out={stats['mean_output_tokens']} tok, "
            f"cost/task=${stats['cost_per_task_usd']:.6f} (${stats['cost_per_1000_requests_usd']:.4f}/1k), "
            f"p50={stats['latency_p50_s']}s, p95={stats['latency_p95_s']}s, "
            f"ID-preserved={stats['exact_id_preservation_rate']*100:.1f}%{j_str}"
        )
    print(f"Total week spend (75 calls): ${scoreboard['spend_week_usd']:.4f}")
    print(f"Model distribution: {scoreboard['model_distribution_75_calls']}")
    print(f"Saved outputs -> {outputs_path}")
    print(f"Saved scoreboard -> {scoreboard_path}")


if __name__ == "__main__":
    main()
