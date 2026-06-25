from __future__ import annotations


P2_PLAYBOOK_KEY = "p2-startup-sourcing"
P2_DEFAULT_GOAL = "Build a verified, deduped Suitable Startups list from VC Score sheets."
P2_DEFAULT_INPUTS = {
    "mode": "sheet_pipeline",
    "source_tabs": ["From Database", "New / External"],
    "output_tab": "Suitable Startups",
    "limit": 1000,
    "allow_google_sheet_write": False,
}
