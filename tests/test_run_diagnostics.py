from uuid import uuid4

from l2l3_protocol.core.schemas import ArtifactType, ImprovementProposalStatus
from l2l3_protocol.runtime.diagnostics import analyze_run


def test_failed_run_diagnosis_uses_incident_brief_evidence_and_proposes_improvement() -> None:
    task_id = str(uuid4())
    run = {
        "id": str(uuid4()),
        "status": "failed",
        "tasks": [{"id": task_id, "worker_profile": "trend-source-collector", "status": "failed"}],
        "artifacts": [],
        "evals": [],
        "events": [
            {
                "event_type": "incident_brief",
                "task_id": task_id,
                "payload": {
                    "worker_profile": "trend-source-collector",
                    "failure_type": "provider_no_results",
                    "error": "huggingface search failed after 2 real attempts",
                    "retry_count_remaining": 0,
                    "repair_guidance": {"l2_can": ["retry the same provider with provider_repairs using alternative real queries"]},
                },
            }
        ],
    }

    diagnosis, proposals = analyze_run(run)

    assert diagnosis.artifact_type == ArtifactType.RUN_DIAGNOSIS
    assert diagnosis.payload["outcome"] == "failed"
    assert diagnosis.payload["root_cause"] == "tool_or_provider_failure"
    assert diagnosis.payload["evidence"][0]["event_type"] == "incident_brief"
    assert "huggingface search failed" in diagnosis.payload["summary"]
    assert proposals
    assert proposals[0].status == ImprovementProposalStatus.PROPOSED
    assert proposals[0].proposal_type == "improve_tool"
    assert proposals[0].target_component == "trend-source-collector/provider:huggingface"
    assert proposals[0].failure_signature == "provider_no_results:trend-source-collector"
    assert "Hugging Face provider repair" in proposals[0].proposed_change
    assert proposals[0].source_run_id == run["id"]
    assert proposals[0].evidence[0]["task_id"] == task_id
    assert proposals[0].behavior_change_requires_approval is True
    assert proposals[0].proof_spec["real_run_required"] is True
    assert proposals[0].proof_spec["baseline_run_id"] == run["id"]
    assert proposals[0].proof_spec["expected_absent_signature"] == "provider_no_results:trend-source-collector"


def test_successful_run_with_no_incidents_records_no_improvement_needed() -> None:
    run = {
        "id": str(uuid4()),
        "status": "waiting_approval",
        "tasks": [{"worker_profile": "trend-draft-quality-judge", "status": "completed"}],
        "artifacts": [{"artifact_type": "channel_drafts", "payload": {"drafts": [{"text": "real draft"}]}}],
        "evals": [{"eval_key": "trend-draft-quality", "passed": True, "score": 1.0}],
        "events": [{"event_type": "run_finished", "payload": {"status": "waiting_approval"}}],
    }

    diagnosis, proposals = analyze_run(run)

    assert diagnosis.payload["outcome"] == "waiting_approval"
    assert diagnosis.payload["root_cause"] == "none"
    assert diagnosis.payload["improvement_needed"] is False
    assert diagnosis.payload["proposal_reason"] == "No improvement proposal needed for this run."
    assert proposals == []


def test_max_turn_failure_after_repeated_eval_repairs_is_repeated_repair() -> None:
    run = {
        "id": str(uuid4()),
        "status": "failed",
        "tasks": [],
        "artifacts": [],
        "evals": [
            {
                "eval_key": "trend-claim-grounding",
                "passed": False,
                "score": 0.3333333333333333,
                "threshold": 1.0,
                "reasons": ["Draft has no claims."],
            }
        ],
        "events": [
            {"event_type": "incident_brief", "payload": {"failure_type": "eval_failed", "worker_profile": "claim-grounding-judge"}},
            {"event_type": "incident_brief", "payload": {"failure_type": "eval_failed", "worker_profile": "claim-grounding-judge"}},
            {"event_type": "run_failed", "payload": {"reason": "max_supervisor_turns exceeded"}},
        ],
    }

    diagnosis, proposals = analyze_run(run)

    assert diagnosis.payload["outcome"] == "failed"
    assert diagnosis.payload["root_cause"] == "repeated_repair"
    assert diagnosis.payload["repeated_repair"] is True
    assert "max_supervisor_turns exceeded" in diagnosis.payload["summary"]
    assert proposals[0].proposal_type == "improve_playbook"
    assert proposals[0].target_component == "playbook:repair-stop-rules"


