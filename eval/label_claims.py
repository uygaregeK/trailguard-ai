"""Blind human labels for the faithfulness check (W3.6).

Shows the claims in data/w3_claim_label_sheet.jsonl one by one, with the
passages the system retrieved, and asks one question per claim:

    Does a passage state this claim?   s = supported   u = unsupported

The judge's verdicts are not shown. Answers are saved after every claim to
data/w3_claim_labels_human.jsonl, so you can stop (q) and continue later.

    python3 eval/label_claims.py --labeler "Arda Agovic"
"""

import argparse
import json
import textwrap
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SHEET = ROOT_DIR / "data" / "w3_claim_label_sheet.jsonl"
OUT = ROOT_DIR / "data" / "w3_claim_labels_human.jsonl"


def load(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--labeler", required=True)
    args = p.parse_args()

    sheet = load(SHEET)
    if not sheet:
        print("No label sheet yet. Run eval/run_w3_rag.py first.")
        return
    done = {r["claim_id"] for r in load(OUT)}
    todo = [c for c in sheet if c["claim_id"] not in done]
    print(f"{len(sheet)} claims on the sheet, {len(done)} already labeled, {len(todo)} to go.\n")
    print("Rule: 'supported' only if one of the passages below states the claim (or it follows")
    print("directly, e.g. simple arithmetic). True-sounding but not in the passages = unsupported.\n")

    for i, c in enumerate(todo, 1):
        print("=" * 78)
        print(f"Claim {len(done) + i}/{len(sheet)}   ({c['claim_id']})\n")
        print("CLAIM:  " + "\n        ".join(textwrap.wrap(c["claim"], 70)))
        print("\nPASSAGES THE SYSTEM HAD:")
        for psg in c["passages"]:
            body = " ".join(psg["text"].split())
            print(f"  [{psg['label']}] " + "\n      ".join(textwrap.wrap(body, 72)))
        while True:
            ans = input("\ns = supported, u = unsupported, q = stop for now > ").strip().lower()
            if ans in ("s", "u", "q"):
                break
        if ans == "q":
            print("Saved. Run the same command again to continue.")
            return
        with OUT.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"claim_id": c["claim_id"], "claim": c["claim"],
                                "human": "supported" if ans == "s" else "unsupported",
                                "labeler": args.labeler}, ensure_ascii=False) + "\n")
    print("\nAll claims labeled. Next: python3 eval/faithfulness_kappa.py")


if __name__ == "__main__":
    main()
