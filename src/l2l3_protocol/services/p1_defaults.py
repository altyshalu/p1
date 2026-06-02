from __future__ import annotations

from typing import Any


P1_PLAYBOOK_KEY = "p1-operator-outreach"
DEFAULT_P1_GOAL = "Find 20 fintech / AI / pre-seed operator-angels, mostly US, and prepare send-ready outreach drafts."
DEFAULT_P1_QUERY = (
    "fintech AI pre-seed operator-angels mostly US B2C product-led angel investors "
    "CPO VP Product Head of Product Lead PM product founder active angel portfolio"
)


def default_p1_inputs() -> dict[str, Any]:
    return {
        "mode": "full_pipeline",
        "limit": 20,
        "sources": ["exa", "apify_funding", "apify_crunchbase", "apify_linkedin"],
        "query": DEFAULT_P1_QUERY,
        "channels": ["linkedin"],
        "allow_data_lake_write": True,
        "allow_google_sheet_write": True,
        "allow_outreach_master_write": True,
        "google_sheet_tab": "P1_L2L3_NEW_LEADS",
        "use_provider_cache": True,
        "apify_search_query": "AI fintech pre-seed consumer startup funding angel investors",
        "days_back": 120,
        "linkedin_keywords": (
            "CPO OR VP Product OR Head of Product OR Lead PM OR Product Founder "
            "angel investor fintech AI pre-seed"
        ),
    }
