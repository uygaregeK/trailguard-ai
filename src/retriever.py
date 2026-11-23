"""Hybrid retriever for the store documents (W3.3).

Pipeline for one query:
    BM25 (keywords, exact IDs) ─┐
                                ├─ Reciprocal Rank Fusion ─> reranker ─> top k chunks
    Dense embeddings (meaning) ─┘

This file holds the parts that need no model: BM25, Reciprocal Rank Fusion,
the access-level filter and the command line. The dense retriever and the
reranker are plug-ins (see DenseRetriever / Reranker below); until a model is
chosen, the pipeline runs with BM25 only, so it can already be tested.

    python3 src/retriever.py "can I return muddy shoes" --k 5
    python3 src/retriever.py "ORD-2026-8841 return" --strategy window
"""

import argparse
import math
import re
import sys
from collections import Counter
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from chunker import build_chunks

# Keeps IDs such as ord-2026-8841 or sku-sal-spdc6-42 as one token,
# so BM25 can match them exactly.
TOKEN = re.compile(r"[a-z0-9§]+(?:-[a-z0-9]+)*")
RRF_K = 60  # standard constant in Reciprocal Rank Fusion


def tokenize(text):
    return TOKEN.findall(text.lower())


class BM25:
    """Okapi BM25 over a list of chunks (standard library only)."""

    def __init__(self, chunks, k1=1.5, b=0.75):
        self.chunks = chunks
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenize(c["text"])) for c in chunks]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg_length = sum(self.lengths) / len(self.lengths)
        doc_freq = Counter(term for d in self.docs for term in d)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in doc_freq.items()}

    def score(self, query_terms, i):
        doc, length = self.docs[i], self.lengths[i]
        total = 0.0
        for term in query_terms:
            if term not in doc:
                continue
            tf = doc[term]
            norm = tf + self.k1 * (1 - self.b + self.b * length / self.avg_length)
            total += self.idf[term] * tf * (self.k1 + 1) / norm
        return total

    def search(self, query, candidates, k):
        """Rank the candidate chunk indexes for a query; returns [(index, score)]."""
        terms = tokenize(query)
        scored = [(i, self.score(terms, i)) for i in candidates]
        scored = [s for s in scored if s[1] > 0]
        return sorted(scored, key=lambda s: -s[1])[:k]


class DenseRetriever:
    """Plug-in: embedding search. Set up once the team picks a model."""

    def search(self, query, candidates, k):
        raise NotImplementedError


class Reranker:
    """Plug-in: re-scores the fused candidates. Set up once the team picks a model."""

    def rerank(self, query, chunks):
        raise NotImplementedError


def reciprocal_rank_fusion(rankings, k=RRF_K):
    """Merge several ranked lists of chunk indexes.

    Each chunk gets sum(1 / (k + rank)) over the lists it appears in
    (rank starts at 1). Chunks that rank high in several lists rise to the top.
    """
    scores = Counter()
    for ranking in rankings:
        for rank, index in enumerate(ranking, start=1):
            scores[index] += 1 / (k + rank)
    return [index for index, _ in scores.most_common()]


class HybridRetriever:
    def __init__(self, strategy="section", dense=None, reranker=None, candidates=20):
        self.chunks = build_chunks(strategy)
        self.bm25 = BM25(self.chunks)
        self.dense = dense
        self.reranker = reranker
        self.candidates = candidates

    def search(self, query, k=5, allowed_access=("public", "internal")):
        """Return the top k chunks for a query.

        allowed_access filters by the document's access_level. Internal
        documents may guide the agent's decisions, but the caller must not
        quote them to customers (see data_inventory.md).
        """
        pool = [i for i, c in enumerate(self.chunks) if c["access_level"] in allowed_access]
        rankings = [[i for i, _ in self.bm25.search(query, pool, self.candidates)]]
        if self.dense is not None:
            rankings.append([i for i, _ in self.dense.search(query, pool, self.candidates)])
        fused = reciprocal_rank_fusion(rankings)[: self.candidates]
        results = [self.chunks[i] for i in fused]
        if self.reranker is not None:
            results = self.reranker.rerank(query, results)
        return results[:k]


def main():
    parser = argparse.ArgumentParser(description="Search the store documents (W3.3)")
    parser.add_argument("query")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--strategy", choices=["section", "window"], default="section")
    parser.add_argument("--public-only", action="store_true", help="Exclude internal documents")
    args = parser.parse_args()

    access = ("public",) if args.public_only else ("public", "internal")
    retriever = HybridRetriever(strategy=args.strategy)
    print("Mode: BM25 only (dense retriever and reranker not set up yet)\n")
    for rank, chunk in enumerate(retriever.search(args.query, k=args.k, allowed_access=access), start=1):
        first_line = chunk["text"].splitlines()[0]
        print(f"{rank}. [{chunk['chunk_id']}] ({chunk['access_level']}) {first_line}")


if __name__ == "__main__":
    main()
