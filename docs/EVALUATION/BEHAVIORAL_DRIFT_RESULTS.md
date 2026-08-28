# Behavioral Drift Results

**Run:** `controlplane/experiments/evaluate_behavioral_drift.py`, 2026-08-28. See `docs/ALGORITHMS/BEHAVIORAL_DRIFT.md` for method and why this is a SYNTHETIC-history demonstration, not a validated real-world baseline (no real historical AGENT-action volume exists yet).

## Results

| Case | Description | Expected | Actual | Match |
|---|---|---|---|---|
| BD-001 | Normal continuation (common tool, common outcome) | NONE | NONE | Yes |
| BD-002 | Rare tool, benign outcome | LOW | LOW | Yes |
| BD-003 | Common tool, unprecedented severity | LOW | LOW | Yes |
| BD-004 | Rare tool AND unprecedented severity | MEDIUM | MEDIUM | Yes |

4/4 matched expectations (`matched_expectation_rate=1.0`).

## Known Limitations

- Baseline history is a stated SYNTHETIC construction (80% `sql_read_query`/ALLOW, 20% `write_report`/ALLOW), not derived from real usage.
- Only 4 demonstration cases, each designed to exercise one specific branch of the detector's logic — not a statistically powered benchmark.
- Not wired into any live decision path (see algorithm doc for why).
