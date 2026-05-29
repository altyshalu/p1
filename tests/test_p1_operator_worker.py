import json
from pathlib import Path

from l2l3_protocol.workers.p1_operator_worker import (
    _apify_crunchbase_search,
    _apify_linkedin_search,
    _redact_secrets,
    build_metrics_report,
    judge_outreach_quality,
    read_existing_dossiers,
    sync_data_lake,
    sync_outreach_master,
)


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


def test_p1_crunchbase_source_normalizes_parseforge_person_rows(monkeypatch) -> None:
    def fake_run(actor_id, actor_input):
        assert actor_id == "parseforge/crunchbase-scraper"
        assert actor_input["startUrls"][0]["url"] == "https://www.crunchbase.com/person/naval-ravikant"
        return [
            {
                "name": "Naval Ravikant",
                "primaryJobTitle": "Founder",
                "primaryOrganization": "AngelList",
                "crunchbaseUrl": "https://www.crunchbase.com/person/naval-ravikant",
                "twitterUrl": "https://x.com/naval",
            }
        ]

    monkeypatch.setattr("l2l3_protocol.workers.p1_operator_worker._run_apify_actor", fake_run)

    result = _apify_crunchbase_search(
        {"crunchbase_start_urls": ["https://www.crunchbase.com/person/naval-ravikant"]},
        1,
    )

    assert result[0]["name"] == "Naval Ravikant"
    assert result[0]["headline"] == "Founder at AngelList"
    assert result[0]["linkedin_url"] == ""
    assert result[0]["source_url"] == "https://www.crunchbase.com/person/naval-ravikant"
    assert result[0]["source"] == "apify_crunchbase"
    assert "Naval Ravikant" in result[0]["evidence"][0]


def test_p1_linkedin_source_normalizes_sales_nav_rows(monkeypatch) -> None:
    def fake_run(actor_id, actor_input):
        assert actor_id == "riceman/linkedin-sales-navigator-lead-search-scraper"
        assert actor_input["keywords"] == "AI angel investor"
        assert actor_input["limit"] == 2
        return [
            {
                "full_name": "Arianna Simpson",
                "headline": "General Partner at a16z crypto",
                "linkedin_url": "https://www.linkedin.com/in/ariannasimpson/",
                "location": "San Francisco Bay Area",
            }
        ]

    monkeypatch.setattr("l2l3_protocol.workers.p1_operator_worker._run_apify_actor", fake_run)

    result = _apify_linkedin_search({"linkedin_keywords": "AI angel investor"}, 2)

    assert result == [
        {
            "name": "Arianna Simpson",
            "headline": "General Partner at a16z crypto",
            "linkedin_url": "https://www.linkedin.com/in/ariannasimpson",
            "source_url": "https://www.linkedin.com/in/ariannasimpson",
            "source": "apify_linkedin",
            "evidence": [
                '{"full_name": "Arianna Simpson", "headline": "General Partner at a16z crypto", "linkedin_url": "https://www.linkedin.com/in/ariannasimpson/", "location": "San Francisco Bay Area"}'
            ],
        }
    ]


def test_p1_data_lake_sync_writes_physical_dossier_files(tmp_path: Path) -> None:
    result = sync_data_lake(
        {
            "inputs": {
                "allow_data_lake_write": True,
                "data_lake_dossier_path": str(tmp_path),
                "p1_dossiers": [
                    {
                        "identity": {"name": "Arianna Simpson", "linkedin_url": "https://www.linkedin.com/in/ariannasimpson"},
                        "historical_context": {"v2_triage_score": 81},
                        "live_intelligence": {"exa_raw_urls": ["https://example.com"]},
                        "gateway_evaluations": {"status": "UNPROCESSED"},
                        "outreach": {"status": "NONE"},
                    }
                ],
            }
        },
        {},
    )

    assert result["sync_result"]["written_count"] == 1
    written = tmp_path / "arianna_simpson.json"
    assert written.exists()
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["identity"]["name"] == "Arianna Simpson"
    assert payload["runtime_source"] == "p1-operator-outreach"


def test_p1_outreach_master_sync_appends_drafts(tmp_path: Path) -> None:
    master_path = tmp_path / "Outreach_Drafts_Master.json"
    master_path.write_text(json.dumps({"drafts": [{"name": "Existing"}]}), encoding="utf-8")

    result = sync_outreach_master(
        {
            "inputs": {
                "allow_outreach_master_write": True,
                "outreach_master_path": str(master_path),
                "approval_package": {
                    "outreach_drafts": [
                        {
                            "name": "Arianna Simpson",
                            "linkedin_url": "https://www.linkedin.com/in/ariannasimpson",
                            "text": "Hi Arianna, ABRT is building an operator-led AI-native VC model.",
                            "evidence_urls": ["https://www.linkedin.com/in/ariannasimpson"],
                            "claims": [{"text": "Arianna is an investor.", "source_url": "https://www.linkedin.com/in/ariannasimpson"}],
                            "status": "draft",
                        }
                    ]
                },
            }
        },
        {},
    )

    assert result["sync_result"]["written_count"] == 1
    payload = json.loads(master_path.read_text(encoding="utf-8"))
    assert [item["name"] for item in payload["drafts"]] == ["Existing", "Arianna Simpson"]
    assert payload["drafts"][1]["runtime_source"] == "p1-operator-outreach"


def test_p1_metrics_report_counts_full_funnel() -> None:
    result = build_metrics_report(
        {
            "inputs": {
                "lead_candidates": [{"name": "A"}, {"name": "B"}, {"name": "C"}],
                "normalized_leads": [{"name": "A"}, {"name": "B"}],
                "rejected_leads": [{"name": "C"}],
                "triage_scores": [
                    {"name": "A", "triage": {"qualified": True}},
                    {"name": "B", "triage": {"qualified": False}},
                ],
                "p1_dossiers": [{"identity": {"name": "A"}}],
                "gateway_evaluations": [
                    {"gateway": {"decision": "awaiting_outreach"}},
                    {"gateway": {"decision": "bypass"}},
                ],
                "outreach_drafts": [{"name": "A"}],
                "quality_eval": {"passed": True, "score": 1.0},
                "external_sync_results": {
                    "google_sheets": {"row_count": 1},
                    "data_lake": {"written_count": 1},
                    "outreach_master": {"written_count": 1},
                },
            }
        },
        {},
    )

    assert result["metrics"] == {
        "raw_leads": 3,
        "normalized_leads": 2,
        "rejected_leads": 1,
        "triage_qualified": 1,
        "triage_rejected": 1,
        "dossiers": 1,
        "gateway_approved": 1,
        "gateway_rejected": 1,
        "drafted": 1,
        "eval_passed": True,
        "sheet_written": 1,
        "data_lake_written": 1,
        "outreach_master_written": 1,
    }
