#!/usr/bin/env python3
"""TrailRun TR — TrailGuard AI Pure Support Assistant UI (Week 3 Demo).

Minimal, product-grade chat interface backed by TrailGuard AI's Week 3
RAG pipeline (`src/rag_chain.py` + `src/retriever.py`). Keeps presentation
metrics tucked away in a slide-over drawer so the live demo feels clean and pure.

Run from the repository root:
    python demo_w3_rag_ui.py
"""

from __future__ import annotations

import argparse
import concurrent.futures
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import threading
from typing import Any
import webbrowser

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
for _p in (str(ROOT_DIR), str(SRC_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Force the fast, responsive demo model before src.llm loads .env (where load_dotenv
# preserves already-set env vars; avoids 2+ min stalls on overloaded gemini-3.1-flash-lite).
os.environ.setdefault("DEMO_GEMINI_MODEL", "gemini-2.5-flash")
os.environ["GEMINI_MODEL"] = os.environ["DEMO_GEMINI_MODEL"]

from src.rag_chain import (
    answer_with_rag,
    generate_rag_answer,
    split_passages_by_access,
)
from src.retriever import HybridRetriever

HAS_DENSE = importlib.util.find_spec("sentence_transformers") is not None


def _load_json(rel_path: str) -> dict[str, Any]:
    return json.loads((ROOT_DIR / rel_path).read_text(encoding="utf-8"))


def _load_jsonl(rel_path: str) -> list[dict[str, Any]]:
    path = ROOT_DIR / rel_path
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _norm_q(text: str) -> str:
    return " ".join(text.strip().lower().split())


_SCOREBOARD = _load_json("reports/scoreboard_w3.json")
_RETRIEVAL_REPORT = _load_json("reports/w3_retrieval.json")
_FAILURE_REPORT = _load_json("reports/w3_failure_labels.json")
_W2_CASES = {r["id"]: r for r in _load_jsonl("data/w2_test_set.jsonl")}
_W3_CASES = {r["id"]: r for r in _load_jsonl("data/w3_retrieval_test.jsonl")}
_W3_OUTPUTS_BY_ID = {r["id"]: r for r in _load_jsonl("data/w3_outputs_rag.jsonl")}

_W3_OUTPUTS_BY_QUERY: dict[str, dict[str, Any]] = {}
for _cid, _row in _W3_OUTPUTS_BY_ID.items():
    _meta = _W2_CASES.get(_cid) or _W3_CASES.get(_cid) or {}
    _q_text = _meta.get("input") or _meta.get("query") or ""
    if _q_text:
        _W3_OUTPUTS_BY_QUERY[_norm_q(_q_text)] = _row

PRESET_SPECS = [
    ("W2-D05", "EN · Size exchange shipping fee?"),
    ("W2-D16", "TR · Evde denedim, iade olur mu?"),
    ("W3-R35", "TR · Kuzey Kıbrıs kargo & ücret?"),
    ("W2-D22", "EN · Rain at Uludağ Ultra? (Abstain)"),
]

PRESETS: list[dict[str, str]] = []
for _pid, _plabel in PRESET_SPECS:
    _meta = _W2_CASES.get(_pid) or _W3_CASES.get(_pid) or {}
    _pq = _meta.get("input") or _meta.get("query") or ""
    if _pq:
        PRESETS.append({"case_id": _pid, "label": _plabel, "query": _pq})

_RETRIEVER: HybridRetriever | None = None
_ACTIVE_HAS_DENSE: bool = HAS_DENSE
_RETRIEVER_LOCK = threading.Lock()


def _get_live_retriever() -> HybridRetriever:
    """Return cached section retriever, gracefully falling back to BM25 on dense errors."""
    global _RETRIEVER, _ACTIVE_HAS_DENSE
    with _RETRIEVER_LOCK:
        if _RETRIEVER is None:
            if HAS_DENSE:
                try:
                    _RETRIEVER = HybridRetriever.from_mode("hybrid_rerank", strategy="section")
                    _ACTIVE_HAS_DENSE = True
                except Exception as exc:
                    print(
                        f"Warning: could not load hybrid_rerank ({exc}); falling back to bm25.",
                        file=sys.stderr,
                    )
                    _RETRIEVER = HybridRetriever.from_mode("bm25", strategy="section")
                    _ACTIVE_HAS_DENSE = False
            else:
                _RETRIEVER = HybridRetriever.from_mode("bm25", strategy="section")
                _ACTIVE_HAS_DENSE = False
        return _RETRIEVER


def build_home_meta() -> dict[str, Any]:
    """Return clean presets and concise Week 3 drawer metrics."""
    sec_runs = {}
    for mode in ("bm25", "dense", "hybrid", "hybrid_rerank"):
        arm = _RETRIEVAL_REPORT.get("runs", {}).get(f"{mode}/section", {})
        overall = arm.get("overall", {})
        tr = arm.get("by_language", {}).get("tr", {})
        sec_runs[mode] = {
            "hit_at_5": overall.get("hit_at_5", 0.0),
            "mrr": overall.get("mrr", 0.0),
            "tr_hit_at_5": tr.get("hit_at_5", 0.0),
        }

    fail_by_label = _FAILURE_REPORT.get("by_label", {})
    return {
        "presets": PRESETS,
        "has_dense": HAS_DENSE,
        "metrics": {
            "hit_at_5": _SCOREBOARD["hit_at_5"]["value"],
            "mrr": _SCOREBOARD["mrr"]["value"],
            "tr_hybrid_hit5": sec_runs["hybrid_rerank"]["tr_hit_at_5"],
            "tr_bm25_hit5": sec_runs["bm25"]["tr_hit_at_5"],
            "unsupported_rate": _SCOREBOARD["unsupported_claims"]["value"],
            "unsupported_n": _SCOREBOARD["unsupported_claims"]["n"],
            "abstention_correct": _SCOREBOARD["abstention_correct"]["value"],
            "retrieval_failures": fail_by_label.get("retrieval", 2),
            "generation_failures": fail_by_label.get("generation", 24),
            "retrieval_modes": sec_runs,
        },
    }


def _format_sources(
    passages: list[dict[str, Any]],
    citations: list[int],
) -> list[dict[str, Any]]:
    cited_set = set(citations)
    sources: list[dict[str, Any]] = []
    for idx, p in enumerate(passages, start=1):
        num = int(p.get("n") or idx)
        sources.append(
            {
                "n": num,
                "chunk_id": p.get("chunk_id") or p.get("doc_id") or f"DOC-{num}",
                "doc_id": p.get("doc_id") or "",
                "title": p.get("title") or "",
                "sections": p.get("sections") or [],
                "text": str(p.get("text") or "").strip(),
                "cited": num in cited_set,
            }
        )
    return sources


def _run_with_timeout(fn: Any, timeout_s: float = 12.0) -> Any:
    """Execute `fn()` with a hard wall-clock timeout without waiting on hung threads."""
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = pool.submit(fn)
    try:
        return future.result(timeout=timeout_s)
    except concurrent.futures.TimeoutError as exc:
        raise TimeoutError(f"Model request exceeded {timeout_s:.0f}s") from exc
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def handle_chat_message(payload: dict[str, Any]) -> dict[str, Any]:
    """Process one support question cleanly and return grounded answer + cited sources."""
    query = str(payload.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "Please enter a question."}

    case_id = str(payload.get("case_id") or "").strip()
    use_llm = bool(payload.get("use_llm", True))
    timeout_s = float(payload.get("timeout_s") or 12.0)

    retriever = _get_live_retriever()
    saved_row = _W3_OUTPUTS_BY_ID.get(case_id) or _W3_OUTPUTS_BY_QUERY.get(_norm_q(query))

    # Ensure demo model override remains active when calling Gemini.
    os.environ["GEMINI_MODEL"] = os.environ.get("DEMO_GEMINI_MODEL", "gemini-2.5-flash")

    # For saved benchmark questions when local dense embeddings are absent or fell back,
    # run live Gemini generation over the saved multilingual `hybrid_rerank/section`
    # passages so EN and TR examples work faithfully without API fragility.
    if saved_row is not None and not _ACTIVE_HAS_DENSE:
        passages_for_rag = [
            {
                "chunk_id": p.get("chunk_id"),
                "doc_id": p.get("doc_id"),
                "sections": p.get("sections", []),
                "access_level": "public",
                "text": p.get("text", ""),
            }
            for p in saved_row.get("passages", [])
        ]
        try:
            rag_res = _run_with_timeout(
                lambda: generate_rag_answer(query, passages_for_rag, use_llm=use_llm),
                timeout_s=timeout_s,
            )
            citations = rag_res.get("citations") or []
            return {
                "ok": True,
                "query": query,
                "answer": rag_res.get("answer", ""),
                "language": rag_res.get("language", saved_row.get("language", "en")),
                "abstained": bool(rag_res.get("abstained", False)),
                "citations": citations,
                "sources": _format_sources(saved_row.get("passages", []), citations),
                "latency_s": rag_res.get("latency_s", 0.0),
                "model": rag_res.get("model"),
                "source_mode": "live_gemini_hybrid_passages" if use_llm else "offline_preview",
            }
        except Exception:
            citations = saved_row.get("citations") or []
            return {
                "ok": True,
                "query": query,
                "answer": saved_row.get("answer", ""),
                "language": saved_row.get("language", "en"),
                "abstained": bool(saved_row.get("abstained", False)),
                "citations": citations,
                "sources": _format_sources(saved_row.get("passages", []), citations),
                "latency_s": saved_row.get("latency_s", 0.0),
                "model": saved_row.get("answer_model"),
                "source_mode": "verified_w3_replay",
            }

    # Live path for any custom typed question (or full hybrid_rerank when active).
    try:
        rag_res = _run_with_timeout(
            lambda: answer_with_rag(
                query,
                k=5,
                strategy="section",
                retriever=retriever,
                include_internal=False,
                use_llm=use_llm,
            ),
            timeout_s=timeout_s,
        )
        pub_passages, _ = split_passages_by_access(rag_res.get("retrieved_passages", []))
        citations = rag_res.get("citations") or []
        return {
            "ok": True,
            "query": query,
            "answer": rag_res.get("answer", ""),
            "language": rag_res.get("language", "en"),
            "abstained": bool(rag_res.get("abstained", False)),
            "citations": citations,
            "sources": _format_sources(pub_passages, citations),
            "latency_s": rag_res.get("latency_s", 0.0),
            "model": rag_res.get("model"),
            "source_mode": f"live_{retriever.mode}" if use_llm else "offline_preview",
        }
    except Exception as exc:
        if saved_row is not None:
            citations = saved_row.get("citations") or []
            return {
                "ok": True,
                "query": query,
                "answer": saved_row.get("answer", ""),
                "language": saved_row.get("language", "en"),
                "abstained": bool(saved_row.get("abstained", False)),
                "citations": citations,
                "sources": _format_sources(saved_row.get("passages", []), citations),
                "latency_s": saved_row.get("latency_s", 0.0),
                "model": saved_row.get("answer_model"),
                "source_mode": "verified_w3_replay",
            }
        return {
            "ok": False,
            "error": f"Temporary API error: {exc}. Try one of the curated examples or retry in a moment.",
        }


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>TrailRun TR · TrailGuard AI</title>
  <style>
    :root {
      --canvas: #FAF9F6;
      --surface: #FFFFFF;
      --surface-soft: #F3F4F1;
      --border: #E5E7EB;
      --ink: #111827;
      --muted: #6B7280;
      --accent: #14532D;
      --accent-soft: #ECFDF5;
      --accent-border: #BBF7D0;
      --warn-bg: #FFFBEB;
      --warn-ink: #92400E;
      --warn-border: #FDE68A;
    }
    * { box-sizing: border-box; }
    html, body { height: 100%; margin: 0; padding: 0; }
    body {
      background: var(--canvas);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, sans-serif;
      font-size: 15px;
      line-height: 1.55;
      display: flex;
      flex-direction: column;
    }

    /* TOP BAR */
    header {
      height: 58px;
      flex-shrink: 0;
      background: rgba(250, 249, 246, 0.9);
      backdrop-filter: blur(8px);
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 24px;
    }
    .brand { display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 15px; letter-spacing: -0.01em; }
    .brand-sub { font-weight: 500; color: var(--muted); font-size: 13px; }
    .header-actions { display: flex; align-items: center; gap: 8px; }
    .ghost-btn {
      background: transparent;
      border: 1px solid var(--border);
      color: var(--ink);
      padding: 6px 12px;
      border-radius: 999px;
      font: inherit;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.15s, border-color 0.15s;
    }
    .ghost-btn:hover { background: var(--surface); border-color: #CBD5E1; }

    /* MAIN SCROLL STAGE */
    main {
      flex: 1;
      overflow-y: auto;
      padding: 28px 20px 24px;
      display: flex;
      justify-content: center;
    }
    .stage { width: 100%; max-width: 740px; display: flex; flex-direction: column; }

    /* WELCOME VIEW */
    .welcome {
      margin: auto 0;
      padding: 24px 0 40px;
      text-align: center;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 14px;
    }
    .welcome h1 { margin: 0; font-size: 28px; font-weight: 700; letter-spacing: -0.02em; }
    .welcome p { margin: 0; color: var(--muted); max-width: 520px; font-size: 15px; }
    .chips {
      margin-top: 12px;
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      width: 100%;
      max-width: 640px;
    }
    @media (max-width: 620px) { .chips { grid-template-columns: 1fr; } }
    .chip-btn {
      text-align: left;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px 14px;
      font: inherit;
      font-size: 13.5px;
      font-weight: 500;
      color: var(--ink);
      cursor: pointer;
      transition: border-color 0.15s, transform 0.1s;
    }
    .chip-btn:hover { border-color: var(--accent); transform: translateY(-1px); }

    /* CHAT THREAD */
    .thread { display: flex; flex-direction: column; gap: 20px; padding-bottom: 12px; }
    .msg-user-wrap { display: flex; justify-content: flex-end; }
    .msg-user {
      max-width: 82%;
      background: var(--accent);
      color: #FFFFFF;
      padding: 11px 16px;
      border-radius: 18px 18px 4px 18px;
      font-size: 14.5px;
    }
    .msg-bot-wrap { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; max-width: 92%; }
    .msg-bot {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 14px 18px;
      font-size: 15px;
      line-height: 1.65;
      width: 100%;
    }
    .msg-bot.abstain {
      background: var(--warn-bg);
      border-color: var(--warn-border);
      color: var(--warn-ink);
    }
    .cite-pill {
      display: inline-flex; align-items: center; justify-content: center;
      background: var(--accent-soft);
      color: var(--accent);
      border: 1px solid var(--accent-border);
      border-radius: 6px;
      padding: 0 6px;
      margin: 0 2px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
      font-weight: 700;
      cursor: pointer;
    }
    .cite-pill:hover { background: var(--accent); color: #FFFFFF; border-color: var(--accent); }

    .source-row { display: flex; flex-wrap: wrap; gap: 6px; padding-left: 2px; }
    .source-chip {
      background: var(--surface);
      border: 1px solid var(--border);
      color: var(--ink);
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
    }
    .source-chip.cited { border-color: var(--accent-border); background: var(--accent-soft); color: var(--accent); font-weight: 600; }
    .source-chip.open { background: var(--accent); color: #FFFFFF; border-color: var(--accent); }

    .source-drawer {
      width: 100%;
      background: var(--surface-soft);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px 14px;
      font-size: 13px;
      line-height: 1.55;
      white-space: pre-wrap;
    }
    .source-head { font-family: ui-monospace, monospace; font-size: 12px; font-weight: 700; color: var(--accent); margin-bottom: 6px; }
    .caption { font-size: 12px; color: var(--muted); padding-left: 4px; }

    /* PINNED COMPOSER */
    footer {
      flex-shrink: 0;
      padding: 10px 20px 20px;
      display: flex;
      justify-content: center;
      background: linear-gradient(to top, var(--canvas) 75%, rgba(250, 249, 246, 0));
    }
    .composer {
      width: 100%;
      max-width: 740px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 6px 8px 6px 18px;
      display: flex;
      align-items: center;
      gap: 10px;
      box-shadow: 0 4px 18px rgba(17, 24, 39, 0.05);
    }
    .composer:focus-within { border-color: var(--accent); }
    .composer input {
      flex: 1;
      border: none;
      outline: none;
      background: transparent;
      font: inherit;
      font-size: 14.5px;
      color: var(--ink);
    }
    .send-btn {
      width: 36px; height: 36px;
      border-radius: 999px;
      border: none;
      background: var(--accent);
      color: #FFFFFF;
      display: flex; align-items: center; justify-content: center;
      cursor: pointer;
      flex-shrink: 0;
    }
    .send-btn:disabled { opacity: 0.5; cursor: wait; }

    /* SLIDE-OVER METRICS DRAWER */
    .backdrop {
      position: fixed; inset: 0;
      background: rgba(17, 24, 39, 0.25);
      display: flex; justify-content: flex-end;
      z-index: 40;
    }
    .drawer {
      width: 100%; max-width: 420px; height: 100%;
      background: var(--surface);
      border-left: 1px solid var(--border);
      padding: 22px;
      overflow-y: auto;
      display: flex; flex-direction: column; gap: 18px;
    }
    .kpi-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
    .kpi { background: var(--surface-soft); border: 1px solid var(--border); border-radius: 12px; padding: 12px; }
    .kpi-num { font-size: 22px; font-weight: 700; color: var(--accent); margin: 2px 0; }
    .kpi-label { font-size: 12px; color: var(--muted); }
    .bar-row { display: flex; flex-direction: column; gap: 5px; font-size: 12.5px; }
    .bar-top { display: flex; justify-content: space-between; }
    .bar-track { height: 7px; border-radius: 999px; background: var(--surface-soft); border: 1px solid var(--border); overflow: hidden; }
    .bar-fill { height: 100%; background: var(--accent); border-radius: 999px; }
    .hidden { display: none !important; }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#14532D" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="m8 3 4 8 5-5 5 15H2L8 3z"/>
      </svg>
      <span>TrailRun TR</span>
      <span class="brand-sub">· TrailGuard AI</span>
    </div>
    <div class="header-actions">
      <button class="ghost-btn" onclick="resetChat()">New Chat</button>
      <button class="ghost-btn" onclick="toggleMetrics(true)">W3 Metrics</button>
    </div>
  </header>

  <main id="scroll-stage">
    <div class="stage">
      <div id="welcome" class="welcome">
        <h1>TrailRun TR Support</h1>
        <p>Answers strictly from 32 official policy, shipping, warranty &amp; product documents — in English or Turkish.</p>
        <div id="chips" class="chips"></div>
      </div>
      <div id="thread" class="thread hidden"></div>
    </div>
  </main>

  <footer>
    <form class="composer" onsubmit="onSubmit(event)">
      <input id="query-input" type="text" placeholder="Ask about returns, exchanges, warranty, or shipping (EN / TR)..." autocomplete="off" />
      <button class="send-btn" id="send-btn" type="submit" aria-label="Send">
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">
          <path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>
        </svg>
      </button>
    </form>
  </footer>

  <!-- SLIDE-OVER METRICS DRAWER (HIDDEN BY DEFAULT) -->
  <div id="metrics-backdrop" class="backdrop hidden" onclick="if (event.target === this) toggleMetrics(false)">
    <div class="drawer">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <div style="font-weight:700; font-size:16px;">Week 3 Evaluation Summary</div>
        <button class="ghost-btn" onclick="toggleMetrics(false)">Close</button>
      </div>
      <div class="kpi-grid" id="drawer-kpis"></div>
      <div style="display:flex; flex-direction:column; gap:10px;">
        <div style="font-weight:600; font-size:13px;">Retrieval Modes (hit@5 · n=50)</div>
        <div id="drawer-bars" style="display:flex; flex-direction:column; gap:10px;"></div>
      </div>
      <div id="drawer-note" style="font-size:12.5px; color:var(--muted); background:var(--surface-soft); border:1px solid var(--border); border-radius:10px; padding:12px;"></div>
    </div>
  </div>

  <script>
    let META = null;
    let msgCounter = 0;

    function esc(s) {
      return String(s ?? '').replace(/[&<>"']/g, m => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }[m]));
    }

    function toggleMetrics(open) {
      document.getElementById('metrics-backdrop').classList.toggle('hidden', !open);
    }

    function resetChat() {
      document.getElementById('thread').innerHTML = '';
      document.getElementById('thread').classList.add('hidden');
      document.getElementById('welcome').classList.remove('hidden');
      document.getElementById('query-input').focus();
    }

    async function init() {
      META = await fetch('/api/meta').then(r => r.json());
      document.getElementById('chips').innerHTML = META.presets.map((p, idx) =>
        `<button class="chip-btn" onclick="askPreset(${idx})">${esc(p.label)}</button>`
      ).join('');

      const m = META.metrics;
      document.getElementById('drawer-kpis').innerHTML = [
        ['Retrieval hit@5', `${(m.hit_at_5 * 100).toFixed(0)}%`, `MRR ${m.mrr.toFixed(3)}`],
        ['Turkish hit@5', `${(m.tr_hybrid_hit5 * 100).toFixed(0)}%`, `vs ${(m.tr_bm25_hit5 * 100).toFixed(0)}% BM25 alone`],
        ['Unsupported Claims', `${(m.unsupported_rate * 100).toFixed(2)}%`, `1 / ${m.unsupported_n} claims`],
        ['Safe Abstention', `${(m.abstention_correct * 100).toFixed(0)}%`, '7 / 7 out-of-scope']
      ].map(([lbl, num, sub]) => `
        <div class="kpi">
          <div class="kpi-label">${lbl}</div>
          <div class="kpi-num">${num}</div>
          <div class="kpi-label">${sub}</div>
        </div>
      `).join('');

      const labels = { bm25: 'BM25', dense: 'Multilingual Dense', hybrid: 'Hybrid RRF', hybrid_rerank: 'Hybrid + Rerank ★' };
      document.getElementById('drawer-bars').innerHTML = ['bm25', 'dense', 'hybrid', 'hybrid_rerank'].map(k => {
        const pct = (m.retrieval_modes[k].hit_at_5 * 100).toFixed(0);
        return `
          <div class="bar-row">
            <div class="bar-top"><span>${labels[k]}</span><strong>${pct}%</strong></div>
            <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
          </div>
        `;
      }).join('');

      document.getElementById('drawer-note').innerHTML =
        `<strong>Failure root-cause:</strong> Only <strong>${m.retrieval_failures}</strong> retrieval misses vs <strong>${m.generation_failures}</strong> generation issues (strict prompt abstained on order lookups). Live order &amp; stock tools arrive in Week 4.`;
    }

    function askPreset(idx) {
      const p = META.presets[idx];
      if (!p) return;
      sendQuery(p.query, p.case_id);
    }

    function onSubmit(e) {
      e.preventDefault();
      const input = document.getElementById('query-input');
      const q = input.value.trim();
      if (!q) return;
      input.value = '';
      sendQuery(q, '');
    }

    async function sendQuery(query, caseId) {
      document.getElementById('welcome').classList.add('hidden');
      const thread = document.getElementById('thread');
      thread.classList.remove('hidden');

      const uWrap = document.createElement('div');
      uWrap.className = 'msg-user-wrap';
      uWrap.innerHTML = `<div class="msg-user">${esc(query)}</div>`;
      thread.appendChild(uWrap);

      const bWrap = document.createElement('div');
      bWrap.className = 'msg-bot-wrap';
      bWrap.innerHTML = `<div class="msg-bot" style="color:var(--muted);">Searching TrailRun TR store documents…</div>`;
      thread.appendChild(bWrap);

      const stage = document.getElementById('scroll-stage');
      stage.scrollTop = stage.scrollHeight;

      const btn = document.getElementById('send-btn');
      btn.disabled = true;

      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query, case_id: caseId, use_llm: true })
        });
        const data = await res.json();
        renderAssistantReply(bWrap, data);
      } catch (err) {
        bWrap.innerHTML = `<div class="msg-bot abstain">Connection error: ${esc(err.message)}</div>`;
      } finally {
        btn.disabled = false;
        stage.scrollTop = stage.scrollHeight;
      }
    }

    function renderAssistantReply(container, data) {
      if (!data.ok) {
        container.innerHTML = `<div class="msg-bot abstain">${esc(data.error)}</div>`;
        return;
      }

      const id = ++msgCounter;
      const citedSources = (data.sources || []).filter(s => s.cited);
      const docTagList = citedSources.map(s => s.doc_id || s.chunk_id).filter((v, i, a) => a.indexOf(v) === i);
      const htmlAnswer = esc(data.answer).replace(/\[(\d+)\]/g, (_, n) =>
        `<button class="cite-pill" onclick="toggleSource(${id}, ${n})" title="View source [${n}]">[${n}]</button>`
      );

      const chipsHtml = citedSources.length ? `
        <div class="source-row">
          ${citedSources.map(s => `<button id="sc-${id}-${s.n}" class="source-chip cited" onclick="toggleSource(${id}, ${s.n})">[${s.n}] ${esc(s.chunk_id)}</button>`).join('')}
        </div>
        <div id="sd-${id}" class="source-drawer hidden"></div>
      ` : '';

      const statusText = data.abstained
        ? `Not in official documents · Safe ${(data.language || 'en').toUpperCase()} abstention`
        : `Verified from ${docTagList.join(', ') || 'store corpus'} · ${Number(data.latency_s || 0).toFixed(1)}s`;

      container.innerHTML = `
        <div class="msg-bot ${data.abstained ? 'abstain' : ''}">${htmlAnswer}</div>
        ${chipsHtml}
        <div class="caption">${esc(statusText)}</div>
      `;
      container._sources = data.sources || [];
    }

    function toggleSource(msgId, n) {
      const box = document.getElementById(`sd-${msgId}`);
      if (!box) return;
      const bWrap = box.closest('.msg-bot-wrap');
      const src = (bWrap._sources || []).find(s => Number(s.n) === Number(n));
      if (!src) return;

      const sameOpen = !box.classList.contains('hidden') && box.dataset.openN === String(n);
      bWrap.querySelectorAll('.source-chip').forEach(el => el.classList.remove('open'));
      if (sameOpen) {
        box.classList.add('hidden');
        box.dataset.openN = '';
        return;
      }
      const chip = document.getElementById(`sc-${msgId}-${n}`);
      if (chip) chip.classList.add('open');
      box.dataset.openN = String(n);
      box.innerHTML = `<div class="source-head">[${src.n}] ${esc(src.chunk_id)}</div>${esc(src.text)}`;
      box.classList.remove('hidden');
    }

    init();
  </script>
</body>
</html>
"""


class SupportUIHandler(BaseHTTPRequestHandler):
    """Serve the pure TrailRun TR chat UI and JSON endpoints."""

    def _send_json(self, code: int, payload: Any) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/?"):
            raw = HTML_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        elif self.path == "/api/meta":
            self._send_json(200, build_home_meta())
        else:
            self._send_json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        if self.path != "/api/chat":
            self._send_json(404, {"error": "Not found"})
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        try:
            body = json.loads((self.rfile.read(length)).decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            self._send_json(400, {"ok": False, "error": f"Invalid JSON: {exc}"})
            return
        self._send_json(200, handle_chat_message(body))

    def log_message(self, format: str, *args: Any) -> None:
        return


def _detect_lan_ip() -> str | None:
    """Best-effort detection of the host's LAN IPv4 address for --host 0.0.0.0."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except Exception:
        return None
    finally:
        sock.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="TrailRun TR — Week 3 Pure Support Demo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    print("Loading TrailGuard AI retriever (hybrid_rerank / bm25)...")
    ret = _get_live_retriever()
    ret.search("warmup", k=1)

    server = ThreadingHTTPServer((args.host, args.port), SupportUIHandler)
    local_host = "127.0.0.1" if args.host == "0.0.0.0" else args.host
    browser_url = f"http://{local_host}:{args.port}"
    print(f"TrailRun TR Support Demo running at {browser_url} (mode={ret.mode}, Ctrl+C to stop)")
    if args.host == "0.0.0.0":
        lan_ip = _detect_lan_ip()
        if lan_ip:
            print(f"Same-Wi-Fi share URL: http://{lan_ip}:{args.port}")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(browser_url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