def test_diagnosis_prefers_typed_incident_over_untyped_task_wrapper() -> None:
    task_id = str(uuid4())
    run = {
        "id": str(uuid4()),
        "status": "waiting_approval",
        "tasks": [],
        "artifacts": [],
        "evals": [{"eval_key": "trend-draft-quality", "passed": True, "score": 1.0}],
        "events": [
            {
                "event_type": "task_failed",
                "task_id": task_id,
                "payload": {
                    "worker_profile": "trend-source-collector",
                    "error": "trend providers failed",
                },
            },
            {
                "event_type": "incident_brief",
                "task_id": task_id,
                "payload": {
                    "worker_profile": "trend-source-collector",
                    "failure_type": "provider_no_results",
                    "error": "huggingface search returned no results",
                },
            },
            {"event_type": "run_finished", "payload": {"status": "waiting_approval"}},
        ],
    }

    diagnosis, proposals = analyze_run(run)

    assert diagnosis.payload["root_cause"] == "tool_or_provider_failure"
    assert "huggingface search returned no results" in diagnosis.payload["summary"]
    assert proposals[0].proposal_type == "improve_tool"


def test_claim_grounding_failure_proposal_targets_eval_contract() -> None:
    run = {
        "id": str(uuid4()),
        "status": "waiting_approval",
        "tasks": [],
        "artifacts": [],
        "evals": [
            {
                "task_id": str(uuid4()),
                "eval_key": "trend-claim-grounding",
                "passed": False,
                "score": 0.3333333333333333,
                "threshold": 1.0,
                "reasons": ["Draft has no claims."],
            }
        ],
        "events": [
            {
                "event_type": "incident_brief",
                "payload": {
                    "worker_profile": "claim-grounding-judge",
                    "failure_type": "eval_failed",
                    "error": "eval did not meet threshold",
                },
            }
        ],
    }

    diagnosis, proposals = analyze_run(run)

    assert diagnosis.payload["root_cause"] == "quality_gate_failed"
    assert proposals[0].proposal_type == "improve_eval"
    assert proposals[0].target_component == "claim-grounding-judge/trend-claim-grounding"
    assert proposals[0].failure_signature == "eval_failed:claim-grounding-judge"
    assert "claim-grounding contract" in proposals[0].proposed_change


def test_missing_env_error_overrides_output_schema_proposal_type() -> None:
    task_id = str(uuid4())
    run = {
        "id": str(uuid4()),
        "status": "failed",
        "tasks": [{"id": task_id, "worker_profile": "p1-source-collector", "status": "failed"}],
        "artifacts": [],
        "evals": [],
        "events": [
            {
                "event_type": "task_failed",
                "task_id": task_id,
                "payload": {
                    "worker_profile": "p1-source-collector",
                    "error": '{"error_type": "P1WorkerInputError", "message": "missing required environment variable: EXA_API_KEY"}',
                },
            },
            {
                "event_type": "incident_brief",
                "task_id": task_id,
                "payload": {
                    "worker_profile": "p1-source-collector",
                    "failure_type": "output_schema",
                    "error": '{"error_type": "P1WorkerInputError", "message": "missing required environment variable: EXA_API_KEY"}',
                    "structured_error": {
                        "error_type": "P1WorkerInputError",
                        "message": "missing required environment variable: EXA_API_KEY",
                    },
                },
            },
        ],
    }

    diagnosis, proposals = analyze_run(run)

    assert diagnosis.payload["root_cause"] == "missing_runtime_dependency"
    assert proposals[0].proposal_type == "improve_observability"
    assert proposals[0].target_component == "runtime:p1-source-collector/env:EXA_API_KEY"
    assert proposals[0].failure_signature == "missing_runtime_dependency:p1-source-collector:EXA_API_KEY"
    assert "missing runtime dependency" in proposals[0].proposed_change.lower()


