from __future__ import annotations

from typing import Any


P1_PLAYBOOK_KEY = "p1-operator-outreach"
DEFAULT_P1_GOAL = "Find 20 fintech / AI / pre-seed operator-angels, mostly US, and prepare send-ready outreach drafts."
DEFAULT_P1_QUERY = (
    '"CPO" OR "VP Product" OR "Head of Product" OR "Lead PM" OR "Fractional CPO" '
    'OR "Independent product advisor" OR "Co-Founder product" '
    '"angel investor" OR "active angel" OR "syndicate lead" '
    '"consumer" OR "PLG" OR "fintech" OR "AI" "United States"'
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
        "use_triage_cache": True,
        "verify_linkedin_live": True,
        "apify_search_query": "AI fintech consumer pre-seed startup funding operator angels product founders",
        "days_back": 120,
        "linkedin_keywords": (
            '("CPO" OR "VP Product" OR "Head of Product" OR "Lead PM" OR "Fractional CPO" '
            'OR "Independent product advisor" OR "Co-Founder product" OR "Product Founder") '
            '("angel investor" OR "active angel" OR "syndicate") '
            '("consumer" OR "PLG" OR "fintech" OR "AI")'
        ),
        "title_keywords": [
            "CPO",
            "VP Product",
            "Head of Product",
            "Lead PM",
            "Fractional CPO",
            "Independent Product Advisor",
            "Co-Founder Product",
            "Product Co-Founder",
            "Product Founder",
        ],
        "seniority_levels": ["Owner/Partner", "CXO", "Vice President"],
    }
