import json
from pathlib import Path
from urllib.error import HTTPError

from l2l3_protocol.workers.p1_operator_worker import (
    _apify_crunchbase_search,
    _apify_funding_search,
    _apify_linkedin_search,
    _ensure_google_sheet_headers,
    _gemini_json,
    _request_json,
    _redact_secrets,
    _run_apify_actor,
    P1WorkerInputError,
    build_metrics_report,
    collect_sources,
    evaluate_gateway,
    judge_outreach_quality,
    gather_live_intelligence,
    merge_source_batches,
    normalize_leads,
    read_existing_dossiers,
    score_triage,
    sync_data_lake,
    sync_outreach_master,
    write_dossiers,
    write_outreach_drafts,
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
                        "run_id": "run-1",
                        "lead_id": "lead-1",
                        "idempotency_key": "run-1:lead-1",
                        "name": "Adeline Lee",
                        "linkedin_url": "https://de.linkedin.com/in/adelineleecs",
                        "identity_status": "verified_linkedin",
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


def test_p1_outreach_writer_enforces_abrt_or_limpid_mention(monkeypatch) -> None:
    monkeypatch.setattr("l2l3_protocol.workers.p1_operator_worker._gemini_client", lambda: object())
    monkeypatch.setattr(
        "l2l3_protocol.workers.p1_operator_worker._gemini_json",
        lambda _client, _prompt: {
            "archetype": "Builder",
            "draft": "Hi Arianna, your operator-investor pattern is exactly the kind of thinking we wanted to compare notes on next week.",
            "evidence_urls": ["https://www.linkedin.com/in/ariannasimpson"],
            "claims": [{"text": "Arianna is an operator-investor.", "source_url": "https://www.linkedin.com/in/ariannasimpson"}],
        },
    )

    result = write_outreach_drafts(
        {
            "inputs": {
                "forge_queue": [
                    {
                        "dossier": {
                            "identity": {"name": "Arianna Simpson", "linkedin_url": "https://www.linkedin.com/in/ariannasimpson", "identity_status": "verified_linkedin"},
                            "live_intelligence": {"exa_raw_urls": ["https://www.linkedin.com/in/ariannasimpson"]},
                        },
                        "gateway": {"current_role_verified": "Investor"},
                    }
                ]
            }
        },
        {},
    )

    assert "abrt" in result["outreach_drafts"][0]["text"].lower() or "limpid" in result["outreach_drafts"][0]["text"].lower()


def test_p1_outreach_writer_enforces_send_ready_cta(monkeypatch) -> None:
    monkeypatch.setattr("l2l3_protocol.workers.p1_operator_worker._gemini_client", lambda: object())
    monkeypatch.setattr(
        "l2l3_protocol.workers.p1_operator_worker._gemini_json",
        lambda _client, _prompt: {
            "archetype": "Builder",
            "draft": "Hi Arianna, ABRT is mapping operator-investors with strong consumer product judgment.",
            "evidence_urls": ["https://www.linkedin.com/in/ariannasimpson"],
            "claims": [{"text": "Arianna is an operator-investor.", "source_url": "https://www.linkedin.com/in/ariannasimpson"}],
        },
    )

    result = write_outreach_drafts(
        {
            "inputs": {
                "forge_queue": [
                    {
                        "dossier": {
                            "identity": {"name": "Arianna Simpson", "linkedin_url": "https://www.linkedin.com/in/ariannasimpson", "identity_status": "verified_linkedin"},
                            "live_intelligence": {"exa_raw_urls": ["https://www.linkedin.com/in/ariannasimpson"]},
                        },
                        "gateway": {"current_role_verified": "Investor"},
                    }
                ]
            }
        },
        {},
    )

    draft = result["outreach_drafts"][0]
    assert "30-minute call" in draft["text"]
    assert judge_outreach_quality({"inputs": {"outreach_drafts": [draft]}}, {})["passed"] is True


def test_p1_outreach_writer_removes_placeholder_signoff(monkeypatch) -> None:
    monkeypatch.setattr("l2l3_protocol.workers.p1_operator_worker._gemini_client", lambda: object())
    monkeypatch.setattr(
        "l2l3_protocol.workers.p1_operator_worker._gemini_json",
        lambda _client, _prompt: {
            "archetype": "Builder",
            "draft": "Hi Arianna, ABRT is mapping operator-investors with strong consumer product judgment. Would a quick 30-minute call next week make sense?\n\nBest,",
            "evidence_urls": ["https://www.linkedin.com/in/ariannasimpson"],
            "claims": [{"text": "Arianna is an operator-investor.", "source_url": "https://www.linkedin.com/in/ariannasimpson"}],
        },
    )

    result = write_outreach_drafts(
        {
            "inputs": {
                "forge_queue": [
                    {
                        "dossier": {
                            "identity": {"name": "Arianna Simpson", "linkedin_url": "https://www.linkedin.com/in/ariannasimpson", "identity_status": "verified_linkedin"},
                            "live_intelligence": {"exa_raw_urls": ["https://www.linkedin.com/in/ariannasimpson"]},
                        },
                        "gateway": {"current_role_verified": "Investor"},
                    }
                ]
            }
        },
        {},
    )

    draft = result["outreach_drafts"][0]
    assert not draft["text"].lower().endswith("best,")
    assert judge_outreach_quality({"inputs": {"outreach_drafts": [draft]}}, {})["passed"] is True


def test_p1_outreach_writer_removes_inline_placeholder_signoff(monkeypatch) -> None:
    monkeypatch.setattr("l2l3_protocol.workers.p1_operator_worker._gemini_client", lambda: object())
    monkeypatch.setattr(
        "l2l3_protocol.workers.p1_operator_worker._gemini_json",
        lambda _client, _prompt: {
            "archetype": "Builder",
            "draft": "Hi Arianna, ABRT is mapping operator-investors with strong consumer product judgment. Would a quick 30-minute call next week make sense? Best,",
            "evidence_urls": ["https://www.linkedin.com/in/ariannasimpson"],
            "claims": [{"text": "Arianna is an operator-investor.", "source_url": "https://www.linkedin.com/in/ariannasimpson"}],
        },
    )

    result = write_outreach_drafts(
        {
            "inputs": {
                "forge_queue": [
                    {
                        "dossier": {
                            "identity": {"name": "Arianna Simpson", "linkedin_url": "https://www.linkedin.com/in/ariannasimpson", "identity_status": "verified_linkedin"},
                            "live_intelligence": {"exa_raw_urls": ["https://www.linkedin.com/in/ariannasimpson"]},
                        },
                        "gateway": {"current_role_verified": "Investor"},
                    }
                ]
            }
        },
        {},
    )

    draft = result["outreach_drafts"][0]
    assert not draft["text"].lower().endswith("best,")
    assert judge_outreach_quality({"inputs": {"outreach_drafts": [draft]}}, {})["passed"] is True


def test_p1_normalizer_rejects_broken_person_name() -> None:
    result = normalize_leads(
        {
            "inputs": {
                "lead_candidates": [
                    {"name": "ann✺b", "source_url": "https://annbordetsky.com", "source": "exa"},
                    {"name": "Elad Gil", "linkedin_url": "https://www.linkedin.com/in/eladgil/", "source": "apify_linkedin"},
                ]
            }
        },
        {},
    )

    assert result["normalized_leads"][0]["name"] == "Elad Gil"
    assert result["normalized_leads"][0]["linkedin_url"] == "https://www.linkedin.com/in/eladgil"
    assert result["normalized_leads"][0]["identity_status"] == "verified_linkedin"
    assert result["rejected_leads"][0]["reason"] == "invalid_person_name"


def test_p1_normalizer_accepts_country_subdomain_linkedin_person_url() -> None:
    result = normalize_leads(
        {
            "inputs": {
                "lead_candidates": [
                    {"name": "Adeline Lee", "linkedin_url": "http://ca.linkedin.com/in/adelineleecs/", "source": "apify_linkedin"},
                ]
            }
        },
        {},
    )

    assert result["normalized_leads"][0]["linkedin_url"] == "http://ca.linkedin.com/in/adelineleecs"
    assert result["normalized_leads"][0]["identity_status"] == "verified_linkedin"


def test_p1_normalizer_allows_mononym_when_linkedin_is_valid() -> None:
    result = normalize_leads(
        {
            "inputs": {
                "lead_candidates": [
                    {"name": "Dara", "linkedin_url": "https://www.linkedin.com/in/dara", "source": "apify_linkedin"},
                ]
            }
        },
        {},
    )

    assert result["normalized_leads"][0]["name"] == "Dara"
    assert result["normalized_leads"][0]["identity_status"] == "verified_linkedin"


def test_p1_normalizer_rejects_non_profile_linkedin_subdomain_shape() -> None:
    result = normalize_leads(
        {
            "inputs": {
                "lead_candidates": [
                    {"name": "Adeline Lee", "linkedin_url": "https://touch.linkedin.com/in/adelineleecs", "source": "exa"},
                ]
            }
        },
        {},
    )

    assert result["normalized_leads"][0]["linkedin_url"] == ""
    assert result["normalized_leads"][0]["identity_status"] == "needs_review"


def test_p1_live_intelligence_repairs_missing_linkedin_from_real_evidence(monkeypatch) -> None:
    monkeypatch.setattr(
        "l2l3_protocol.workers.p1_operator_worker._exa_people_search",
        lambda _query, _limit: [
            {"source_url": "https://www.linkedin.com/in/navalr", "headline": "Naval Ravikant", "evidence": ["AngelList co-founder"]},
            {"source_url": "https://example.com/naval", "headline": "Naval Ravikant", "evidence": ["Investor"]},
        ],
    )

    result = gather_live_intelligence(
        {
            "inputs": {
                "exa_results_per_dossier": 2,
                "p1_dossiers": [
                    {
                        "identity": {"name": "Naval Ravikant", "linkedin_url": "", "identity_status": "needs_review"},
                        "historical_context": {"all_recorded_headlines": ["AngelList co-founder and angel investor"]},
                        "live_intelligence": {},
                        "gateway_evaluations": {"status": "UNPROCESSED"},
                        "outreach": {"status": "NONE"},
                    }
                ],
            }
        },
        {},
    )

    identity = result["p1_dossiers"][0]["identity"]
    assert identity["linkedin_url"] == "https://www.linkedin.com/in/navalr"
    assert identity["identity_status"] == "verified_linkedin"


def test_p1_gateway_blocks_unverified_linkedin_even_when_model_passes(monkeypatch) -> None:
    monkeypatch.setattr("l2l3_protocol.workers.p1_operator_worker._gemini_client", lambda: object())
    monkeypatch.setattr(
        "l2l3_protocol.workers.p1_operator_worker._gemini_json",
        lambda _client, _prompt: {
            "identity_confidence": 100,
            "product_b2c_fit": "PASS",
            "product_leadership_fit": "PASS",
            "verified_investor_fit": "PASS",
            "bandwidth_signal": "HIGH",
            "liquidity_signal": "YES",
            "systematic_alignment": "YES",
            "exclusion_signal": "NO",
            "current_role_verified": "Angel investor",
            "evidence_urls": ["https://www.crunchbase.com/person/naval-ravikant"],
            "mythos_dossier": "Model says yes, deterministic identity gate says not yet.",
        },
    )

    result = evaluate_gateway(
        {
            "inputs": {
                "p1_dossiers": [
                    {
                        "identity": {"name": "Naval Ravikant", "linkedin_url": "", "identity_status": "needs_review"},
                        "historical_context": {"all_recorded_headlines": ["AngelList co-founder"]},
                        "live_intelligence": {"exa_raw_urls": ["https://www.crunchbase.com/person/naval-ravikant"]},
                        "gateway_evaluations": {"status": "UNPROCESSED"},
                        "outreach": {"status": "NONE"},
                    }
                ]
            }
        },
        {},
    )

    gateway = result["gateway_evaluations"][0]["gateway"]
    assert gateway["decision"] == "needs_more_evidence"
    assert "missing_verified_person_linkedin" in gateway["decision_reasons"]
    assert "identity_status_not_verified:needs_review" in gateway["decision_reasons"]


def test_p1_gateway_blocks_dead_live_linkedin_before_outreach(monkeypatch) -> None:
    monkeypatch.setattr("l2l3_protocol.workers.p1_operator_worker._gemini_client", lambda: object())
    monkeypatch.setattr("l2l3_protocol.workers.p1_operator_worker._linkedin_profile_url_is_live", lambda _url: False)
    monkeypatch.setattr(
        "l2l3_protocol.workers.p1_operator_worker._gemini_json",
        lambda _client, _prompt: {
            "identity_confidence": 100,
            "product_b2c_fit": "PASS",
            "product_leadership_fit": "PASS",
            "verified_investor_fit": "PASS",
            "bandwidth_signal": "HIGH",
            "liquidity_signal": "YES",
            "systematic_alignment": "YES",
            "exclusion_signal": "NO",
            "current_role_verified": "Angel investor",
            "evidence_urls": ["https://www.linkedin.com/in/navalr", "https://www.crunchbase.com/person/naval-ravikant"],
            "mythos_dossier": "Model says yes, deterministic live LinkedIn gate says not outreach-ready.",
        },
    )

    result = evaluate_gateway(
        {
            "inputs": {
                "verify_linkedin_live": True,
                "p1_dossiers": [
                    {
                        "identity": {"name": "Naval Ravikant", "linkedin_url": "https://www.linkedin.com/in/navalr", "identity_status": "verified_linkedin"},
                        "historical_context": {"all_recorded_headlines": ["AngelList co-founder"]},
                        "live_intelligence": {"exa_raw_urls": ["https://www.linkedin.com/in/navalr", "https://www.crunchbase.com/person/naval-ravikant"]},
                        "gateway_evaluations": {"status": "UNPROCESSED"},
                        "outreach": {"status": "NONE"},
                    }
                ],
            }
        },
        {},
    )

    gateway = result["gateway_evaluations"][0]["gateway"]
    assert gateway["decision"] == "needs_more_evidence"
    assert "linkedin_profile_not_live" in gateway["decision_reasons"]


def test_p1_outreach_quality_rejects_unverified_linkedin_identity() -> None:
    result = judge_outreach_quality(
        {
            "inputs": {
                "outreach_drafts": [
                    {
                        "run_id": "run-1",
                        "lead_id": "lead-1",
                        "idempotency_key": "run-1:lead-1",
                        "name": "Naval Ravikant",
                        "linkedin_url": "",
                        "identity_status": "needs_review",
                        "text": "ABRT is building Limpid around operator product DNA. Would a quick 30-minute call next week make sense?",
                        "evidence_urls": ["https://www.crunchbase.com/person/naval-ravikant"],
                        "claims": [{"text": "Naval is an investor.", "source_url": "https://www.crunchbase.com/person/naval-ravikant"}],
                        "status": "draft",
                        "publish": False,
                    }
                ]
            }
        },
        {},
    )

    assert result["passed"] is False
    assert "all_have_verified_person_linkedin" in result["reasons"]


def test_p1_outreach_quality_rejects_linkedin_without_matching_evidence() -> None:
    result = judge_outreach_quality(
        {
            "inputs": {
                "outreach_drafts": [
                    {
                        "run_id": "run-1",
                        "lead_id": "lead-1",
                        "idempotency_key": "run-1:lead-1",
                        "name": "Elad Gil",
                        "linkedin_url": "https://www.linkedin.com/in/eladgil",
                        "identity_status": "verified_linkedin",
                        "text": "ABRT is building Limpid around operator-led investing. Would a quick 30-minute call next week make sense?",
                        "evidence_urls": ["https://www.crunchbase.com/person/elad-gil"],
                        "claims": [{"text": "Elad has operator-investor experience.", "source_url": "https://www.crunchbase.com/person/elad-gil"}],
                        "status": "draft",
                        "publish": False,
                    }
                ]
            }
        },
        {},
    )

    assert result["passed"] is False
    assert "all_linkedin_urls_are_evidence_backed" in result["reasons"]


def test_p1_outreach_quality_rejects_dead_live_linkedin_profile(monkeypatch) -> None:
    monkeypatch.setattr("l2l3_protocol.workers.p1_operator_worker._linkedin_profile_url_is_live", lambda _url: False)

    result = judge_outreach_quality(
        {
            "inputs": {
                "verify_linkedin_live": True,
                "outreach_drafts": [
                    {
                        "run_id": "run-1",
                        "lead_id": "lead-1",
                        "idempotency_key": "run-1:lead-1",
                        "name": "Naval Ravikant",
                        "linkedin_url": "https://www.linkedin.com/in/navalr",
                        "identity_status": "verified_linkedin",
                        "text": "ABRT is building Limpid around operator-led investing. Would a quick 30-minute call next week make sense?",
                        "evidence_urls": ["https://www.linkedin.com/in/navalr"],
                        "claims": [{"text": "Naval has operator-investor experience.", "source_url": "https://www.linkedin.com/in/navalr"}],
                        "status": "draft",
                        "publish": False,
                    }
                ],
            }
        },
        {},
    )

    assert result["passed"] is False
    assert "all_have_live_linkedin_profile" in result["reasons"]


def test_p1_outreach_quality_accepts_live_verified_evidence_backed_linkedin(monkeypatch) -> None:
    monkeypatch.setattr("l2l3_protocol.workers.p1_operator_worker._linkedin_profile_url_is_live", lambda _url: True)

    result = judge_outreach_quality(
        {
            "inputs": {
                "verify_linkedin_live": True,
                "outreach_drafts": [
                    {
                        "run_id": "run-1",
                        "lead_id": "lead-1",
                        "idempotency_key": "run-1:lead-1",
                        "name": "Elad Gil",
                        "linkedin_url": "https://www.linkedin.com/in/eladgil",
                        "identity_status": "verified_linkedin",
                        "text": "ABRT is building Limpid around operator-led investing. Would a quick 30-minute call next week make sense?",
                        "evidence_urls": ["https://www.linkedin.com/in/eladgil"],
                        "claims": [{"text": "Elad has operator-investor experience.", "source_url": "https://www.linkedin.com/in/eladgil"}],
                        "status": "draft",
                        "publish": False,
                    }
                ],
            }
        },
        {},
    )

    assert result["passed"] is True


def test_p1_outreach_quality_rejects_duplicate_meeting_cta() -> None:
    result = judge_outreach_quality(
        {
            "inputs": {
                "outreach_drafts": [
                    {
                        "run_id": "run-1",
                        "lead_id": "lead-1",
                        "idempotency_key": "run-1:lead-1",
                        "name": "Elad Gil",
                        "linkedin_url": "https://www.linkedin.com/in/eladgil",
                        "identity_status": "verified_linkedin",
                        "text": (
                            "Hi Elad, ABRT is building Limpid around operator-led investing. "
                            "I'd love to connect for 30 minutes next week to compare notes. "
                            "Would a quick 30-minute call next week make sense?"
                        ),
                        "evidence_urls": ["https://www.linkedin.com/in/eladgil"],
                        "claims": [{"text": "Elad has operator-investor experience.", "source_url": "https://www.linkedin.com/in/eladgil"}],
                        "status": "draft",
                        "publish": False,
                    }
                ]
            }
        },
        {},
    )

    assert result["passed"] is False
    assert "single_meeting_cta" in result["reasons"]


def test_p1_outreach_quality_rejects_same_sentence_duplicate_meeting_cta() -> None:
    result = judge_outreach_quality(
        {
            "inputs": {
                "outreach_drafts": [
                    {
                        "run_id": "run-1",
                        "lead_id": "lead-1",
                        "idempotency_key": "run-1:lead-1",
                        "name": "Elad Gil",
                        "linkedin_url": "https://www.linkedin.com/in/eladgil",
                        "identity_status": "verified_linkedin",
                        "text": "ABRT is building Limpid around operator-led investing. Would a quick 30-minute call next week or a brief chat next week make sense?",
                        "evidence_urls": ["https://www.linkedin.com/in/eladgil"],
                        "claims": [{"text": "Elad has operator-investor experience.", "source_url": "https://www.linkedin.com/in/eladgil"}],
                        "status": "draft",
                        "publish": False,
                    }
                ]
            }
        },
        {},
    )

    assert result["passed"] is False
    assert "single_meeting_cta" in result["reasons"]


def test_p1_outreach_quality_rejects_resonates_only_without_meeting_cta() -> None:
    result = judge_outreach_quality(
        {
            "inputs": {
                "outreach_drafts": [
                    {
                        "run_id": "run-1",
                        "lead_id": "lead-1",
                        "idempotency_key": "run-1:lead-1",
                        "name": "Elad Gil",
                        "linkedin_url": "https://www.linkedin.com/in/eladgil",
                        "identity_status": "verified_linkedin",
                        "text": "ABRT is building Limpid around operator-led investing. Curious whether that thesis resonates.",
                        "evidence_urls": ["https://www.linkedin.com/in/eladgil"],
                        "claims": [{"text": "Elad has operator-investor experience.", "source_url": "https://www.linkedin.com/in/eladgil"}],
                        "status": "draft",
                        "publish": False,
                    }
                ]
            }
        },
        {},
    )

    assert result["passed"] is False
    assert "has_clear_cta" in result["reasons"]


def test_google_sheet_header_update_uses_values_update_range(monkeypatch) -> None:
    calls = []

    def fake_request_json(url, method="GET", token=None, body=None, timeout=120):
        calls.append({"url": url, "method": method, "body": body})
        if method == "GET":
            return {"values": []}
        return {"updatedRange": "P1_L2L3_NEW_LEADS!1:1"}

    monkeypatch.setattr("l2l3_protocol.workers.p1_operator_worker._request_json", fake_request_json)

    _ensure_google_sheet_headers("sheet-id", "P1_L2L3_NEW_LEADS", "token")

    put_call = next(call for call in calls if call["method"] == "PUT")
    assert "%211%3A1?valueInputOption=RAW" in put_call["url"]
    assert ":update" not in put_call["url"]


def test_gemini_json_retries_invalid_json_with_json_mime_config() -> None:
    class Response:
        def __init__(self, text: str):
            self.text = text

    class Models:
        def __init__(self):
            self.calls = []

        def generate_content(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return Response('{"score": 1')
            return Response('{"score": 1}')

    class Client:
        def __init__(self):
            self.models = Models()

    client = Client()

    result = _gemini_json(client, "Return JSON.")

    assert result == {"score": 1}
    assert len(client.models.calls) == 2
    assert client.models.calls[0]["config"].response_mime_type == "application/json"
    assert "Return one complete valid JSON object only" in client.models.calls[1]["contents"]


def test_p1_http_error_redaction_removes_provider_tokens() -> None:
    raw = "https://api.apify.com/v2/acts/a/runs?token=apify_api_MsDummySecretWithS123 apify_api_MsDummySecretWithS123"

    redacted = _redact_secrets(raw)

    assert "MsDummySecretWithS123" not in redacted
    assert "token=[REDACTED]" in redacted
    assert "apify_api_[REDACTED]" in redacted


def test_p1_request_json_retries_transient_get_http_errors(monkeypatch) -> None:
    calls = {"count": 0}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise HTTPError(request.full_url, 502, "Bad Gateway", hdrs=None, fp=None)
        return Response()

    monkeypatch.setattr("l2l3_protocol.workers.p1_operator_worker.urlopen", fake_urlopen)
    monkeypatch.setattr("l2l3_protocol.workers.p1_operator_worker.time.sleep", lambda _seconds: None)

    assert _request_json("https://api.apify.com/v2/actor-runs/run-id?token=secret") == {"ok": True}
    assert calls["count"] == 2


def test_p1_triage_blocks_high_score_without_check_writer_proof(monkeypatch) -> None:
    monkeypatch.setattr("l2l3_protocol.workers.p1_operator_worker._gemini_client", lambda: object())
    monkeypatch.setattr(
        "l2l3_protocol.workers.p1_operator_worker._gemini_json",
        lambda _client, _prompt: {
            "b2c_plg_dna_score": 30,
            "product_leadership_score": 20,
            "verified_angel_score": 20,
            "liquidity_ecosystem_score": 10,
            "systematic_fit_score": 10,
            "geography_language_score": 5,
            "hard_gates": {
                "b2c_or_plg_product_experience": True,
                "product_leadership": True,
                "verified_angel_or_check_writer": False,
                "geography_language_fit": True,
                "excluded_industry": False,
                "excluded_profile_type": False,
            },
            "evidence_urls": ["https://www.linkedin.com/in/operator"],
            "reasoning": "Strong product operator, but no personal angel portfolio proof.",
        },
    )

    scored = score_triage(
        {
            "inputs": {
                "normalized_leads": [
                    {
                        "lead_id": "lead-1",
                        "name": "Strong Operator",
                        "headline": "Former VP Product at Consumer App",
                        "linkedin_url": "https://www.linkedin.com/in/operator",
                    }
                ]
            }
        },
        {},
    )

    triage = scored["triage_scores"][0]["triage"]
    assert triage["total_score"] == 95
    assert triage["qualified"] is False
    assert triage["status"] == "needs_enrichment"
    assert triage["missing_required_gates"] == ["verified_angel_or_check_writer"]


def test_p1_triage_allows_only_gateway_eligible_golden_icp(monkeypatch) -> None:
    monkeypatch.setattr("l2l3_protocol.workers.p1_operator_worker._gemini_client", lambda: object())
    monkeypatch.setattr(
        "l2l3_protocol.workers.p1_operator_worker._gemini_json",
        lambda _client, _prompt: {
            "b2c_plg_dna_score": 28,
            "product_leadership_score": 20,
            "verified_angel_score": 25,
            "liquidity_ecosystem_score": 8,
            "systematic_fit_score": 8,
            "geography_language_score": 5,
            "hard_gates": {
                "b2c_or_plg_product_experience": True,
                "product_leadership": True,
                "verified_angel_or_check_writer": True,
                "geography_language_fit": True,
                "excluded_industry": False,
                "excluded_profile_type": False,
            },
            "evidence_urls": ["https://www.linkedin.com/in/productangel", "https://angel.co/u/productangel"],
            "reasoning": "Product leader with public angel portfolio.",
        },
    )

    scored = score_triage(
        {
            "inputs": {
                "normalized_leads": [
                    {
                        "lead_id": "lead-2",
                        "name": "Product Angel",
                        "headline": "CPO and Angel Investor",
                        "linkedin_url": "https://www.linkedin.com/in/productangel",
                    }
                ]
            }
        },
        {},
    )

    triage = scored["triage_scores"][0]["triage"]
    assert triage["qualified"] is True
    assert triage["quality_band"] == "gold"
    assert triage["status"] == "gateway_eligible"
    dossiers = write_dossiers({"inputs": {"triage_scores": scored["triage_scores"]}}, {})
    assert dossiers["p1_dossiers"][0]["historical_context"]["p1_hard_gates"]["verified_angel_or_check_writer"] is True


def test_p1_gateway_requires_verified_investor_product_and_evidence(monkeypatch) -> None:
    monkeypatch.setattr("l2l3_protocol.workers.p1_operator_worker._gemini_client", lambda: object())
    monkeypatch.setattr(
        "l2l3_protocol.workers.p1_operator_worker._gemini_json",
        lambda _client, _prompt: {
            "identity_confidence": 98,
            "product_b2c_fit": "PASS",
            "product_leadership_fit": "PASS",
            "verified_investor_fit": "FAIL",
            "bandwidth_signal": "HIGH",
            "liquidity_signal": "YES",
            "systematic_alignment": "YES",
            "exclusion_signal": "NO",
            "current_role_verified": "Independent product advisor",
            "evidence_urls": ["https://www.linkedin.com/in/operator"],
            "mythos_dossier": "Strong operator, but no personal investing evidence.",
        },
    )

    result = evaluate_gateway(
        {
            "inputs": {
                "p1_dossiers": [
                    {
                        "identity": {"name": "Strong Operator", "linkedin_url": "https://www.linkedin.com/in/operator", "identity_status": "verified_linkedin"},
                        "historical_context": {"all_recorded_headlines": ["Former CPO"]},
                        "live_intelligence": {"exa_raw_urls": ["https://www.linkedin.com/in/operator"]},
                        "gateway_evaluations": {"status": "UNPROCESSED"},
                        "outreach": {"status": "NONE"},
                    }
                ]
            }
        },
        {},
    )

    gateway = result["gateway_evaluations"][0]["gateway"]
    assert gateway["decision"] == "needs_more_evidence"
    assert gateway["decision_reasons"] == ["missing_verified_angel_or_check_writer_fit"]


def test_p1_gateway_approves_full_golden_icp(monkeypatch) -> None:
    monkeypatch.setattr("l2l3_protocol.workers.p1_operator_worker._gemini_client", lambda: object())
    monkeypatch.setattr(
        "l2l3_protocol.workers.p1_operator_worker._gemini_json",
        lambda _client, _prompt: {
            "identity_confidence": 96,
            "product_b2c_fit": "PASS",
            "product_leadership_fit": "PASS",
            "verified_investor_fit": "PASS",
            "bandwidth_signal": "HIGH",
            "liquidity_signal": "YES",
            "systematic_alignment": "YES",
            "exclusion_signal": "NO",
            "current_role_verified": "Fractional CPO and angel investor",
            "evidence_urls": ["https://www.linkedin.com/in/productangel", "https://angel.co/u/productangel"],
            "mythos_dossier": "Verified product-led operator angel with bandwidth.",
        },
    )

    result = evaluate_gateway(
        {
            "inputs": {
                "p1_dossiers": [
                    {
                        "identity": {"name": "Product Angel", "linkedin_url": "https://www.linkedin.com/in/productangel", "identity_status": "verified_linkedin"},
                        "historical_context": {"all_recorded_headlines": ["CPO and Angel Investor"]},
                        "live_intelligence": {"exa_raw_urls": ["https://angel.co/u/productangel"]},
                        "gateway_evaluations": {"status": "UNPROCESSED"},
                        "outreach": {"status": "NONE"},
                    }
                ]
            }
        },
        {},
    )

    gateway = result["gateway_evaluations"][0]["gateway"]
    assert gateway["decision"] == "awaiting_outreach"
    assert gateway["decision_reasons"] == []


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


def test_p1_funding_source_enriches_company_rows_into_founder_leads(monkeypatch) -> None:
    def fake_run(actor_id, actor_input):
        assert actor_id == "nexgendata/startup-funding-tracker"
        assert actor_input["maxItems"] == 1
        assert actor_input["maxResults"] == 1
        return [
            {
                "companyName": "Pixley AI",
                "fundingAmount": 0,
                "roundType": "YC F25",
                "investors": "Y Combinator",
                "industry": "Consumer, Content",
                "sourceUrl": "https://www.ycombinator.com/companies/pixley-ai",
            }
        ]

    def fake_exa(query, limit):
        assert "Pixley AI founder LinkedIn" in query
        return [
            {
                "name": "Pixley AI",
                "headline": "Pixley AI | LinkedIn",
                "source_url": "https://www.linkedin.com/company/pixley-ai",
                "source": "exa",
                "evidence": ["Pixley AI company page"],
            },
            {
                "name": "Maya Chen",
                "headline": "Founder at Pixley AI",
                "source_url": "https://www.linkedin.com/in/mayachen",
                "source": "exa",
                "evidence": ["Founder at Pixley AI"],
            }
        ]

    monkeypatch.setattr("l2l3_protocol.workers.p1_operator_worker._run_apify_actor", fake_run)
    monkeypatch.setattr("l2l3_protocol.workers.p1_operator_worker._exa_people_search", fake_exa)

    result = _apify_funding_search({"apify_search_query": "AI consumer startup", "days_back": 60}, 1)

    assert result[0]["name"] == "Maya Chen"
    assert result[0]["headline"] == "Founder at Pixley AI"
    assert result[0]["source"] == "apify_funding"
    assert result[0]["source_url"] == "https://www.linkedin.com/in/mayachen"
    assert "Pixley AI" in result[0]["evidence"][0]


def test_apify_actor_run_request_includes_charged_max_items(monkeypatch) -> None:
    calls = []

    def fake_request_json(url, method="GET", token=None, body=None, timeout=120):
        calls.append({"url": url, "method": method, "body": body})
        if "/runs?" in url:
            return {"data": {"id": "run-1"}}
        if "/actor-runs/run-1" in url:
            return {"data": {"status": "SUCCEEDED", "defaultDatasetId": "dataset-1"}}
        if "/datasets/dataset-1/items" in url:
            return [{"name": "Maya Chen"}]
        raise AssertionError(url)

    monkeypatch.setenv("APIFY_API_TOKEN", "token")
    monkeypatch.setattr("l2l3_protocol.workers.p1_operator_worker._request_json", fake_request_json)

    result = _run_apify_actor("nexgendata/startup-funding-tracker", {"maxItems": 1, "timeoutSeconds": 1})

    assert result == [{"name": "Maya Chen"}]
    assert calls[0]["method"] == "POST"
    assert "maxItems=1" in calls[0]["url"]


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


def test_p1_source_collector_reuses_explicit_provider_cache(tmp_path: Path, monkeypatch) -> None:
    calls = {"count": 0}

    def fake_run(actor_id, actor_input):
        calls["count"] += 1
        assert actor_id == "riceman/linkedin-sales-navigator-lead-search-scraper"
        return [
            {
                "full_name": "Arianna Simpson",
                "headline": "General Partner at a16z crypto",
                "linkedin_url": "https://www.linkedin.com/in/ariannasimpson/",
            }
        ]

    monkeypatch.setattr("l2l3_protocol.workers.p1_operator_worker._run_apify_actor", fake_run)
    inputs = {
        "sources": ["apify_linkedin"],
        "linkedin_keywords": "AI angel investor",
        "limit": 1,
        "provider_cache_dir": str(tmp_path / "provider-cache"),
    }

    first = collect_sources({"inputs": inputs}, {})

    assert calls["count"] == 1
    assert first["source_attempts"][0]["cache_enabled"] is True
    assert first["source_attempts"][0]["cache_hit"] is False
    assert first["source_attempts"][0]["query_hash"]
    assert first["source_attempts"][0]["safe_query_summary"]
    assert first["source_attempts"][0]["attempt_count"] == 1
    assert first["lead_candidates"][0]["name"] == "Arianna Simpson"

    def fail_if_called(actor_id, actor_input):
        raise AssertionError("provider should not be called when explicit real cache is valid")

    monkeypatch.setattr("l2l3_protocol.workers.p1_operator_worker._run_apify_actor", fail_if_called)

    second = collect_sources({"inputs": inputs}, {})

    assert second["source_attempts"][0]["cache_hit"] is True
    assert second["source_attempts"][0]["cache_key"] == first["source_attempts"][0]["cache_key"]
    assert second["lead_candidates"] == first["lead_candidates"]


def test_p1_source_collector_preserves_zero_result_source_without_failing(monkeypatch) -> None:
    monkeypatch.setattr("l2l3_protocol.workers.p1_operator_worker._exa_people_search", lambda _query, _limit: [])

    result = collect_sources({"inputs": {"mode": "source_only", "sources": ["exa"], "limit": 5, "use_provider_cache": False}}, {})

    assert result["lead_candidates"] == []
    assert result["source_attempts"][0]["provider"] == "exa"
    assert result["source_attempts"][0]["result_count"] == 0


def test_p1_source_merger_fails_only_when_all_sources_are_empty() -> None:
    try:
        merge_source_batches(
            {
                "inputs": {
                    "source_batches": [
                        {"source": "exa", "lead_candidates": [], "source_attempts": [{"provider": "exa", "result_count": 0}]},
                        {"source": "apify_linkedin", "lead_candidates": [], "source_attempts": [{"provider": "apify_linkedin", "result_count": 0}]},
                    ]
                }
            },
            {},
        )
    except ValueError as exc:
        assert "real P1 sourcing returned no lead candidates after merging source batches" in str(exc)
    else:
        raise AssertionError("expected source merge failure")


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
    written = Path(result["sync_result"]["files"][0]["path"])
    assert written.exists()
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["identity"]["name"] == "Arianna Simpson"
    assert payload["runtime_source"] == "p1-operator-outreach"


def test_p1_data_lake_sync_requires_explicit_output_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("P1_DOSSIER_SOURCE_PATH", str(tmp_path))

    try:
        sync_data_lake({"inputs": {"allow_data_lake_write": True, "p1_dossiers": []}}, {})
    except P1WorkerInputError as exc:
        assert "data_lake_dossier_path" in str(exc)
    else:
        raise AssertionError("expected data lake sync to reject source path fallback")


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
                            "run_id": "run-1",
                            "lead_id": "lead-1",
                            "idempotency_key": "run-1:lead-1",
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
                "task_timings": [
                    {"worker_profile": "p1-source-collector", "duration_ms": 10},
                    {"worker_profile": "p1-source-merger", "duration_ms": 5},
                    {"worker_profile": "p1-lead-normalizer", "duration_ms": 7},
                    {"worker_profile": "p1-triage-scorer", "duration_ms": 11},
                    {"worker_profile": "p1-dossier-writer", "duration_ms": 13},
                    {"worker_profile": "p1-live-intel-gatherer", "duration_ms": 17},
                    {"worker_profile": "p1-gateway-evaluator", "duration_ms": 19},
                    {"worker_profile": "p1-forge-queue-builder", "duration_ms": 23},
                    {"worker_profile": "p1-outreach-draft-writer", "duration_ms": 29},
                    {"worker_profile": "p1-outreach-quality-judge", "duration_ms": 31},
                    {"worker_profile": "p1-data-lake-syncer", "duration_ms": 37},
                    {"worker_profile": "p1-google-sheets-syncer", "duration_ms": 41},
                    {"worker_profile": "p1-outreach-master-syncer", "duration_ms": 43},
                ],
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
        "sheet_duplicate_skipped": 0,
        "data_lake_written": 1,
        "data_lake_duplicate_skipped": 0,
        "outreach_master_written": 1,
        "outreach_master_duplicate_skipped": 0,
        "rejection_buckets": {"unknown": 1},
        "source_counts": {},
        "provider_cache_hits": 0,
        "duration_by_worker_ms": {
            "p1-source-collector": 10,
            "p1-source-merger": 5,
            "p1-lead-normalizer": 7,
            "p1-triage-scorer": 11,
            "p1-dossier-writer": 13,
            "p1-live-intel-gatherer": 17,
            "p1-gateway-evaluator": 19,
            "p1-forge-queue-builder": 23,
            "p1-outreach-draft-writer": 29,
            "p1-outreach-quality-judge": 31,
            "p1-data-lake-syncer": 37,
            "p1-google-sheets-syncer": 41,
            "p1-outreach-master-syncer": 43,
        },
        "total_duration_ms": 286,
        "source_duration_ms": 22,
        "triage_duration_ms": 24,
        "gateway_duration_ms": 59,
        "drafting_duration_ms": 60,
        "sync_duration_ms": 121,
    }


def test_p1_outreach_quality_rejects_missing_cta_and_placeholder_signoff() -> None:
    result = judge_outreach_quality(
        {
            "inputs": {
                "outreach_drafts": [
                    {
                        "run_id": "run-2",
                        "lead_id": "lead-2",
                        "idempotency_key": "run-2:lead-2",
                        "name": "Arianna Simpson",
                        "text": "ABRT is building Limpid around operator product DNA. Best,",
                        "evidence_urls": ["https://www.linkedin.com/in/ariannasimpson"],
                        "claims": [{"text": "Arianna is an investor.", "source_url": "https://www.linkedin.com/in/ariannasimpson"}],
                        "status": "draft",
                        "publish": False,
                    }
                ]
            }
        },
        {},
    )

    assert result["passed"] is False
    assert "has_clear_cta" in result["reasons"]
    assert "no_placeholder_signoff" in result["reasons"]