def test_missing_env_proposal_uses_env_evidence_in_mixed_runtime_failures() -> None:
    task_id = str(uuid4())
    run = {
        "id": str(uuid4()),
        "status": "failed",
        "tasks": [{"id": task_id, "worker_profile": "p1-source-collector", "status": "failed"}],
        "artifacts": [],
        "evals": [],
        "events": [
            {
                "event_type": "incident_brief",
                "task_id": task_id,
                "payload": {
                    "worker_profile": "setup-checker",
                    "failure_type": "missing_provider_credential",
                    "error": "provider credential unavailable",
                },
            },
            {
                "event_type": "incident_brief",
                "task_id": task_id,
                "payload": {
                    "worker_profile": "p1-source-collector",
                    "failure_type": "output_schema",
                    "error": "missing required environment variable: exa_api_key",
                },
            },
        ],
    }

    diagnosis, proposals = analyze_run(run)

    assert diagnosis.payload["root_cause"] == "missing_runtime_dependency"
    assert proposals[0].proposal_type == "improve_observability"
    assert proposals[0].target_component == "runtime:p1-source-collector/env:exa_api_key"
    assert proposals[0].failure_signature == "missing_runtime_dependency:p1-source-collector:exa_api_key"


def test_apify_billing_error_is_provider_failure_not_worker_crash() -> None:
    task_id = str(uuid4())
    run = {
        "id": str(uuid4()),
        "status": "failed",
        "tasks": [{"id": task_id, "worker_profile": "p1-source-collector", "status": "failed"}],
        "artifacts": [],
        "evals": [],
        "events": [
            {
                "event_type": "incident_brief",
                "task_id": task_id,
                "payload": {
                    "worker_profile": "p1-source-collector",
                    "failure_type": "worker_exception",
                    "error": '{"error_type":"P1WorkerInputError","message":"real HTTP request failed POST https://api.apify.com/v2/acts/nexgendata~startup-funding-tracker/runs?token=[REDACTED]&maxItems=10: 402: {\\"error\\":{\\"type\\":\\"not-enough-usage-to-run-paid-actor\\",\\"message\\":\\"remaining usage\\"}}"}',
                    "structured_error": {
                        "error_type": "P1WorkerInputError",
                        "message": 'real HTTP request failed POST https://api.apify.com/v2/acts/nexgendata~startup-funding-tracker/runs?token=[REDACTED]&maxItems=10: 402: {"error":{"type":"not-enough-usage-to-run-paid-actor","message":"remaining usage"}}',
                    },
                },
            }
        ],
    }

    diagnosis, proposals = analyze_run(run)

    assert diagnosis.payload["root_cause"] == "tool_or_provider_failure"
    assert proposals[0].proposal_type == "improve_tool"
    assert proposals[0].target_component == "p1-source-collector/provider:apify"
    assert proposals[0].failure_signature == "worker_exception:p1-source-collector"


def test_apify_provider_detection_uses_host_before_substrings() -> None:
    task_id = str(uuid4())
    run = {
        "id": str(uuid4()),
        "status": "failed",
        "tasks": [{"id": task_id, "worker_profile": "p1-source-collector", "status": "failed"}],
        "artifacts": [],
        "evals": [],
        "events": [
            {
                "event_type": "incident_brief",
                "task_id": task_id,
                "payload": {
                    "worker_profile": "p1-source-collector",
                    "failure_type": "worker_exception",
                    "structured_error": {
                        "error_type": "P1WorkerInputError",
                        "message": 'real HTTP request failed POST https://api.apify.com/v2/acts/example~actor/runs?token=[REDACTED]&maxItems=1: 402: {"error":{"type":"not-enough-usage-to-run-paid-actor"}}',
                    },
                },
            }
        ],
    }

    _, proposals = analyze_run(run)

    assert proposals[0].target_component == "p1-source-collector/provider:apify"


def test_generic_worker_http_error_is_not_provider_failure_without_provider_marker() -> None:
    task_id = str(uuid4())
    run = {
        "id": str(uuid4()),
        "status": "failed",
        "tasks": [{"id": task_id, "worker_profile": "custom-worker", "status": "failed"}],
        "artifacts": [],
        "evals": [],
        "events": [
            {
                "event_type": "incident_brief",
                "task_id": task_id,
                "payload": {
                    "worker_profile": "custom-worker",
                    "failure_type": "worker_exception",
                    "error": "real HTTP request failed POST http://internal-service.local/jobs: 500",
                },
            }
        ],
    }

    diagnosis, proposals = analyze_run(run)

    assert diagnosis.payload["root_cause"] == "worker_execution_failed"
    assert proposals[0].proposal_type == "fix_code"
    assert proposals[0].target_component == "custom-worker"


