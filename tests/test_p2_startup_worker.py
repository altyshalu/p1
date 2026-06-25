from __future__ import annotations

from l2l3_protocol.workers import p2_startup_worker as p2


def _wo(inputs: dict) -> dict:
    return {"inputs": inputs, "worker_profile": "test", "task_type": "test"}


def test_p2_reader_surfaces_duplicate_headers_and_normalizer_rejects_empty_rows() -> None:
    read = p2.read_sheets(
        _wo(
            {
                "source_tabs": ["From Database"],
                "sheet_rows_by_tab": {
                    "From Database": [
                        ["Company Name", "Company Name", "Website", "Founder LinkedIn"],
                        ["Acme AI", "Duplicate", "acme.ai", "https://linkedin.com/in/founder"],
                        ["", "", "", ""],
                    ]
                },
            }
        ),
        {},
    )

    assert read["drift_report"]
    normalized = p2.normalize_startups(_wo({"raw_startup_rows": read["raw_startup_rows"]}), {})
    assert len(normalized["normalized_startups"]) == 1
    assert normalized["normalized_startups"][0]["Company Name"] == "Acme AI"
    assert normalized["rejected_startups"][0]["reason"] == "empty or placeholder row"


def test_p2_founder_resolver_splits_links_without_adding_rows() -> None:
    resolved = p2.resolve_founder_links(
        _wo(
            {
                "normalized_startups": [
                    {
                        "Company Name": "SplitCo",
                        "Founder LinkedIn URL(s)": "https://linkedin.com/in/a, https://www.linkedin.com/in/b/",
                    }
                ]
            }
        ),
        {},
    )

    rows = resolved["founder_links_resolved"]
    assert len(rows) == 1
    assert rows[0]["Founder LinkedIn URL(s)"] == "https://linkedin.com/in/a"
    assert rows[0]["Founder LinkedIn URL 2"] == "https://www.linkedin.com/in/b"


def test_p2_website_verifier_supports_correction_and_tbc() -> None:
    verified = p2.verify_websites(
        _wo(
            {
                "founder_links_resolved": [
                    {"Company Name": "GoodCo", "Website URL": "https://techcrunch.com/goodco"},
                    {"Company Name": "MissingCo", "Website URL": ""},
                ],
                "website_verification_overrides": {
                    "goodco": {
                        "website_url": "https://goodco.com",
                        "final_url": "https://goodco.com",
                        "status": "Verified",
                        "note": "Official website found during repair.",
                    }
                },
            }
        ),
        {},
    )

    rows = verified["website_verification"]
    assert rows[0]["Website URL"] == "https://goodco.com"
    assert rows[0]["Website Verification Status"] == "Verified"
    assert rows[1]["Website URL"] == "[TBC]"
    assert verified["verification_summary"]["tbc_urls"] == 1
    assert verified["verification_summary"]["corrected_urls"] == 1


def test_p2_judge_only_approves_fit_with_verified_evidence() -> None:
    base = {
        "Company Name": "ApproveCo",
        "Website Verification Status": "Verified",
        "Website Verification Note": "ok",
        "Direction": "AI / Generative Tech",
        "Startup Stage": "Seed",
        "Founder LinkedIn Count": 1,
        "Additional Decision-Useful Info": "B2B AI workflow automation with traction.",
        "ARR": "$500000",
        "Country of Incorporation": "US",
    }
    scored = p2.score_icp(_wo({"sector_classification": [base, {**base, "Company Name": "TbcCo", "Website Verification Status": "Needs manual verification"}]}), {})
    judged = p2.judge_startups(_wo({"synthetic_benchmarks": scored["icp_scores"]}), {})

    assert judged["judge_results"][0]["Judge Tag"] == "Approve"
    assert judged["judge_results"][1]["Judge Tag"] == "Needs manual verification"


def test_p2_suitable_builder_excludes_new_external_and_internal_duplicates() -> None:
    rows = [
        {"Company Name": "KeepCo", "Website URL": "https://keep.co", "Website Final URL": "https://keep.co", "Judge Tag": "Approve"},
        {"Company Name": "ExternalCo", "Website URL": "https://external.co", "Website Final URL": "https://external.co", "Judge Tag": "Approve", "Source Tab": "New / External"},
        {"Company Name": "KeepCo", "Website URL": "https://keep.co", "Website Final URL": "https://keep.co", "Judge Tag": "Approve"},
        {"Company Name": "RejectCo", "Website URL": "https://reject.co", "Judge Tag": "Reject", "Judge Reason": "low score"},
    ]

    built = p2.build_suitable_list(_wo({"judge_results": rows}), {})

    assert [row["Company Name"] for row in built["suitable_startups"]] == ["KeepCo"]
    assert built["duplicates_removed"] == 2
    assert built["rejected_startups"][0]["company"] == "RejectCo"
