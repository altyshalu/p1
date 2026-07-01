#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_inputs(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("inputs-json must contain a JSON object")
    mode = payload.get("mode")
    if mode not in {"source_only", "full_pipeline"}:
        raise SystemExit("inputs-json mode must be source_only or full_pipeline")
    return payload


def run_command(args: list[str]) -> None:
    print("+ " + " ".join(args), flush=True)
    subprocess.run(args, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the standard team P1 angel-search flow.")
    parser.add_argument("action", choices=["preflight", "source-only", "full"])
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--inputs-json", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--approve", action="store_true", help="Approve external writes after the full pipeline reaches waiting_approval.")
    args = parser.parse_args()

    inputs_path = Path(args.inputs_json)
    if not inputs_path.is_absolute():
        inputs_path = ROOT / inputs_path
    inputs = load_inputs(inputs_path)
    mode = str(inputs["mode"])

    if args.action == "source-only" and mode != "source_only":
        raise SystemExit("source-only action requires inputs-json mode=source_only")
    if args.action == "full" and mode != "full_pipeline":
        raise SystemExit("full action requires inputs-json mode=full_pipeline")

    readiness_cmd = [
        sys.executable,
        "scripts/real-p1-readiness.py",
        "--base-url",
        args.base_url,
        "--env-file",
        args.env_file,
        "--mode",
        mode,
        "--inputs-json",
        str(inputs_path),
    ]
    run_command(readiness_cmd)

    if args.action == "preflight":
        return 0

    proof_cmd = [
        sys.executable,
        "scripts/real-p1-full-proof.py",
        "--base-url",
        args.base_url,
        "--env-file",
        args.env_file,
        "--inputs-json",
        str(inputs_path),
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--goal",
        "Run the standard P1 Europe angel investor search.",
    ]
    if args.approve:
        proof_cmd.append("--approve")
    if bool(inputs.get("allow_google_sheet_write")):
        proof_cmd.append("--verify-sheet")
    if bool(inputs.get("allow_outreach_master_write")):
        proof_cmd.append("--verify-outreach-master")
    if bool(inputs.get("allow_data_lake_write")):
        proof_cmd.append("--verify-data-lake")
    if args.action == "full":
        proof_cmd.append("--verify-quality")
    run_command(proof_cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
