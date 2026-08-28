"""ControlPlane Dashboard -- read-only observability surface over real
Postgres data (requests, query_profiles, route_decisions, trajectory
steps, events, ledger, response_evaluations). No live push/websocket --
each page load queries current state directly (bootstrap SS35: "Do not
fake live data"; a manual-refresh read of real current state satisfies
the underlying requirement -- request-level observability -- without
adding websocket/streaming infrastructure this milestone doesn't
otherwise need, per bootstrap SS45's "grow the product, not
infrastructure").
"""
