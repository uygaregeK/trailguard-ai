import os
import time
from typing import Any, Dict
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError

load_dotenv()

# Standard paid-tier pricing for gemini-2.5-flash (USD per 1,000,000 tokens)
# Used for W1.6 token & cost math and scoreboard `cost_per_task_usd` tracking.
PRICE_PER_1M_INPUT_USD = 0.15
PRICE_PER_1M_OUTPUT_USD = 0.60

FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-3.1-flash-lite", "gemini-3.5-flash"]


def compute_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Compute exact USD cost from token counts using Module 1 formula."""
    return (
        input_tokens * PRICE_PER_1M_INPUT_USD
        + output_tokens * PRICE_PER_1M_OUTPUT_USD
    ) / 1_000_000.0


def call_llm(
    user_message: str,
    system_prompt: str,
    temperature: float = 0.0,
    model: str | None = None,
) -> Dict[str, Any]:
    """Call Google Gemini API with automatic rate-limit handling and return usage & cost."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Copy .env.example to .env and paste your Google AI Studio key."
        )

    primary_model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    candidates = [primary_model] + [m for m in FALLBACK_MODELS if m != primary_model]
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            api_version="v1beta",
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )

    last_err: Exception | None = None
    for attempt in range(3):
        for candidate_model in candidates:
            config_kwargs: Dict[str, Any] = {
                "system_instruction": system_prompt,
                "temperature": temperature,
            }
            if "2.5" in candidate_model:
                config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)

            try:
                t0 = time.perf_counter()
                response = client.models.generate_content(
                    model=candidate_model,
                    contents=user_message,
                    config=types.GenerateContentConfig(**config_kwargs),
                )
                latency_s = time.perf_counter() - t0

                usage = response.usage_metadata
                input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
                output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
                total_tokens = int(
                    getattr(usage, "total_token_count", input_tokens + output_tokens) or 0
                )

                return {
                    "model": candidate_model,
                    "temperature": temperature,
                    "output_text": response.text or "",
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "cost_usd": round(compute_cost_usd(input_tokens, output_tokens), 8),
                    "latency_s": round(latency_s, 4),
                }
            except APIError as err:
                last_err = err
                if err.code in (429, 503):
                    continue
                raise
        time.sleep(5 * (attempt + 1))

    raise RuntimeError(f"All Gemini candidate models rate-limited: {last_err}")
