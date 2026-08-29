"""MCP client: discovery and invocation over the capability fabric.

WHAT THIS IS. The spec asks for five logical capability groups (Model,
SQL/Data, RAG/Retrieval, Web/External Data, Agent/Tools) reachable
through a uniform discover-then-invoke interface, and explicitly allows
them to be "implemented as fewer or more physical servers depending on
deployment simplicity".

This implementation runs the groups **in-process** and adapts the
existing capability implementations rather than standing up separate
server processes. That is a deliberate choice, and the honest label for
it is IN_PROCESS rather than a claim of a networked MCP deployment:

- The architecture's requirement is the *boundary* (uniform discovery,
  uniform invocation, normalized results, classified failures), not a
  particular transport. Every consumer -- planner, executor, dashboard --
  goes through this interface and is unaware of what is behind it.
- Standing up real MCP server processes would add operational surface
  (ports, lifecycles, health checks) without changing a single control
  decision, and the spec warns against adding infrastructure for
  appearance.
- Swapping an adapter for a networked transport later changes only the
  adapter: the contract, the failure taxonomy, and every caller stay
  identical.

WHAT THIS DELIBERATELY DOES NOT DO. It does not plan, route, score risk,
apply policy, authorize, retry, replan, or decide anything. It reports
what happened in a normalized shape and classifies failures so
ControlPlane can decide. ``tests/test_mcp.py`` asserts this module
imports none of the decision/policy/risk/trust modules -- the boundary is
tested, not merely promised.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache

from controlplane.capabilities.registry import (
    CapabilityDescriptor,
    CapabilityStatus,
    get_capability_registry,
)
from controlplane.db.models import new_id
from controlplane.mcp.contracts import MCPFailure, MCPResult, MCPStatus

# The five logical capability groups from the spec. Capability -> group,
# used for discovery and for reporting which "server" served a call.
CAPABILITY_GROUPS: dict[str, str] = {
    "RAG": "rag-retrieval",
    "SQL": "sql-data",
    "AGENT": "agent-tools",
    "GENERAL": "model",
    "WEB": "web-external",
    "CHAT_HISTORY": "rag-retrieval",
    "MEMORY": "rag-retrieval",
}

_DEFAULT_TIMEOUT_S = 30.0


@dataclass
class DiscoveredCapability:
    """What discovery returns: registry metadata plus its serving group."""

    descriptor: CapabilityDescriptor
    server: str

    def to_dict(self) -> dict:
        return {**self.descriptor.to_dict(), "server": self.server, "transport": "IN_PROCESS"}


class MCPClient:
    def __init__(self, handlers: dict | None = None, timeout_s: float = _DEFAULT_TIMEOUT_S) -> None:
        """``handlers`` maps capability_id -> callable(query) -> dict.

        Injected rather than imported so a caller can supply real
        capabilities, test doubles, or a future networked transport
        without this module changing.
        """
        self._registry = get_capability_registry()
        self._handlers = handlers or {}
        self._timeout_s = timeout_s
        self._health: dict[str, str] = {}

    # --- Discovery -------------------------------------------------

    def discover(
        self,
        *,
        data_requirements: set[str] | None = None,
        supplies_evidence: bool | None = None,
        usable_only: bool = True,
    ) -> list[DiscoveredCapability]:
        """"What capabilities are available?"

        Delegates the metadata question to the Capability Registry rather
        than keeping a second, divergent copy of capability facts.
        """
        descriptors = self._registry.discover(
            data_requirements=data_requirements,
            supplies_evidence=supplies_evidence,
            usable_only=usable_only,
        )
        return [
            DiscoveredCapability(descriptor=d, server=CAPABILITY_GROUPS.get(d.capability_id, "unknown"))
            for d in descriptors
        ]

    def server_for(self, capability_id: str) -> str:
        return CAPABILITY_GROUPS.get(capability_id, "unknown")

    # --- Health ----------------------------------------------------

    def health(self, capability_id: str) -> str:
        """Last observed health. Starts from the registry's declared
        status and is updated by real invocation outcomes, so a
        capability that keeps failing is reported DEGRADED even though
        its static metadata says AVAILABLE."""
        if capability_id in self._health:
            return self._health[capability_id]
        descriptor = self._registry.get(capability_id)
        return descriptor.status.value if descriptor else CapabilityStatus.UNAVAILABLE.value

    # --- Invocation ------------------------------------------------

    def invoke(self, capability_id: str, query: str, **kwargs) -> MCPResult:
        """Invoke one capability and normalize the outcome.

        Never raises for a capability-level failure: a failure is a
        first-class result that ControlPlane must be able to see and act
        on, not an exception that unwinds the execution graph.
        """
        operation_id = new_id("mcpop")
        server = self.server_for(capability_id)
        descriptor = self._registry.get(capability_id)

        if descriptor is None:
            return MCPResult(
                capability_id=capability_id, operation_id=operation_id, server=server,
                status=MCPStatus.FAILED, failure=MCPFailure.CAPABILITY_NOT_FOUND,
                error=f"no capability registered with id {capability_id!r}",
            )

        handler = self._handlers.get(capability_id)
        if handler is None:
            self._health[capability_id] = CapabilityStatus.UNAVAILABLE.value
            return MCPResult(
                capability_id=capability_id, operation_id=operation_id, server=server,
                status=MCPStatus.FAILED, failure=MCPFailure.UNAVAILABLE,
                error=f"capability {capability_id!r} is registered but no handler is wired "
                      "in this deployment",
            )

        start = time.monotonic()
        try:
            output = handler(query, **kwargs) if kwargs else handler(query)
        except TimeoutError as exc:
            return self._failed(capability_id, operation_id, server, MCPFailure.TIMEOUT, exc, start)
        except PermissionError as exc:
            return self._failed(capability_id, operation_id, server, MCPFailure.PERMISSION_DENIED, exc, start)
        except (TypeError, ValueError) as exc:
            return self._failed(capability_id, operation_id, server, MCPFailure.INVALID_REQUEST, exc, start)
        except Exception as exc:
            return self._failed(capability_id, operation_id, server, MCPFailure.SERVER_FAILURE, exc, start)

        latency_ms = int((time.monotonic() - start) * 1000)

        if not isinstance(output, dict):
            return self._failed(
                capability_id, operation_id, server, MCPFailure.INVALID_RESPONSE,
                TypeError(f"handler returned {type(output).__name__}, expected dict"), start,
            )

        self._health[capability_id] = CapabilityStatus.AVAILABLE.value
        return MCPResult(
            capability_id=capability_id, operation_id=operation_id, server=server,
            status=MCPStatus.OK, output=output,
            evidence=_extract_evidence(output),
            latency_ms=latency_ms,
            permissions_used=descriptor.required_permissions,
        )

    def _failed(self, capability_id, operation_id, server, failure, exc, start) -> MCPResult:
        self._health[capability_id] = CapabilityStatus.DEGRADED.value
        return MCPResult(
            capability_id=capability_id, operation_id=operation_id, server=server,
            status=MCPStatus.FAILED, failure=failure, error=str(exc)[:300],
            latency_ms=int((time.monotonic() - start) * 1000),
        )


def _extract_evidence(output: dict) -> list[str]:
    """Pull evidence text out of a capability's own output shape.

    The existing capabilities predate this fabric and each return their
    own dict; normalizing here is exactly the adapter's job and is
    cheaper than rewriting three working capabilities to a new contract.
    """
    evidence: list[str] = []
    for chunk in output.get("chunks") or []:
        text = chunk.get("text") if isinstance(chunk, dict) else None
        if text:
            evidence.append(text)
    for row in output.get("rows") or []:
        if isinstance(row, dict):
            evidence.append(", ".join(f"{k}={v}" for k, v in row.items()))
    return evidence


@lru_cache(maxsize=1)
def get_mcp_client() -> MCPClient:
    """Process-wide client wired to the real in-process capabilities.

    Imported lazily so that constructing the fabric does not drag the RAG
    embedding model into every process that merely wants to *discover*
    what capabilities exist.
    """
    from controlplane.capabilities.rag_capability import RAGCapability
    from controlplane.capabilities.sql_capability import SQLCapability

    rag, sql = RAGCapability(), SQLCapability()
    return MCPClient(handlers={
        "RAG": lambda query, **kw: rag.execute(query, **kw),
        "SQL": lambda query, **kw: sql.execute(query, **kw),
    })
