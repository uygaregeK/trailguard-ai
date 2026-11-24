"""Hybrid retriever for the store documents (W3.3).

Pipeline for one query:
    BM25 (keywords, exact IDs) ─┐
                                ├─ Reciprocal Rank Fusion ─> reranker ─> top k chunks
    Dense embeddings (meaning) ─┘

Models (team decision, W3): both are multilingual, because the documents are
in English and many customers write in Turkish. Both run locally with
sentence-transformers: no API key, no cost, same results on every run.

    embeddings : sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
    reranker   : cross-encoder/mmarco-mMiniLMv2-L12-H384-v1

The first run downloads them (about 0.5 GB in total) into the Hugging Face
cache. With dense=None and reranker=None the pipeline is BM25 only, which is
the baseline arm of the retrieval ablation.

    python3 src/retriever.py "can I return muddy shoes" --k 5              # BM25 only
    python3 src/retriever.py "Speedcross'u evde denedim, iade?" --mode hybrid_rerank
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

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_RERANKER_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
MODES = ("bm25", "dense", "hybrid", "hybrid_rerank")


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


def _load_sentence_transformers():
    try:
        import sentence_transformers
    except ImportError as exc:
        raise ImportError(
            f"sentence-transformers is not installed for {sys.executable}. "
            "Run: pip install -r requirements.txt"
        ) from exc
    return sentence_transformers


class DenseRetriever:
    """Embedding search (meaning, works across Turkish and English).

    Load the model once and reuse it: HybridRetriever calls index(chunks),
    which embeds that retriever's chunks and returns a searchable index.
    """

    def __init__(self, model_name=DEFAULT_EMBEDDING_MODEL, model=None):
        self.model_name = model_name
        self.model = model or _load_sentence_transformers().SentenceTransformer(model_name)

    def embed(self, texts):
        return self.model.encode(list(texts), normalize_embeddings=True, convert_to_numpy=True)

    def index(self, chunks):
        return DenseIndex(self, self.embed(c["text"] for c in chunks))


class DenseIndex:
    def __init__(self, dense, embeddings):
        self.dense = dense
        self.embeddings = embeddings  # one unit-length row per chunk

    def search(self, query, candidates, k):
        """Rank the candidate chunk indexes by cosine similarity; returns [(index, score)]."""
        query_vector = self.dense.embed([query])[0]
        scored = [(i, float(self.embeddings[i] @ query_vector)) for i in candidates]
        return sorted(scored, key=lambda s: -s[1])[:k]


class Reranker:
    """Cross-encoder that reads the query and each candidate chunk together."""

    def __init__(self, model_name=DEFAULT_RERANKER_MODEL, model=None, max_length=512):
        self.model_name = model_name
        self.model = model or _load_sentence_transformers().CrossEncoder(model_name, max_length=max_length)

    def rerank(self, query, chunks):
        """Return the chunks sorted by relevance, each with a "rerank_score"."""
        if not chunks:
            return []
        scores = self.model.predict([(query, c["text"]) for c in chunks])
        rescored = [{**c, "rerank_score": float(s)} for c, s in zip(chunks, scores)]
        return sorted(rescored, key=lambda c: -c["rerank_score"])


def reciprocal_rank_fusion(rankings, k=RRF_K):
    """Merge several ranked lists of chunk indexes.

    Each chunk gets sum(1 / (k + rank)) over the lists it appears in
    (rank starts at 1). Chunks that rank high in several lists rise to the top.
    """
    scores = Counter()
    for ranking in rankings:
        for rank, index in enumerate(ranking, start=1):
            scores[index] += 1 / (k + rank)
    return scores.most_common()  # [(index, fused score)], best first


class HybridRetriever:
    def __init__(self, strategy="section", dense=None, reranker=None, candidates=20, use_bm25=True):
        self.strategy = strategy
        self.chunks = build_chunks(strategy)
        self.bm25 = BM25(self.chunks) if use_bm25 else None
        self.dense_index = dense.index(self.chunks) if dense is not None else None
        self.reranker = reranker
        self.candidates = candidates
        if self.bm25 is None and self.dense_index is None:
            raise ValueError("Need BM25, a dense retriever, or both")

    @classmethod
    def from_mode(cls, mode, strategy="section", candidates=20, dense=None, reranker=None):
        """Build one arm of the ablation: bm25, dense, hybrid or hybrid_rerank.

        Pass already-loaded dense/reranker objects to avoid loading the models
        again for every strategy.
        """
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if mode == "bm25":
            return cls(strategy, candidates=candidates)
        dense = dense or DenseRetriever()
        if mode == "dense":
            return cls(strategy, dense=dense, candidates=candidates, use_bm25=False)
        if mode == "hybrid":
            return cls(strategy, dense=dense, candidates=candidates)
        return cls(strategy, dense=dense, reranker=reranker or Reranker(), candidates=candidates)

    @property
    def mode(self):
        if self.dense_index is None:
            return "bm25"
        if self.bm25 is None:
            return "dense"
        return "hybrid_rerank" if self.reranker is not None else "hybrid"

    def search(self, query, k=5, allowed_access=("public", "internal")):
        """Return the top k chunks for a query.

        allowed_access filters by the document's access_level. Internal
        documents may guide the agent's decisions, but the caller must not
        quote them to customers (see data_inventory.md).

        Each returned chunk is a copy with a "score": the reranker's score when
        a reranker is set, otherwise the fusion (RRF) score. Higher is better.
        """
        pool = [i for i, c in enumerate(self.chunks) if c["access_level"] in allowed_access]
        rankings = []
        if self.bm25 is not None:
            rankings.append([i for i, _ in self.bm25.search(query, pool, self.candidates)])
        if self.dense_index is not None:
            rankings.append([i for i, _ in self.dense_index.search(query, pool, self.candidates)])
        fused = reciprocal_rank_fusion(rankings)[: self.candidates]
        results = [{**self.chunks[i], "score": score} for i, score in fused]
        if self.reranker is not None:
            results = [{**c, "score": c["rerank_score"]} for c in self.reranker.rerank(query, results)]
        return results[:k]


def main():
    parser = argparse.ArgumentParser(description="Search the store documents (W3.3)")
    parser.add_argument("query")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--strategy", choices=["section", "window"], default="section")
    parser.add_argument("--mode", choices=MODES, default="bm25")
    parser.add_argument("--public-only", action="store_true", help="Exclude internal documents")
    args = parser.parse_args()

    access = ("public",) if args.public_only else ("public", "internal")
    retriever = HybridRetriever.from_mode(args.mode, strategy=args.strategy)
    print(f"Mode: {retriever.mode} | strategy: {args.strategy}\n")
    for rank, chunk in enumerate(retriever.search(args.query, k=args.k, allowed_access=access), start=1):
        first_line = chunk["text"].splitlines()[0]
        print(f"{rank}. [{chunk['chunk_id']}] ({chunk['access_level']}) score={chunk['score']:.3f}  {first_line}")


if __name__ == "__main__":
    main()
