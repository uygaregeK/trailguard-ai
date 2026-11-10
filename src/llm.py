import os
from pathlib import Path
import time

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# Official Google AI Studio Paid-Tier Pricing (USD per 1,000,000 tokens)
MODEL_PRICING_PER_1M_USD = {
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-3.1-flash-lite": {"input": 0.25, "output": 1.50},
    "gemini-3.5-flash": {"input": 0.25, "output": 1.50},
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
}

DEFAULT_PRICING = {"input": 0.30, "output": 2.50}
FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-3.1-flash-lite", "gemini-3.5-flash"]


def get_model_pricing(model_name: str) -> dict:
    """Return official (input, output) USD price per 1M tokens for the given model."""
    return MODEL_PRICING_PER_1M_USD.get(model_name, DEFAULT_PRICING)


def compute_cost_usd(
    input_tokens: int,
    output_tokens: int,
    thinking_tokens: int = 0,
    model_name: str = "gemini-2.5-flash",
) -> float:
    """Compute exact USD cost using Module 1 formula:
    (n_in * c_in + (n_out + n_think) * c_out) / 1,000,000
    """
    prices = get_model_pricing(model_name)
    billed_output_tokens = output_tokens + thinking_tokens
    return (
        input_tokens * prices["input"] + billed_output_tokens * prices["output"]
    ) / 1_000_000.0


def call_llm(
    user_message: str,
    system_prompt: str,
    temperature: float = 0.0,
    model: str | None = None,
    allow_fallback: bool = True,
) -> dict:
    """Call Google Gemini API with thinking_budget=0, exact token accounting, and rate-limit handling."""
    from google import genai
    from google.genai import types
    from google.genai.errors import APIError

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Copy .env.example to .env and add your Google AI Studio key."
        )

    primary_model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    if allow_fallback:
        candidates = [primary_model] + [m for m in FALLBACK_MODELS if m != primary_model]
    else:
        candidates = [primary_model]

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            api_version="v1beta",
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )

    last_err = None
    for attempt in range(3):
        for candidate_model in candidates:
            config_kwargs = {
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
                thinking_tokens = int(getattr(usage, "thoughts_token_count", 0) or 0)
                total_tokens = int(
                    getattr(
                        usage,
                        "total_token_count",
                        input_tokens + output_tokens + thinking_tokens,
                    )
                    or 0
                )

                cost_usd = compute_cost_usd(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    thinking_tokens=thinking_tokens,
                    model_name=candidate_model,
                )

                return {
                    "model": candidate_model,
                    "temperature": temperature,
                    "output_text": response.text or "",
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "thinking_tokens": thinking_tokens,
                    "total_tokens": total_tokens,
                    "cost_usd": round(cost_usd, 8),
                    "latency_s": round(latency_s, 4),
                }
            except APIError as err:
                last_err = err
                if err.code in (429, 503):
                    continue
                raise
        time.sleep(5 * (attempt + 1))

    raise RuntimeError(f"Gemini API rate-limited across candidate models: {last_err}")
