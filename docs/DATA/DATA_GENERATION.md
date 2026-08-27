# ControlPlane Data Generation Methodology

## Purpose

This document defines the initial methodology for producing the custom ControlPlane dataset.

The methodology is intentionally model- and provider-agnostic. Specific model, provider, and tooling choices are not specified in the initial version and require clarification before implementation.

## Generation Sequence

Large-scale generation must not begin until the schema has been reviewed and stabilized.

The required initial sequence is:

```text
Schema
  ↓
Taxonomy
  ↓
30 representative examples
  ↓
Schema review
  ↓
Freeze v0.1
  ↓
Large-scale generation
