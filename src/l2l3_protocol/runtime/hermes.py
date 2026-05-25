import asyncio
from typing import Any

from l2l3_protocol.config import Settings
from l2l3_protocol.logging import get_logger

logger = get_logger("protocol.workers")


class HermesRuntime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def available(self) -> bool:
        return self.settings.hermes_enabled and bool(self.settings.deepseek_api_key)

    async def run(self, prompt: str, system_message: str, task_id: str, enabled_toolsets: list[str] | None = None) -> str:
        if not self.available():
            raise RuntimeError("Hermes runtime is disabled or DEEPSEEK_API_KEY is missing")
        try:
            from run_agent import AIAgent

            agent = AIAgent(
                model=self.settings.hermes_model,
                api_key=self.settings.deepseek_api_key,
                base_url=self.settings.deepseek_base_url,
                quiet_mode=True,
                skip_memory=True,
                skip_context_files=True,
                max_iterations=self.settings.hermes_max_iterations,
                enabled_toolsets=enabled_toolsets,
            )
            result: dict[str, Any] = await asyncio.to_thread(
                agent.run_conversation,
                user_message=prompt,
                system_message=system_message,
                task_id=task_id,
            )
            return str(result.get("final_response", ""))
        except Exception as exc:
            logger.warning("hermes_worker_failed", task_id=task_id, error_type=type(exc).__name__)
            raise
