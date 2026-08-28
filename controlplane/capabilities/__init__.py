"""Real capability implementations -- SQL, RAG -- that the Execution
Graph's ``GraphExecutor`` invokes for the ``SQL``/``RAG`` capability
nodes, replacing the ``MOCKED`` handler used through Milestone 3.

Distinct from ``controlplane.routing`` (decides *what* to run) and
``controlplane.execution`` (runs *whatever* it's given) -- this package
is the *what* for the two capabilities implemented so far. See
docs/architecture/RUNTIME_FLOW.md SS2.3 ("a capability executes an
authorized step... a capability must not independently decide which
other capability should run next").
"""
