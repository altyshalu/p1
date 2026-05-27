from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = Path(__file__).with_name("real-before-after-proof.py")
SPEC = importlib.util.spec_from_file_location("real_before_after_proof", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"could not load proof helper from {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
request_json = MODULE.request_json
run_before_after_proof = MODULE.run_before_after_proof


def list_cases(api_url: str) -> None:
    cases = request_json(f"{api_url.rstrip('/')}/regression-cases")
    print(json.dumps(cases, indent=2, ensure_ascii=False))


def rerun_cases(api_url: str, case_id: str | None, limit: int, timeout_seconds: int) -> None:
    payload = request_json(f"{api_url.rstrip('/')}/regression-cases")
    if not isinstance(payload, list):
        raise RuntimeError(f"regression case list returned invalid payload: {payload}")
    cases = [item for item in payload if isinstance(item, dict)]
    if case_id is not None:
        cases = [item for item in cases if item.get("id") == case_id]
    if limit > 0:
        cases = cases[:limit]
    results = []
    for case in cases:
        results.append(
            run_before_after_proof(
                api_url=api_url,
                baseline_run_id=str(case["baseline_run_id"]),
                proposal_id=str(case["proposal_id"]),
                timeout_seconds=timeout_seconds,
            )
        )
    print(json.dumps(results, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="List or rerun real regression cases against the live API.")
    parser.add_argument("--api-url", default="http://localhost:8080")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list")
    rerun = subparsers.add_parser("rerun")
    rerun.add_argument("--case-id")
    rerun.add_argument("--limit", type=int, default=10)
    rerun.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()
    if args.command == "list":
        list_cases(args.api_url)
    else:
        rerun_cases(args.api_url, args.case_id, args.limit, args.timeout_seconds)


if __name__ == "__main__":
    main()
