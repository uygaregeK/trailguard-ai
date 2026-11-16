"""W2.6 helper: pick 20 open-ended answers for blind human labeling.

Reads the test set and the system outputs, picks 20 open-ended cases with a
fixed seed (so the same 20 are chosen every time), and writes a sheet with the
input, the expected answer and the system's answer. The judge's verdicts are
NOT included, so the labels stay blind.

Usage:
    python3 eval/make_label_sheet.py --tests data/w2_test_set.jsonl \
        --outputs <outputs file> --prompt-version v2
"""

import argparse
import json
import random
from pathlib import Path

OPEN_ENDED = {"answer", "abstain", "refuse"}
N_LABELS = 20
SEED = 42


def load(path: Path):
    """Load a .jsonl file (one object per line) or a .json list."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return json.loads(text)


def answer_text(row: dict) -> str:
    """Find the model's answer in an output row, whatever the key is called."""
    for key in ("output_text", "output", "answer", "response"):
        if row.get(key):
            return row[key]
    return ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tests", type=Path, required=True)
    parser.add_argument("--outputs", type=Path, required=True)
    parser.add_argument("--prompt-version", default="v2")
    parser.add_argument("--out", type=Path, default=Path("data/w2_label_sheet.jsonl"))
    args = parser.parse_args()

    tests = {t["id"]: t for t in load(args.tests)}
    outputs = {o["id"]: o for o in load(args.outputs)}

    # Only open-ended cases that the system actually answered
    candidates = sorted(
        cid for cid, t in tests.items()
        if t.get("expected_behavior") in OPEN_ENDED and cid in outputs
    )
    if len(candidates) < N_LABELS:
        raise SystemExit(f"Only {len(candidates)} open-ended cases with outputs; need {N_LABELS}.")

    chosen = sorted(random.Random(SEED).sample(candidates, N_LABELS))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for cid in chosen:
            t = tests[cid]
            f.write(json.dumps({
                "id": cid,
                "prompt_version": args.prompt_version,
                "type": t.get("type"),
                "input": t["input"],
                "expected_behavior": t.get("expected_behavior"),
                "expected_answer": t.get("expected_answer"),
                "system_answer": answer_text(outputs[cid]),
                "label": "",      # fill in: pass or fail
                "failed": [],     # fill in: e.g. ["C1", "C2"]
                "note": "",       # fill in: one sentence of evidence
            }, ensure_ascii=False) + "\n")

    print(f"Wrote {N_LABELS} cases to {args.out} (seed {SEED}): {', '.join(chosen)}")


if __name__ == "__main__":
    main()
