"""Manual/live Gemini validation -- NOT collected by pytest (doesn't match
``test_*``), and never run in CI. Run explicitly:

    GEMINI_API_KEY_1=... [GEMINI_API_KEY_2=...] .venv/Scripts/python -m tests.manual_gemini_live_check

Never pass the key on a shared/logged shell if avoidable; this script
never prints it. If neither GEMINI_API_KEY_1 nor GEMINI_API_KEY_2 is
set, reports "GEMINI LIVE VALIDATION: NOT EXECUTED" and exits without
fabricating a result, per docs/PROJECT_STATE/DECISIONS.md.

Asks Gemini for its live model list rather than guessing one from
training data (same reasoning as the Groq equivalent).
"""

from __future__ import annotations

import os
import sys

from controlplane.models.gemini_provider import GeminiProvider
from controlplane.models.provider import ModelProviderError


def main() -> int:
    keys = [k for k in (os.environ.get("GEMINI_API_KEY_1"), os.environ.get("GEMINI_API_KEY_2")) if k]
    if not keys:
        print("GEMINI LIVE VALIDATION: NOT EXECUTED")
        print("Reason: neither GEMINI_API_KEY_1 nor GEMINI_API_KEY_2 is set in the environment.")
        return 0

    probe = GeminiProvider(api_keys=keys, model="placeholder-not-used-for-listing")
    try:
        models = probe.list_models()
    except ModelProviderError as exc:
        print("GEMINI LIVE VALIDATION: NOT EXECUTED")
        print(f"Reason: could not list models ({exc}).")
        return 1

    # Prefer a stable (non-preview) flash-class model for the validation
    # call -- cheap and fast, appropriate for a one-off connectivity check.
    stable_flash = [m for m in models if "flash" in m and "preview" not in m and "image" not in m and "tts" not in m]
    model = (stable_flash or models)[0].removeprefix("models/")

    provider = GeminiProvider(api_keys=keys, model=model)
    result = provider.generate(prompt="Reply with exactly one short sentence confirming you received this.")

    print("GEMINI LIVE VALIDATION: EXECUTED")
    print(f"model_used: {result.model}")
    print(f"latency_ms: {result.latency_ms}")
    print(f"input_tokens: {result.input_tokens}")
    print(f"output_tokens: {result.output_tokens}")
    print(f"finish_reason: {result.finish_reason}")
    print(f"response_content: {result.content!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
