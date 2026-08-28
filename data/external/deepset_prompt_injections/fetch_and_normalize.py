"""Fetch + normalize the public `deepset/prompt-injections` dataset
(Milestone 8, bootstrap section 12: "If a task lacks sufficient quality
data, search public Hugging Face datasets"). This project's own
hand-authored `prompt_injection_cases.json` (12 cases) demonstrated the
mechanism but was too small for a real accuracy claim (bootstrap
section 58: "n=3 [scale] is not a serious benchmark").

Source: https://huggingface.co/datasets/deepset/prompt-injections
License: Apache-2.0
Revision (pinned): 4f61ecb038e9c3fb77e21034b22511b523772cdd (verified via
the live HF API on 2026-08-28 -- not guessed).
Schema: two columns, `text` (str) and `label` (0=benign, 1=injection).
Splits: train (546 rows), test (116 rows) -- both used here (662 total);
this project only evaluates, it does not train anything on this data, so
the train/test split from the source is not load-bearing for us.

RAW -> PROCESSED pipeline (bootstrap section 13): this script IS the raw
fetch; its output is the processed, normalized artifact
(`prompt_injections_normalized.json`), committed to the repo (662 short
text records, no PII, Apache-2.0 -- safe and small to commit, unlike a
model binary). Re-run this script to reproduce it from the source at the
pinned revision.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from huggingface_hub import hf_hub_download

_REPO_ID = "deepset/prompt-injections"
_REVISION = "4f61ecb038e9c3fb77e21034b22511b523772cdd"
_TRAIN_FILE = "data/train-00000-of-00001-9564e8b05b4757ab.parquet"
_TEST_FILE = "data/test-00000-of-00001-701d16158af87368.parquet"
_OUT_PATH = Path(__file__).parent / "prompt_injections_normalized.json"

_LABEL_MAP = {0: "NO_PATTERN_DETECTED", 1: "INJECTION_PATTERN_DETECTED"}


def _load_split(filename: str, split: str) -> list[dict]:
    path = hf_hub_download(repo_id=_REPO_ID, filename=filename, repo_type="dataset", revision=_REVISION)
    df = pd.read_parquet(path)
    records = []
    for i, row in df.iterrows():
        records.append({
            "case_id": f"DSPI-{split}-{i:04d}",
            "query": row["text"],
            "expected_label": _LABEL_MAP[int(row["label"])],
            "split": split,
            "source_label": int(row["label"]),
            "provenance": "EXTERNAL",
            "source_dataset": _REPO_ID,
            "source_revision": _REVISION,
            "source_license": "apache-2.0",
        })
    return records


def main() -> None:
    train = _load_split(_TRAIN_FILE, "train")
    test = _load_split(_TEST_FILE, "test")
    records = train + test

    with open(_OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(records)} normalized records to {_OUT_PATH}")
    print(f"  train={len(train)} test={len(test)}")
    from collections import Counter
    print(f"  label distribution: {dict(Counter(r['expected_label'] for r in records))}")
    print(f"  fetched {datetime.now(timezone.utc).date().isoformat()} (UTC date), source revision {_REVISION}")


if __name__ == "__main__":
    main()
