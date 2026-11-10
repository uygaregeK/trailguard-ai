"""Week 1 Baseline Evaluation Script (Deliverables W1.5 & W1.6).

Runs prompts/v1_baseline.txt across all 25 inputs in data/w1_inputs.jsonl at
temperatures T in {0.0, 0.7, 1.2}, measures token usage, USD cost, latency (p50/p95),
exact identifier preservation, and cross-temperature lexical stability (Jaccard similarity),
and writes:
  - data/w1_baseline_outputs.json
  - reports/scoreboard_w1.json
"""

import argparse
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Set

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.llm import PRICE_PER_1M_INPUT_USD, PRICE_PER_1M_OUTPUT_USD, call_llm

ID_PATTERN = re.compile(r"\b(?:ORD|SKU|TRK|RMA)-[A-Z0-9-]+\b")


def load_jsonl(path: Path) -> List[Dict]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def word_set(text: str) -> Set[str]:
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


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (k - f) * (s[c] - s[f])


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Week 1 Baseline Evaluation (W1.5 & W1.6)")
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
        help="Optional limit on number of inputs for quick smoke testing",
    )
    args = parser.parse_args()

    inputs_path = ROOT_DIR / "data" / "w1_inputs.jsonl"
    prompt_path = ROOT_DIR / "prompts" / "v1_baseline.txt"
    outputs_path = ROOT_DIR / "data" / "w1_baseline_outputs.json"
    scoreboard_path = ROOT_DIR / "reports" / "scoreboard_w1.json"

    cases = load_jsonl(inputs_path)
    if args.limit:
        cases = cases[: args.limit]
    system_prompt = prompt_path.read_text(encoding="utf-8").strip()

    print(f"Loaded {len(cases)} cases from {inputs_path.name}")
    print(f"Running temperatures: {args.temperatures}\n")

    all_results: List[Dict] = []
    temp_metrics: Dict[str, Dict] = {str(t): {"latencies": [], "costs": [], "in_tok": [], "out_tok": [], "id_ok": []} for t in args.temperatures}

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
            id_preserved = check_exact_ids_preserved(case["input"], res["output_text"])
            res["exact_ids_preserved"] = id_preserved
            case_record["runs"][str(temp)] = res

            tm = temp_metrics[str(temp)]
            tm["latencies"].append(res["latency_s"])
            tm["costs"].append(res["cost_usd"])
            tm["in_tok"].append(res["input_tokens"])
            tm["out_tok"].append(res["output_tokens"])
            tm["id_ok"].append(1.0 if id_preserved else 0.0)

        # Compute cross-temperature lexical overlap if 0.0, 0.7, 1.2 were run
        if "0.0" in case_record["runs"] and "0.7" in case_record["runs"]:
            case_record["jaccard_0.0_vs_0.7"] = round(
                jaccard_similarity(
                    case_record["runs"]["0.0"]["output_text"],
                    case_record["runs"]["0.7"]["output_text"],
                ),
                4,
            )
        if "0.0" in case_record["runs"] and "1.2" in case_record["runs"]:
            case_record["jaccard_0.0_vs_1.2"] = round(
                jaccard_similarity(
                    case_record["runs"]["0.0"]["output_text"],
                    case_record["runs"]["1.2"]["output_text"],
                ),
                4,
            )

        all_results.append(case_record)

    summary_by_temp = {}
    for temp_str, tm in temp_metrics.items():
        mean_in = statistics.mean(tm["in_tok"])
        mean_out = statistics.mean(tm["out_tok"])
        mean_cost = statistics.mean(tm["costs"])
        summary_by_temp[temp_str] = {
            "n_cases": len(cases),
            "mean_input_tokens": round(mean_in, 2),
            "mean_output_tokens": round(mean_out, 2),
            "cost_per_task_usd": round(mean_cost, 6),
            "cost_per_1000_requests_usd": round(mean_cost * 1000, 4),
            "latency_p50_s": round(percentile(tm["latencies"], 0.50), 3),
            "latency_p95_s": round(percentile(tm["latencies"], 0.95), 3),
            "exact_id_preservation_rate": round(statistics.mean(tm["id_ok"]), 4),
        }

    primary_temp = "0.0" if "0.0" in summary_by_temp else str(args.temperatures[0])
    primary = summary_by_temp[primary_temp]

    scoreboard = {
        "week": 1,
        "use_case": "UC1",
        "model": all_results[0]["runs"][primary_temp]["model"] if all_results else "gemini-2.5-flash",
        "n_eval_cases": len(cases),
        "e2e_accuracy": None,
        "hit_at_5": None,
        "mrr": None,
        "unsupported_claims": None,
        "task_success": None,
        "steps_per_task": None,
        "abstention_correct": None,
        "injection_success": None,
        "pass_k": None,
        "latency_p50_s": primary["latency_p50_s"],
        "latency_p95_s": primary["latency_p95_s"],
        "cost_per_task_usd": primary["cost_per_task_usd"],
        "temperature_comparison": summary_by_temp,
        "pricing_assumptions_usd_per_1m": {
            "input": PRICE_PER_1M_INPUT_USD,
            "output": PRICE_PER_1M_OUTPUT_USD,
        },
    }

    outputs_path.parent.mkdir(parents=True, exist_ok=True)
    scoreboard_path.parent.mkdir(parents=True, exist_ok=True)
    outputs_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
    scoreboard_path.write_text(json.dumps(scoreboard, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== Week 1 Baseline Evaluation Complete ===")
    for temp_str, stats in summary_by_temp.items():
        print(
            f"T={temp_str}: in={stats['mean_input_tokens']} tok, out={stats['mean_output_tokens']} tok, "
            f"cost/task=${stats['cost_per_task_usd']:.6f} (${stats['cost_per_1000_requests_usd']:.4f}/1k), "
            f"p50={stats['latency_p50_s']}s, p95={stats['latency_p95_s']}s, "
            f"ID-preserved={stats['exact_id_preservation_rate']*100:.1f}%"
        )
    print(f"\nSaved detailed outputs -> {outputs_path}")
    print(f"Saved Week 1 scoreboard -> {scoreboard_path}")


if __name__ == "__main__":
    main()

