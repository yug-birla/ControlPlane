"""Manual/live Groq validation -- NOT collected by pytest (doesn't match
``test_*``), and never run in CI. Run explicitly:

    GROQ_API_KEY=... .venv/Scripts/python -m tests.manual_groq_live_check

Never pass the key on a shared/logged shell if avoidable; this script
never prints it. If GROQ_API_KEY is unset, reports
"GROQ LIVE VALIDATION: NOT EXECUTED" and exits without fabricating a
result, per docs/PROJECT_STATE/DECISIONS.md.

This also demonstrates why GROQ_MODEL should never be hard-coded: it asks
Groq for the live list of available models rather than guessing one from
training data, which could be stale or already decommissioned.
"""

from __future__ import annotations

import os
import sys

from controlplane.models.groq_provider import GroqProvider
from controlplane.models.provider import ModelProviderError


def main() -> int:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("GROQ LIVE VALIDATION: NOT EXECUTED")
        print("Reason: GROQ_API_KEY is not set in the environment.")
        return 0

    probe = GroqProvider(api_key=api_key, model="placeholder-not-used-for-listing")
    try:
        models = probe.list_models()
    except ModelProviderError as exc:
        print("GROQ LIVE VALIDATION: NOT EXECUTED")
        print(f"Reason: could not list models ({exc}).")
        return 1

    chat_candidates = [m for m in models if "whisper" not in m and "tts" not in m and "guard" not in m]
    if not chat_candidates:
        print("GROQ LIVE VALIDATION: NOT EXECUTED")
        print("Reason: no chat-completion-looking model found in the live model list.")
        return 1

    model = chat_candidates[0]
    provider = GroqProvider(api_key=api_key, model=model)
    result = provider.generate(prompt="Reply with exactly one short sentence confirming you received this.")

    print("GROQ LIVE VALIDATION: EXECUTED")
    print(f"model_used: {result.model}")
    print(f"latency_ms: {result.latency_ms}")
    print(f"input_tokens: {result.input_tokens}")
    print(f"output_tokens: {result.output_tokens}")
    print(f"finish_reason: {result.finish_reason}")
    print(f"response_content: {result.content!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
