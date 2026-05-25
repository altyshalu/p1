from l2l3_protocol.api.main import app
from l2l3_protocol.core.schemas import RegistryChangeCandidateCreate, RegistryChangeStatus, RegistryKind
from l2l3_protocol.hub.registry import is_safe_registry_change


def test_taskforce_hub_api_routes_are_registered() -> None:
    routes = {(route.path, ",".join(sorted(getattr(route, "methods", set()) or []))) for route in app.routes}

    assert ("/hub/{kind}", "GET") in routes
    assert ("/hub/{kind}/{key}", "GET") in routes
    assert ("/hub/change-candidates", "POST") in routes
    assert ("/hub/change-candidates/{candidate_id}/approve", "POST") in routes
    assert ("/hub/change-candidates/{candidate_id}/reject", "POST") in routes
    assert ("/hub/sync/yaml", "POST") in routes
    assert not any(path.startswith("/registry") for path, _ in routes)


def test_hub_change_policy_auto_applies_only_safe_metadata_changes() -> None:
    safe = RegistryChangeCandidateCreate(
        kind=RegistryKind.FAILURE_PATTERN,
        key="timeout-001",
        change_type="update_metadata",
        payload={"frequency": 2, "last_seen": "2026-05-25"},
    )
    unsafe = RegistryChangeCandidateCreate(
        kind=RegistryKind.WORKER,
        key="publisher",
        change_type="update_spec",
        payload={"entrypoint": "dangerous.module"},
    )

    assert is_safe_registry_change(safe) is True
    assert is_safe_registry_change(unsafe) is False
    assert RegistryChangeStatus.AUTO_APPLIED_SAFE.value == "auto_applied_safe"
