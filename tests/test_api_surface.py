from l2l3_protocol.api.main import app


def test_generic_runtime_api_routes_are_registered() -> None:
    routes = {(route.path, ",".join(sorted(getattr(route, "methods", set()) or []))) for route in app.routes}

    assert ("/runs", "POST") in routes
    assert ("/runs/{run_id}", "GET") in routes
    assert ("/runs/{run_id}/messages", "POST") in routes
    assert ("/runs/{run_id}/control", "POST") in routes
    assert ("/runs/{run_id}/events/stream", "GET") in routes
