from pathlib import Path

from l2l3_protocol.memory.adapters import ProceduralRegistry


def test_build_in_public_registry_loads_dynamic_runtime_specs() -> None:
    registry = ProceduralRegistry(Path("registries"))

    process = registry.load_process_pack("build-in-public")
    profiles = registry.list_worker_profiles()
    judge = registry.load_worker_profile("quality-judge")
    eval_spec = registry.load_eval_spec("build-in-public-draft-quality")

    assert "stages" not in process
    assert process["allowed_workers"]
    assert set(process["allowed_workers"]).issubset(profiles)
    assert judge["grader_spec"]["eval_key"] == "build-in-public-draft-quality"
    assert judge["entrypoint"] == "l2l3_protocol.workers.build_in_public_worker"
    assert eval_spec["minimum_score"] == 0.75
