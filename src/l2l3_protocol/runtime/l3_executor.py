import asyncio
import json
import os
import re
import sys
from typing import Any

from l2l3_protocol.core.schemas import TaskContract
from l2l3_protocol.runtime.hermes import HermesRuntime


class L3WorkerExecutionError(RuntimeError):
    pass


class L3SandboxExecutor:
    def __init__(self, hermes: HermesRuntime | None = None) -> None:
        self.hermes = hermes

    async def run(self, contract: TaskContract, context: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        worker_type = profile.get("worker_type") or contract.worker_type
        if worker_type == "hermes_agent":
            return await self._run_hermes_agent(contract, context, profile)
        if worker_type in {"sandboxed_subprocess", "evaluator", "human_gate"}:
            return await self._run_subprocess(contract, context, profile)
        raise L3WorkerExecutionError(f"unsupported worker_type: {worker_type}")

    async def _run_subprocess(self, contract: TaskContract, context: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        module = profile.get("entrypoint")
        if not module:
            raise L3WorkerExecutionError(f"worker profile missing entrypoint: {contract.worker_profile}")
        timeout = float(contract.budget.get("max_seconds", 30))
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
            "L2L3_SANDBOX": "1",
        }
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
            "contract": contract.model_dump(mode="json"),
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
            raise L3WorkerExecutionError(f"L3 worker timed out after {timeout}s: {contract.worker_profile}") from exc
        if process.returncode != 0:
            raise L3WorkerExecutionError(stderr.decode("utf-8", errors="replace") or f"L3 worker exited {process.returncode}")
        try:
            payload = json.loads(stdout.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise L3WorkerExecutionError(f"L3 worker returned invalid JSON: {contract.worker_profile}") from exc
        self._validate_required_keys(contract, payload)
        payload["_worker_execution"] = {
            "mode": "sandboxed_subprocess",
            "worker_profile": contract.worker_profile,
            "task_type": contract.task_type,
        }
        return payload

    async def _run_hermes_agent(self, contract: TaskContract, context: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        if self.hermes is None or not self.hermes.available():
            raise L3WorkerExecutionError(f"Hermes L3 worker is required but unavailable: {contract.worker_profile}")
        prompt = json.dumps(
            {
                "instruction": profile.get("agent_prompt") or "Complete this L3 task and return strict JSON.",
                "contract": contract.model_dump(mode="json"),
                "context": context,
                "output_schema": contract.output_schema,
                "hard_constraints": [
                    "Return one JSON object and nothing else.",
                    "Do not perform side effects outside the contract side_effect_policy.",
                    "If required inputs are missing, return a JSON object with error and missing_inputs.",
                ],
            },
            ensure_ascii=True,
        )
        raw = await self.hermes.run(
            prompt=prompt,
            system_message="You are a bounded L3 worker. Execute only the given contract and return strict JSON.",
            task_id=f"l3-worker:{contract.worker_profile}:{contract.id}",
            enabled_toolsets=contract.allowed_tools,
        )
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                raise L3WorkerExecutionError(f"Hermes L3 worker returned invalid JSON: {contract.worker_profile}")
            payload = json.loads(match.group(0))
        self._validate_required_keys(contract, payload)
        payload["_worker_execution"] = {
            "mode": "hermes_agent",
            "worker_profile": contract.worker_profile,
            "task_type": contract.task_type,
        }
        return payload

    @staticmethod
    def _validate_required_keys(contract: TaskContract, payload: dict[str, Any]) -> None:
        required = contract.output_schema.get("required", [])
        missing = [key for key in required if key not in payload]
        if missing:
            raise L3WorkerExecutionError(f"L3 worker output missing required keys: {missing}")
