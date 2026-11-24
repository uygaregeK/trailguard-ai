"""Does the faithfulness judge agree with a human? (W3.6)

Compares the human labels (data/w3_claim_labels_human.jsonl, written blind by
eval/label_claims.py) with the judge's verdicts for the same claims (saved in
data/w3_outputs_rag.jsonl). Writes reports/w3_faithfulness_kappa.json.

    python3 eval/faithfulness_kappa.py
"""

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "eval"))
from stats import cohens_kappa  # noqa: E402

HUMAN = ROOT_DIR / "data" / "w3_claim_labels_human.jsonl"
ANSWERS = ROOT_DIR / "data" / "w3_outputs_rag.jsonl"
OUT = ROOT_DIR / "reports" / "w3_faithfulness_kappa.json"


def load(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", type=Path, default=HUMAN,
                    help="reference labels to compare with (default: the human labels)")
    labels_path = ap.parse_args().labels
    if not labels_path.is_absolute():
        labels_path = (Path.cwd() / labels_path)
    if not labels_path.exists():
        print("No human labels yet: run python3 eval/label_claims.py --labeler \"Your Name\"")
        return
    judge = {}
    for row in load(ANSWERS):
        for j, cl in enumerate(row["faithfulness"]["claims"] or []):
            judge[f"{row['id']}#c{j}"] = cl
    pairs, skipped = [], []
    for h in load(labels_path):
        cl = judge.get(h["claim_id"])
        if cl is None or cl["claim"] != h["claim"]:
            skipped.append(h["claim_id"])       # the judge was re-run and the claim changed
            continue
        pairs.append((h["claim_id"], h["human"], cl["verdict"]))

    hum = [p[1] for p in pairs]
    jud = [p[2] for p in pairs]
    res = cohens_kappa(hum, jud)
    table = {f"human_{a}__judge_{b}": sum(1 for _, x, y in pairs if x == a and y == b)
             for a in ("supported", "unsupported") for b in ("supported", "unsupported")}
    out = {
        "n": len(pairs),
        "labels_file": str(labels_path.resolve().relative_to(ROOT_DIR)),
        "labelers": sorted({h["labeler"] for h in load(labels_path)}),
        **({k: (round(v, 4) if isinstance(v, float) else v) for k, v in res.items()} if isinstance(res, dict) else {"kappa": res}),
        "confusion": table,
        "disagreements": [{"claim_id": i, "human": x, "judge": y} for i, x, y in pairs if x != y],
        "human_unsupported_rate": round(hum.count("unsupported") / len(hum), 4) if hum else None,
        "judge_unsupported_rate": round(jud.count("unsupported") / len(jud), 4) if jud else None,
        "skipped_changed_claims": skipped,
        "script": "eval/faithfulness_kappa.py",
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\nSaved -> {OUT.relative_to(ROOT_DIR)}. Run python3 eval/run_w3_rag.py --recompute to put it on the scoreboard.")


if __name__ == "__main__":
    main()
