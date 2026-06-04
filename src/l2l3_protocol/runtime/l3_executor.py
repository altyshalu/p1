import asyncio
import json
import os
import re
import sys
from typing import Any

from l2l3_protocol.core.schemas import WorkOrder
from l2l3_protocol.runtime.hermes import HermesRuntime


class L3WorkerExecutionError(RuntimeError):
    pass


class L3SandboxExecutor:
    def __init__(self, hermes: HermesRuntime | None = None) -> None:
        self.hermes = hermes

    async def run(self, work_order: WorkOrder, context: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        worker_type = profile.get("worker_type") or work_order.worker_type
        if worker_type == "hermes_agent":
            return await self._run_hermes_agent(work_order, context, profile)
        if worker_type in {"sandboxed_subprocess", "evaluator", "human_gate", "adapter"}:
            return await self._run_subprocess(work_order, context, profile)
        raise L3WorkerExecutionError(f"unsupported worker_type: {worker_type}")

    async def _run_subprocess(self, work_order: WorkOrder, context: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        module = profile.get("entrypoint")
        if not module:
            raise L3WorkerExecutionError(f"worker profile missing entrypoint: {work_order.worker_profile}")
        timeout = float(work_order.budget.get("max_seconds", 30))
        env = {
            "HOME": os.environ.get("HOME", ""),
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
            "L2L3_SANDBOX": "1",
        }
        for key in (
            "CODEX_HOME",
            "OPENAI_API_KEY",
            "L2L3_ENABLE_CODEX_IMPLEMENTER",
            "GEMINI_API_KEY",
            "DEEPSEEK_API_KEY",
            "DEEPSEEK_BASE_URL",
            "EXA_API_KEY",
            "APIFY_API_TOKEN",
            "GOOGLE_SA_PATH",
            "P1_GOOGLE_SHEET_ID",
            "P1_DOSSIER_SOURCE_PATH",
            "P1_DOSSIER_OUTPUT_PATH",
            "P1_OUTREACH_MASTER_PATH",
        ):
            if os.environ.get(key):
                env[key] = os.environ[key]
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            module,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        request = {
            "work_order": work_order.model_dump(mode="json"),
            "context": context,
        }
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(json.dumps(request, ensure_ascii=True).encode("utf-8")),
                timeout=timeout,
            )
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise L3WorkerExecutionError(f"L3 worker timed out after {timeout}s: {work_order.worker_profile}") from exc
        if process.returncode != 0:
            raise L3WorkerExecutionError(stderr.decode("utf-8", errors="replace") or f"L3 worker exited {process.returncode}")
        try:
            payload = json.loads(stdout.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise L3WorkerExecutionError(f"L3 worker returned invalid JSON: {work_order.worker_profile}") from exc
        self._validate_required_keys(work_order, payload)
        payload["_worker_execution"] = {
            "mode": "sandboxed_subprocess",
            "worker_profile": work_order.worker_profile,
            "task_type": work_order.task_type,
        }
        return payload

    async def _run_hermes_agent(self, work_order: WorkOrder, context: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        if self.hermes is None or not self.hermes.available():
            raise L3WorkerExecutionError(f"Hermes L3 worker is required but unavailable: {work_order.worker_profile}")
        prompt = json.dumps(
            {
                "instruction": profile.get("agent_prompt") or "Complete this L3 task and return strict JSON.",
                "work_order": work_order.model_dump(mode="json"),
                "context": context,
                "output_schema": work_order.output_schema,
                "hard_constraints": [
                    "Return one JSON object and nothing else.",
                    "Do not perform External Actions outside the Work Order external_action_policy.",
                    "If required inputs are missing, return a JSON object with error and missing_inputs.",
                ],
            },
            ensure_ascii=True,
        )
        raw = await self.hermes.run(
            prompt=prompt,
            system_message="You are a bounded L3 worker. Execute only the given Work Order and return strict JSON.",
            task_id=f"l3-worker:{work_order.worker_profile}:{work_order.id}",
            enabled_toolsets=work_order.allowed_tools,
        )
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                raise L3WorkerExecutionError(f"Hermes L3 worker returned invalid JSON: {work_order.worker_profile}")
            payload = json.loads(match.group(0))
        self._validate_required_keys(work_order, payload)
        payload["_worker_execution"] = {
            "mode": "hermes_agent",
            "worker_profile": work_order.worker_profile,
            "task_type": work_order.task_type,
        }
        return payload

    @staticmethod
    def _validate_required_keys(work_order: WorkOrder, payload: dict[str, Any]) -> None:
        required = work_order.output_schema.get("required", [])
        missing = [key for key in required if key not in payload]
        if missing:
            raise L3WorkerExecutionError(f"L3 worker output missing required keys: {missing}")
