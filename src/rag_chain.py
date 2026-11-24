"""W3.4 — Grounded RAG Generation Chain with Numbered Citations & Abstention.

Connects Dilara's HybridRetriever (`src/retriever.py`) with `prompts/v3_rag.txt`
and `src/llm.py` (`call_llm` at temperature=0.0), enforcing:
  - Strict separation of `access_level: public` passages (`[1]..[N]`) from
    `access_level: internal` SOP guidance (never quoted or cited).
  - Post-generation validation of inline `[1]`, `[2]` citations with automatic retry.
  - Safe abstention using `FIXED_ABSTENTION_RESPONSE` on empty/low-confidence
    retrieval or persistent citation validation failure (never fabricating `[1]`).
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Any

_ROOT_DIR = Path(__file__).resolve().parent.parent
_SRC_DIR = _ROOT_DIR / "src"
for _path in (str(_ROOT_DIR), str(_SRC_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from src.llm import call_llm

RAG_PROMPT_PATH = _ROOT_DIR / "prompts" / "v3_rag.txt"

FIXED_ABSTENTION_RESPONSE = (
    "I cannot answer this from TrailRun TR's official policy and catalog documents. "
    "I am escalating your request to a human specialist."
)

CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def load_rag_system_prompt(prompt_path: Path = RAG_PROMPT_PATH) -> str:
    """Load the W3.4 RAG system prompt from disk."""
    return prompt_path.read_text(encoding="utf-8").strip()


def split_passages_by_access(
    passages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separate public citable passages from internal SOP passages."""
    public_passages: list[dict[str, Any]] = []
    internal_passages: list[dict[str, Any]] = []
    for passage in passages:
        if passage.get("access_level", "public") == "internal":
            internal_passages.append(passage)
        else:
            public_passages.append(passage)
    return public_passages, internal_passages


def _format_section_label(passage: dict[str, Any]) -> str:
    """Extract a concise section label from chunk metadata."""
    sections = passage.get("sections")
    if isinstance(sections, list) and sections:
        return ", ".join(str(s) for s in sections)
    section = passage.get("section")
    if section:
        return str(section)
    return ""


def format_numbered_passages(passages: list[dict[str, Any]]) -> str:
    """Format public retrieved chunks into numbered blocks [1]..[N] for citation."""
    if not passages:
        return ""
    blocks: list[str] = []
    for idx, passage in enumerate(passages, start=1):
        chunk_id = passage.get("chunk_id") or passage.get("id") or f"DOC-{idx}"
        doc_id = passage.get("doc_id") or chunk_id
        title = passage.get("title") or ""
        section = _format_section_label(passage)
        header_parts = [f"[{idx}]", f"chunk_id={chunk_id}", f"doc_id={doc_id}"]
        if title:
            header_parts.append(f"title={title}")
        if section:
            header_parts.append(f"section={section}")
        text = str(passage.get("text", "")).strip()
        blocks.append(f"{' | '.join(header_parts)}\n{text}")
    return "\n\n".join(blocks)


def _format_internal_guidance(internal_passages: list[dict[str, Any]]) -> str:
    """Format unnumbered internal guidance blocks for decision support only."""
    if not internal_passages:
        return ""
    blocks: list[str] = []
    for passage in internal_passages:
        doc_id = passage.get("doc_id") or passage.get("chunk_id") or "INTERNAL"
        title = passage.get("title") or ""
        text = str(passage.get("text", "")).strip()
        blocks.append(f"({doc_id} {title})\n{text}")
    return "\n\n".join(blocks)


def extract_citation_numbers(text: str) -> list[int]:
    """Return sorted unique integer citation indices `[n]` found in `text`."""
    return sorted({int(match) for match in CITATION_PATTERN.findall(text)})


def validate_citations(
    text: str,
    num_public_passages: int,
    internal_doc_ids: list[str] | None = None,
) -> tuple[bool, list[int], list[str]]:
    """Validate inline `[n]` citations (and ensure no internal doc IDs leak)."""
    stripped = text.strip()
    if stripped == FIXED_ABSTENTION_RESPONSE:
        return True, [], []

    citations = extract_citation_numbers(stripped)
    errors: list[str] = []

    if num_public_passages <= 0:
        errors.append("No public passages available to support a non-abstaining answer.")
    else:
        out_of_range = [c for c in citations if c < 1 or c > num_public_passages]
        if out_of_range:
            errors.append(
                f"Out-of-range citation(s) {out_of_range}; valid range is [1]..[{num_public_passages}]."
            )
        if not citations:
            errors.append(
                f"Missing inline [n] citations; cite supporting claims from [1]..[{num_public_passages}]."
            )

    if internal_doc_ids:
        lowered = stripped.lower()
        leaked = [doc_id for doc_id in internal_doc_ids if doc_id and doc_id.lower() in lowered]
        if leaked:
            errors.append(f"Response must not reference internal guidance IDs: {leaked}.")

    return len(errors) == 0, citations, errors


