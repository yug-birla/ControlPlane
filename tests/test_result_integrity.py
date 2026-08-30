"""Every recorded result must survive being read back sceptically.

This project has repeatedly found metrics that looked valid and were not:
a latency span whose end preceded its start, an evidence count that was
structurally always zero, an accuracy whose denominator included cases it
could not score, a control arm that silently became the treatment, a
failure rate of 0.0 produced by an empty denominator.

None of those failed a test. Each was found by reading a recorded number
and asking whether it could physically be correct. These tests ask that
question mechanically, over every result file in the repository, so the
next one of the family is caught by the suite rather than by luck.

They are deliberately structural rather than value-based: they assert
nothing about whether a result is GOOD, only that it is possible.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

_RESULTS = Path("docs/EVALUATION/RESULTS")

# Metric names whose value is a proportion and therefore cannot leave
# [0, 1]. Matched by suffix so new metrics are covered automatically.
_RATE_SUFFIXES = ("_rate", "_accuracy", "_recall", "_precision", "_f1", "macro_f1")

# Keys that are counts of things and cannot be negative.
_COUNT_SUFFIXES = ("_count", "sample_count")


def _result_files() -> list[Path]:
    if not _RESULTS.exists():
        return []
    return sorted(_RESULTS.glob("*.json"))


def _walk(node, path=""):
    """Yield (dotted_path, key, value) for every scalar in a nested dict."""
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else key
            if isinstance(value, (dict, list)):
                yield from _walk(value, here)
            else:
                yield here, key, value
    elif isinstance(node, list):
        for i, value in enumerate(node):
            if isinstance(value, (dict, list)):
                yield from _walk(value, f"{path}[{i}]")


def test_there_are_recorded_results_at_all():
    """A guard on the guard: if the glob stops matching, every test below
    passes vacuously and the audit silently stops running."""
    files = _result_files()
    assert files, f"no result files under {_RESULTS}"
    assert len(files) >= 5, [f.name for f in files]


@pytest.mark.parametrize("path", _result_files(), ids=lambda p: p.name)
def test_every_result_file_is_readable_json(path: Path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict), f"{path.name} is not an object"


@pytest.mark.parametrize("path", _result_files(), ids=lambda p: p.name)
def test_no_proportion_escapes_its_range(path: Path):
    """A rate above 1.0 or below 0 is arithmetically impossible and means
    the denominator is wrong -- the defect family that produced the
    multi-agent ceiling."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    offenders = []
    for dotted, key, value in _walk(data):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        if not any(key.endswith(s) for s in _RATE_SUFFIXES):
            continue
        if math.isnan(value) or not (0.0 <= value <= 1.0):
            offenders.append(f"{dotted}={value}")
    assert offenders == [], offenders


@pytest.mark.parametrize("path", _result_files(), ids=lambda p: p.name)
def test_no_count_is_negative(path: Path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    offenders = [
        f"{dotted}={value}"
        for dotted, key, value in _walk(data)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        and any(key.endswith(s) for s in _COUNT_SUFFIXES) and value < 0
    ]
    assert offenders == [], offenders


@pytest.mark.parametrize("path", _result_files(), ids=lambda p: p.name)
def test_no_latency_is_negative(path: Path):
    """The span defect, generalised. 298 of 400 recorded spans once had a
    non-positive duration because completed_at preceded started_at."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    offenders = [
        f"{dotted}={value}"
        for dotted, key, value in _walk(data)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        and ("latency" in key or key.endswith("_ms")) and value < 0
    ]
    assert offenders == [], offenders


@pytest.mark.parametrize("path", _result_files(), ids=lambda p: p.name)
def test_a_reported_sample_count_is_never_zero(path: Path):
    """An experiment that scored nothing must not present metrics beside
    a sample_count of 0 -- that is a completed script, not a measurement."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    offenders = [
        dotted for dotted, key, value in _walk(data)
        if key == "sample_count" and value == 0
    ]
    assert offenders == [], offenders


def test_the_communication_ablation_records_that_it_actually_ablated():
    """The specific lesson from the invalid ablation: a comparison
    between two arms is only meaningful if the arms differed. The result
    file must carry that evidence, not merely the scores."""
    matches = sorted(_RESULTS.glob("agent_communication_*.json"))
    if not matches:
        pytest.skip("communication ablation has not been run yet")

    with open(matches[-1], encoding="utf-8") as f:
        data = json.load(f)

    integrity = data.get("channel_integrity")
    assert integrity, "no channel-integrity record"
    assert integrity["channel_actually_removed"] is True, integrity
    assert integrity["cases_with_delivery_in_communication_arm"], integrity
    assert integrity["cases_with_delivery_in_suppressed_arm"] == [], integrity


def test_experiments_record_the_commit_they_ran_at():
    """SS55. A result that cannot be tied to a code state cannot be
    reproduced. Checked on the files new enough to carry it rather than
    retrofitted onto older runs, which would mean editing history."""
    matches = sorted(_RESULTS.glob("agent_communication_*.json"))
    if not matches:
        pytest.skip("no commit-stamped result files yet")

    with open(matches[-1], encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("git_commit"), "no git_commit recorded"
    assert data["git_commit"] != "unknown", "git commit could not be resolved at run time"
