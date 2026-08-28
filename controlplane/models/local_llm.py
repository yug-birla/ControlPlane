"""Shared local causal-LM loading + generation.

Extracted in Milestone 9 because a SECOND consumer of the same local
model appeared (``controlplane.models.local_generation_provider``, the
offline ``ModelProvider``), and the bootstrap's "no duplicate
architecture" rule forbids copy-pasting the (non-obvious, hard-won)
loading configuration into a second file. ``controlplane.judge.local_judge``
was the original and only consumer through Milestone 8; it now delegates
here rather than owning the loading itself.

Model: Qwen/Qwen2.5-1.5B-Instruct, revision
989aa7980e4cf806f80c7fef2b1adb7bc71aa306 (pinned; verified via the live
Hugging Face API), Apache-2.0, ~1.5B parameters, ~3GB in bf16.

The loading configuration here is NOT the ``from_pretrained`` default,
and each deviation is a real fix for a real, reproduced failure on this
machine -- do not "simplify" them away:

- ``dtype=torch.bfloat16, low_cpu_mem_usage=True``: the default implicit
  float32 upcast during the memory-mapped load failed with
  ``OSError: The paging file is too small`` (Milestone 6). bf16 halves
  the resident footprint and loads successfully.
- ``local_files_only=True``: offline-first. Raises cleanly if the model
  isn't already cached rather than silently downloading inside a request
  path. Populate the cache during setup via
  ``controlplane.models.model_download``.
- ``torch.set_num_threads(os.cpu_count())``: torch defaults to a
  conservative thread count (10 on this 16-core machine); using every
  core is a measured ~35% latency reduction (88s -> 57s for one 80-token
  judgment) with no correctness tradeoff.

NO-GPU LOCAL INFERENCE. CPU-only latency is accepted and measured, not
hidden -- see docs/EVALUATION/ for the numbers.

Instances are deliberately NOT cached inside this module. Callers that
want a process-wide singleton use their own ``@lru_cache`` factory
(``controlplane.judge.local_judge.get_local_judge``,
``controlplane.models.local_generation_provider.get_local_generation_provider``)
and may pass an already-loaded ``LocalLLM`` to share one ~3GB copy
between the judge and the generation provider in a process that needs
both.
"""

from __future__ import annotations

import time

MODEL_REPO = "Qwen/Qwen2.5-1.5B-Instruct"
MODEL_REVISION = "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"


class LocalLLMError(Exception):
    pass


class LocalLLM:
    """A loaded local instruction-tuned causal LM.

    Exposes chat-formatted greedy generation only. Deliberately has no
    opinion about prompts, JSON contracts, or provider semantics -- those
    belong to the judge / provider layers above it.
    """

    model_repo = MODEL_REPO
    model_revision = MODEL_REVISION

    def __init__(self) -> None:
        try:
            import os

            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise LocalLLMError(
                "transformers/torch are not installed; run pip install -e \".[dev]\""
            ) from exc

        torch.set_num_threads(os.cpu_count() or 4)

        try:
            self._tokenizer = AutoTokenizer.from_pretrained(
                MODEL_REPO, revision=MODEL_REVISION, local_files_only=True
            )
            self._model = AutoModelForCausalLM.from_pretrained(
                MODEL_REPO,
                revision=MODEL_REVISION,
                local_files_only=True,
                dtype=torch.bfloat16,
                low_cpu_mem_usage=True,
            )
        except Exception as exc:
            raise LocalLLMError(
                f"local model {MODEL_REPO}@{MODEL_REVISION} is not cached locally -- "
                "download it once via huggingface_hub.snapshot_download during setup, "
                "never during a request"
            ) from exc

    def chat(self, messages: list[dict], max_new_tokens: int) -> tuple[str, int, int, int]:
        """Greedy (``do_sample=False``) chat generation.

        Returns ``(text, latency_ms, input_tokens, output_tokens)``. Token
        counts are the real tokenizer counts, not word-count estimates --
        ``ModelResult`` consumers report them as measured values.
        """
        text = self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self._tokenizer([text], return_tensors="pt")
        input_tokens = int(inputs["input_ids"].shape[1])

        start = time.monotonic()
        output_ids = self._model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=self._tokenizer.eos_token_id,
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        generated_ids = output_ids[0][input_tokens:]
        output_text = self._tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
        return output_text, latency_ms, input_tokens, int(generated_ids.shape[0])
