"""ControlPlane.ai runtime package.

Layer 1 (Foundation) only: API entry, request/trace/trajectory identity,
ExecutionState, configuration, structured logging, error model, health
checks, and the response envelope. No routing, RAG, MCP, evaluation, or
intervention logic lives here yet -- see docs/PROJECT_STATE/FUTURE_WORK.md.
"""

__version__ = "0.1.0"
