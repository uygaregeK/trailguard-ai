"""Split the store documents into chunks for retrieval (W3.2).

Two strategies, so we can compare them in a retrieval ablation:

  section : one chunk per numbered clause ("## §1 ...") of a document.
            Our policies are written as numbered clauses, and the agent
            cites clauses, so this keeps each rule whole.
  window  : fixed windows of N words with an overlap, ignoring structure.
            The usual baseline: simple, but can cut a rule in half.

Every chunk carries the document's metadata (doc_id, title, category,
access_level, version) and the clause(s) it covers, so a retrieval test can
check hits at the document or the clause level.

    python3 src/chunker.py                      # both strategies, print stats
    python3 src/chunker.py --strategy section   # one strategy
Writes data/chunks_<strategy>.jsonl
"""

import argparse
import json
import re
import statistics
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT_DIR / "data" / "corpus"

FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)
SECTION_HEADING = re.compile(r"^## (§\d+)\s+(.*)$", re.M)

WINDOW_WORDS = 120     # about 160 tokens
WINDOW_OVERLAP = 30    # words shared by neighbouring windows


def parse_document(path):
    """Return (metadata dict, body text) for one corpus file."""
    match = FRONTMATTER.match(path.read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"{path.name}: missing YAML frontmatter")
    meta = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"')
    return meta, match.group(2).strip()


def split_sections(body):
    """List of (clause id, clause title, clause text) in document order."""
    headings = list(SECTION_HEADING.finditer(body))
    sections = []
    for i, heading in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
        text = body[heading.end():end].strip()
        sections.append((heading.group(1), heading.group(2).strip(), text))
    return sections


def base_fields(meta):
    return {
        "doc_id": meta["doc_id"],
        "title": meta["title"],
        "category": meta["category"],
        "access_level": meta["access_level"],
        "version": meta["version"],
    }


def chunk_by_section(meta, body):
    chunks = []
    for clause, clause_title, text in split_sections(body):
        chunks.append({
            "chunk_id": f"{meta['doc_id']}#{clause}",
            **base_fields(meta),
            "sections": [clause],
            # Title and clause heading go into the text, so a chunk makes sense on its own
            "text": f"{meta['title']} — {clause} {clause_title}\n{text}",
        })
    return chunks


def chunk_by_window(meta, body, size=WINDOW_WORDS, overlap=WINDOW_OVERLAP):
    # Remember which clause every word belongs to, to label each window
    words, word_clause = [], []
    for clause, clause_title, text in split_sections(body):
        for word in f"{clause} {clause_title} {text}".split():
            words.append(word)
            word_clause.append(clause)

    chunks, start, step = [], 0, size - overlap
    while start < len(words):
        end = min(start + size, len(words))
        covered = list(dict.fromkeys(word_clause[start:end]))
        chunks.append({
            "chunk_id": f"{meta['doc_id']}#w{len(chunks)}",
            **base_fields(meta),
            "sections": covered,
            "text": f"{meta['title']}\n" + " ".join(words[start:end]),
        })
        if end == len(words):
            break
        start += step
    return chunks


STRATEGIES = {"section": chunk_by_section, "window": chunk_by_window}


def build_chunks(strategy, corpus_dir=CORPUS_DIR):
    chunks = []
    for path in sorted(corpus_dir.glob("*.md")):
        meta, body = parse_document(path)
        chunks.extend(STRATEGIES[strategy](meta, body))
    return chunks


def main():
    parser = argparse.ArgumentParser(description="Chunk the corpus (W3.2)")
    parser.add_argument("--strategy", choices=[*STRATEGIES, "both"], default="both")
    args = parser.parse_args()

    strategies = list(STRATEGIES) if args.strategy == "both" else [args.strategy]
    for strategy in strategies:
        chunks = build_chunks(strategy)
        out = ROOT_DIR / "data" / f"chunks_{strategy}.jsonl"
        out.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks), encoding="utf-8")
        sizes = [len(c["text"].split()) for c in chunks]
        split_rules = sum(1 for c in chunks if len(c["sections"]) > 1)
        print(f"{strategy:8s}: {len(chunks)} chunks | words per chunk: mean {statistics.mean(sizes):.0f}, "
              f"min {min(sizes)}, max {max(sizes)} | chunks spanning >1 clause: {split_rules} -> {out.name}")


if __name__ == "__main__":
    main()