def _build_cited_passages(
    public_passages: list[dict[str, Any]],
    citations: list[int],
) -> list[dict[str, Any]]:
    """Map cited 1-based indices back to their source public passage metadata."""
    cited: list[dict[str, Any]] = []
    for idx in citations:
        if 1 <= idx <= len(public_passages):
            p = public_passages[idx - 1]
            cited.append(
                {
                    "index": idx,
                    "chunk_id": p.get("chunk_id"),
                    "doc_id": p.get("doc_id"),
                    "title": p.get("title"),
                    "sections": p.get("sections"),
                    "access_level": p.get("access_level", "public"),
                }
            )
    return cited


def _abstain_result(
    *,
    reason: str,
    citation_validation_failed: bool = False,
    validation_errors: list[str] | None = None,
    cost_usd: float = 0.0,
    latency_s: float = 0.0,
    total_tokens: int = 0,
    retries_used: int = 0,
    model: str | None = None,
    num_public_passages: int = 0,
    num_internal_passages: int = 0,
) -> dict[str, Any]:
    """Build a uniform abstention response dictionary."""
    return {
        "answer": FIXED_ABSTENTION_RESPONSE,
        "abstained": True,
        "abstention_reason": reason,
        "citations": [],
        "cited_passages": [],
        "citation_validation_failed": citation_validation_failed,
        "validation_errors": validation_errors or [],
        "num_public_passages": num_public_passages,
        "num_internal_passages": num_internal_passages,
        "retries_used": retries_used,
        "model": model,
        "cost_usd": round(cost_usd, 8),
        "latency_s": round(latency_s, 4),
        "total_tokens": total_tokens,
    }