def test_repaired_eval_failure_does_not_create_terminal_quality_proposal() -> None:
    run = {
        "id": str(uuid4()),
        "status": "waiting_approval",
        "tasks": [],
        "artifacts": [],
        "evals": [
            {
                "task_id": str(uuid4()),
                "eval_key": "trend-claim-grounding",
                "passed": False,
                "score": 0.6666666666666666,
                "threshold": 1.0,
                "reasons": ["Draft has no claims."],
            },
            {
                "task_id": str(uuid4()),
                "eval_key": "trend-claim-grounding",
                "passed": True,
                "score": 1.0,
                "threshold": 1.0,
                "reasons": [],
            },
            {
                "task_id": str(uuid4()),
                "eval_key": "trend-draft-quality",
                "passed": True,
                "score": 1.0,
                "threshold": 0.8,
                "reasons": [],
            },
        ],
        "events": [
            {
                "event_type": "incident_brief",
                "payload": {
                    "worker_profile": "claim-grounding-judge",
                    "failure_type": "eval_failed",
                    "error": "eval did not meet threshold",
                    "eval_result": {
                        "eval_key": "trend-claim-grounding",
                        "passed": False,
                    },
                },
            }
        ],
    }

    diagnosis, proposals = analyze_run(run)

    assert diagnosis.payload["root_cause"] == "none"
    assert diagnosis.payload["improvement_needed"] is False
    assert diagnosis.payload["evidence"] == []
    assert proposals == []


def test_invalid_provider_proposal_targets_trend_radar_inputs() -> None:
    run = {
        "id": str(uuid4()),
        "status": "failed",
        "tasks": [],
        "artifacts": [],
        "evals": [],
        "events": [
            {
                "event_type": "run_input_validation_failed",
                "payload": {
                    "failure_type": "input_validation",
                    "error": "unsupported providers requested: ['notarealprovider']; supported providers: ['arxiv', 'github', 'huggingface']",
                },
            }
        ],
    }

    diagnosis, proposals = analyze_run(run)

    assert diagnosis.payload["root_cause"] == "bad_or_missing_input"
    assert proposals[0].proposal_type == "improve_policy"
    assert proposals[0].target_component == "trend-radar/input.providers"
    assert proposals[0].failure_signature == "input_validation:trend-radar/input.providers"


def test_unknown_failure_auto_creates_stable_diagnosis_category() -> None:
    task_id = str(uuid4())
    base_run = {
        "id": str(uuid4()),
        "status": "failed",
        "tasks": [{"id": task_id, "worker_profile": "new-worker", "status": "failed"}],
        "artifacts": [],
        "evals": [],
        "events": [
            {
                "event_type": "incident_brief",
                "task_id": task_id,
                "payload": {
                    "worker_profile": "new-worker",
                    "failure_type": "vendor_limit_shape_changed",
                    "error": "Vendor limit response changed shape for request 81237 and object 9f8a7c6b5d4e3f2a",
                },
            }
        ],
    }
    comparable_run = {
        **base_run,
        "id": str(uuid4()),
        "events": [
            {
                **base_run["events"][0],
                "payload": {
                    **base_run["events"][0]["payload"],
                    "error": "Vendor limit response changed shape for request 44444 and object aaaaaaaaaaaaaaaa",
                },
            }
        ],
    }

    diagnosis, proposals = analyze_run(base_run)
    comparable_diagnosis, comparable_proposals = analyze_run(comparable_run)

    assert diagnosis.payload["root_cause"] == "runtime_failed"
    category = diagnosis.payload["diagnosis_category"]
    assert category["auto_created"] is True
    assert category["source"] == "auto_created"
    assert category["key"].startswith("auto:new-worker:vendor-limit-shape-changed:")
    assert proposals[0].failure_signature == category["key"]
    assert comparable_diagnosis.payload["diagnosis_category"]["key"] == category["key"]
    assert comparable_proposals[0].failure_signature == proposals[0].failure_signature


def test_auto_created_failure_signature_fits_storage_limit() -> None:
    task_id = str(uuid4())
    run = {
        "id": str(uuid4()),
        "status": "failed",
        "tasks": [{"id": task_id, "worker_profile": "worker-" + "x" * 120, "status": "failed"}],
        "artifacts": [],
        "evals": [],
        "events": [
            {
                "event_type": "incident_brief",
                "task_id": task_id,
                "payload": {
                    "worker_profile": "worker-" + "x" * 120,
                    "failure_type": "failure-" + "y" * 120,
                    "error": "Vendor contract changed with " + ("z" * 240),
                },
            }
        ],
    }

    diagnosis, proposals = analyze_run(run)

    assert len(diagnosis.payload["diagnosis_category"]["key"]) <= 160
    assert len(proposals[0].failure_signature) <= 160
