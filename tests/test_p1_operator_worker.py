import json
from pathlib import Path

from l2l3_protocol.workers.p1_operator_worker import _redact_secrets, judge_outreach_quality, read_existing_dossiers


def test_p1_dossier_reader_surfaces_real_state_drift(tmp_path: Path) -> None:
    dossier_path = tmp_path / "operator.json"
    dossier_path.write_text(
        json.dumps(
            {
                "identity": {"name": "Adeline Lee", "linkedin_url": "https://linkedin.com/in/adelineleecs", "alternative_urls": []},
                "historical_context": {
                    "sources_found": ["GSheet:04_THE_FORGE_FINAL"],
                    "all_recorded_headlines": ["Advisor and Angel Investor"],
                    "v2_triage_score": 62,
                },
                "live_intelligence": {"last_updated": "2026-05-04", "exa_raw_urls": ["https://example.com"], "exa_snippets": []},
                "gateway_evaluations": {"status": "Awaiting Outreach"},
                "outreach": {"status": "NONE", "draft_message": ""},
                "L2_State": "OUTREACH_DRAFTED",
            }
        )
    )

    result = read_existing_dossiers(
        {"inputs": {"mode": "existing_dossiers", "limit": 1, "dossier_source_path": str(tmp_path)}},
        {},
    )

    assert result["p1_dossiers"][0]["identity"]["name"] == "Adeline Lee"
    assert result["drift_report"]["drift_count"] == 1
    assert result["drift_report"]["items"][0]["drift_type"] == "draft_state_without_draft"


def test_p1_outreach_quality_requires_evidence_and_no_publish() -> None:
    result = judge_outreach_quality(
        {
            "inputs": {
                "outreach_drafts": [
                    {
                        "name": "Adeline Lee",
                        "text": "ABRT is building Limpid around operator product DNA. Curious whether this resonates for a quick 30-minute call next week?",
                        "evidence_urls": ["https://de.linkedin.com/in/adelineleecs"],
                        "claims": [{"text": "Adeline has operator product DNA.", "source_url": "https://de.linkedin.com/in/adelineleecs"}],
                        "status": "draft",
                        "publish": False,
                    }
                ]
            }
        },
        {},
    )

    assert result["passed"] is True
    assert result["score"] == 1.0
    assert result["approval_package"]["approval_required"] is True


def test_p1_http_error_redaction_removes_provider_tokens() -> None:
    raw = "https://api.apify.com/v2/acts/a/runs?token=apify_api_MsDummySecretWithS123 apify_api_MsDummySecretWithS123"

    redacted = _redact_secrets(raw)

    assert "MsDummySecretWithS123" not in redacted
    assert "token=[REDACTED]" in redacted
    assert "apify_api_[REDACTED]" in redacted