def generate_rag_answer(
    query: str,
    retrieved_passages: list[dict[str, Any]],
    *,
    min_score_threshold: float | None = None,
    max_retries: int = 1,
    temperature: float = 0.0,
    use_llm: bool = True,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """Generate a citation-verified RAG answer from retrieved passages."""
    public_passages, internal_passages = split_passages_by_access(retrieved_passages)

    if not public_passages:
        return _abstain_result(
            reason="no_public_passages",
            num_public_passages=0,
            num_internal_passages=len(internal_passages),
        )

    if min_score_threshold is not None and "score" in public_passages[0]:
        top_score = float(public_passages[0]["score"])
        if top_score < min_score_threshold:
            return _abstain_result(
                reason=f"low_top_score ({top_score:.4f} < {min_score_threshold:.4f})",
                num_public_passages=len(public_passages),
                num_internal_passages=len(internal_passages),
            )

    if not use_llm:
        snippet = str(public_passages[0].get("text", "")).strip()
        first_line = snippet.splitlines()[0] if snippet else ""
        offline_answer = f"{first_line} [1]".strip()
        return {
            "answer": offline_answer,
            "abstained": False,
            "abstention_reason": None,
            "citations": [1],
            "cited_passages": _build_cited_passages(public_passages, [1]),
            "citation_validation_failed": False,
            "validation_errors": [],
            "num_public_passages": len(public_passages),
            "num_internal_passages": len(internal_passages),
            "retries_used": 0,
            "model": "offline-preview",
            "cost_usd": 0.0,
            "latency_s": 0.0,
            "total_tokens": 0,
        }

    prompt_text = system_prompt if system_prompt is not None else load_rag_system_prompt()
    formatted_public = format_numbered_passages(public_passages)
    formatted_internal = _format_internal_guidance(internal_passages)
    internal_doc_ids = sorted(
        {str(p["doc_id"]) for p in internal_passages if p.get("doc_id")}
    )

    base_user_message = (
        f"<customer_query>\n{query.strip()}\n</customer_query>\n\n"
        f"<public_passages>\n{formatted_public}\n</public_passages>"
    )
    if formatted_internal:
        base_user_message += (
            f"\n\n<internal_guidance>\n{formatted_internal}\n</internal_guidance>"
        )

    current_user_message = base_user_message
    total_cost_usd = 0.0
    total_latency_s = 0.0
    total_tokens = 0
    last_model: str | None = None
    last_errors: list[str] = []

    for attempt in range(max_retries + 1):
        res = call_llm(
            user_message=current_user_message,
            system_prompt=prompt_text,
            temperature=temperature,
        )
        total_cost_usd += float(res.get("cost_usd", 0.0) or 0.0)
        total_latency_s += float(res.get("latency_s", 0.0) or 0.0)
        total_tokens += int(res.get("total_tokens", 0) or 0)
        last_model = res.get("model")
        output_text = str(res.get("output_text", "")).strip()

        if output_text == FIXED_ABSTENTION_RESPONSE:
            return _abstain_result(
                reason="insufficient_evidence",
                citation_validation_failed=False,
                cost_usd=total_cost_usd,
                latency_s=total_latency_s,
                total_tokens=total_tokens,
                retries_used=attempt,
                model=last_model,
                num_public_passages=len(public_passages),
                num_internal_passages=len(internal_passages),
            )

        is_valid, citations, errors = validate_citations(
            output_text,
            num_public_passages=len(public_passages),
            internal_doc_ids=internal_doc_ids,
        )
        if is_valid:
            return {
                "answer": output_text,
                "abstained": False,
                "abstention_reason": None,
                "citations": citations,
                "cited_passages": _build_cited_passages(public_passages, citations),
                "citation_validation_failed": False,
                "validation_errors": [],
                "num_public_passages": len(public_passages),
                "num_internal_passages": len(internal_passages),
                "retries_used": attempt,
                "model": last_model,
                "cost_usd": round(total_cost_usd, 8),
                "latency_s": round(total_latency_s, 4),
                "total_tokens": total_tokens,
            }

        last_errors = errors
        current_user_message = (
            f"{base_user_message}\n\n"
            f"Your previous draft failed validation: {errors}. "
            f"Rewrite using ONLY inline citations [1]..[{len(public_passages)}] from `<public_passages>`, "
            f"never mention internal guidance, or reply with ONLY the exact abstention sentence."
        )

    return _abstain_result(
        reason="citation_validation_failed",
        citation_validation_failed=True,
        validation_errors=last_errors,
        cost_usd=total_cost_usd,
        latency_s=total_latency_s,
        total_tokens=total_tokens,
        retries_used=max_retries,
        model=last_model,
        num_public_passages=len(public_passages),
        num_internal_passages=len(internal_passages),
    )


def answer_with_rag(
    query: str,
    *,
    k: int = 5,
    strategy: str = "section",
    dense: Any = None,
    reranker: Any = None,
    candidates: int = 20,
    include_internal: bool = False,
    allowed_access: tuple[str, ...] | None = None,
    retriever: Any = None,
    min_score_threshold: float | None = None,
    max_retries: int = 1,
    temperature: float = 0.0,
    use_llm: bool = True,
) -> dict[str, Any]:
    """Retrieve passages via Dilara's HybridRetriever and generate a cited answer."""
    if retriever is None:
        from src.retriever import HybridRetriever

        retriever = HybridRetriever(
            strategy=strategy,
            dense=dense,
            reranker=reranker,
            candidates=candidates,
        )

    access = (
        allowed_access
        if allowed_access is not None
        else (("public", "internal") if include_internal else ("public",))
    )
    passages = retriever.search(query, k=k, allowed_access=access)

    result = generate_rag_answer(
        query=query,
        retrieved_passages=passages,
        min_score_threshold=min_score_threshold,
        max_retries=max_retries,
        temperature=temperature,
        use_llm=use_llm,
    )
    result["query"] = query
    result["retrieval"] = {
        "strategy": strategy,
        "k": k,
        "allowed_access": list(access),
        "num_retrieved": len(passages),
        "chunk_ids": [p.get("chunk_id") for p in passages],
    }
    result["retrieved_passages"] = passages
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Smoke-test W3.4 TrailGuard RAG chain")
    parser.add_argument("query", nargs="?", default=None, help="Optional customer query")
    parser.add_argument("--k", type=int, default=5, help="Number of passages to retrieve")
    parser.add_argument(
        "--strategy",
        choices=["section", "window"],
        default="section",
        help="Chunking strategy for HybridRetriever",
    )
    parser.add_argument(
        "--include-internal",
        action="store_true",
        help="Allow internal SOPs in retrieval (isolated into <internal_guidance>)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip live LLM calls and test retrieval + formatting offline",
    )
    args = parser.parse_args()

    queries = (
        [args.query]
        if args.query
        else [
            "What is the return window for unused trail running shoes, and is there a return shipping fee?",
            "Can you recommend the best painkillers for runner's knee tendinitis?",
        ]
    )
    for q in queries:
        out = answer_with_rag(
            q,
            k=args.k,
            strategy=args.strategy,
            include_internal=args.include_internal,
            use_llm=not args.offline,
        )
        summary = {k: v for k, v in out.items() if k != "retrieved_passages"}
        print(json.dumps(summary, indent=2, ensure_ascii=False))
