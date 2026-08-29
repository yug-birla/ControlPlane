"""MCP capability fabric.

MCP provides capability DISCOVERY, INVOCATION, and RESOURCE ACCESS.
ControlPlane owns routing, risk, policy, evaluation, intervention,
replanning, trust, and human escalation.

MCP must never become the brain
(docs/architecture/CONTROLPLANE_FINAL_ARCHITECTURE_IMPLEMENTATION_MASTER_SPEC.md
section 45). That boundary is enforced structurally here: nothing in this
package imports the decision, intervention, replanning, policy, risk, or
trust modules, and a test asserts that.
"""
