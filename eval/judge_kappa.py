"""Check the LLM judge against the 20 human labels with Cohen's kappa (W2.6).

The human labels are written blind (before looking at the judge's verdicts) on
the same answers the judge graded. This script lines the two up by case id and
reports raw agreement, chance agreement and kappa.

    python3 eval/judge_kappa.py

Reads:  data/w2_human_labels_20.jsonl      (id, prompt_version, label: pass/fail)
        data/w2_outputs_<version>.jsonl     (judge verdicts saved by run_w2_eval.py)
Writes: reports/w2_judge_kappa.json
"""

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "eval"))   # so that stats.py (next to this file) can be imported

from stats import cohens_kappa

SCRIPT_NAME = "eval/judge_kappa.py"


def load_jsonl(path):
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def find_outputs_file(version):
    """Find the saved outputs for a prompt version. A short name such as "v2"
    is accepted when exactly one file starts with it (w2_outputs_v2_*.jsonl)."""
    exact = ROOT_DIR / "data" / f"w2_outputs_{version}.jsonl"
    if exact.exists():
        return exact
    matches = sorted((ROOT_DIR / "data").glob(f"w2_outputs_{version}*.jsonl"))
    if len(matches) == 1:
        return matches[0]
    sys.exit(f"Cannot find one outputs file for prompt version '{version}' (found {len(matches)}).")


def main():
    parser = argparse.ArgumentParser(description="Cohen's kappa between the LLM judge and human labels (W2.6)")
    parser.add_argument("--labels", type=Path, default=ROOT_DIR / "data" / "w2_human_labels_20.jsonl")
    parser.add_argument("--out", type=Path, default=ROOT_DIR / "reports" / "w2_judge_kappa.json")
    args = parser.parse_args()

    human_rows = load_jsonl(args.labels)
    human_labels, judge_labels, disagreements = [], [], []

    for row in human_rows:
        if row["label"] not in ("pass", "fail"):
            sys.exit(f"{row['id']}: human label must be 'pass' or 'fail', got '{row['label']}'.")
        outputs = {r["id"]: r for r in load_jsonl(find_outputs_file(row["prompt_version"]))}
        if row["id"] not in outputs or "judge" not in outputs[row["id"]]:
            sys.exit(f"{row['id']}: no judge verdict saved for prompt version '{row['prompt_version']}'.")
        verdict = outputs[row["id"]]["judge"]

        human_labels.append(row["label"])
        judge_labels.append(verdict["label"])
        if row["label"] != verdict["label"]:
            disagreements.append({
                "id": row["id"],
                "human": row["label"],
                "judge": verdict["label"],
                "human_note": row.get("note", ""),
                "judge_note": verdict.get("note", ""),
            })

    result = cohens_kappa(human_labels, judge_labels)

    def count(human, judge):
        return sum(1 for h, j in zip(human_labels, judge_labels) if h == human and j == judge)

    report = {
        **result,
        "table": {
            "human_pass_judge_pass": count("pass", "pass"),
            "human_pass_judge_fail": count("pass", "fail"),
            "human_fail_judge_pass": count("fail", "pass"),
            "human_fail_judge_fail": count("fail", "fail"),
            "judge_error": sum(1 for j in judge_labels if j == "error"),
        },
        "disagreements": disagreements,
        "labels_file": args.labels.name,
        "script": SCRIPT_NAME,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"n = {result['n']} | raw agreement po = {result['po']} | chance agreement pe = {result['pe']} | kappa = {result['kappa']}")
    print("Table:", report["table"])
    print(f"Disagreements: {len(disagreements)} (listed in {args.out.name})")
    print(f"Saved -> {args.out}")


if __name__ == "__main__":
    main()
