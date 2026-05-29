import asyncio
from typing import Any

from l2l3_protocol.config import Settings
from l2l3_protocol.logging import get_logger

logger = get_logger('protocol.workers')


class HermesRuntime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def available(self) -> bool:
        return self.settings.hermes_enabled and bool(self.settings.deepseek_api_key or self.settings.gemini_api_key)

    def provider(self) -> str | None:
        if not self.settings.hermes_enabled:
            return None
        if self.settings.deepseek_api_key:
            return 'deepseek'
        if self.settings.gemini_api_key:
            return 'gemini'
        return None

    def model_name(self) -> str | None:
        provider = self.provider()
        if provider == 'deepseek':
            return self.settings.hermes_model
        if provider == 'gemini':
            return self.settings.hermes_gemini_model
        return None

    async def run(self, prompt: str, system_message: str, task_id: str, enabled_toolsets: list[str] | None = None) -> str:
        provider = self.provider()
        if provider is None:
            raise RuntimeError('Hermes runtime is disabled or no supported API key is configured')
        if provider == 'deepseek':
            return await self._run_deepseek(prompt, system_message, task_id, enabled_toolsets)
        if provider == 'gemini':
            return await self._run_gemini(prompt, system_message, task_id)
        raise RuntimeError(f'unsupported Hermes provider: {provider}')

    async def _run_deepseek(
        self,
        prompt: str,
        system_message: str,
        task_id: str,
        enabled_toolsets: list[str] | None,
    ) -> str:
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
            return str(result.get('final_response', ''))
        except Exception as exc:
            logger.warning('hermes_worker_failed', task_id=task_id, provider='deepseek', error_type=type(exc).__name__)
            raise

    async def _run_gemini(self, prompt: str, system_message: str, task_id: str) -> str:
        try:
            from google import genai

            def _call() -> str:
                client = genai.Client(api_key=self.settings.gemini_api_key)
                response = client.models.generate_content(
                    model=self.settings.hermes_gemini_model,
                    contents=f'SYSTEM:\n{system_message}\n\nUSER:\n{prompt}',
                )
                text = getattr(response, 'text', None)
                if isinstance(text, str) and text.strip():
                    return text
                candidates = getattr(response, 'candidates', None) or []
                for candidate in candidates:
                    content = getattr(candidate, 'content', None)
                    parts = getattr(content, 'parts', None) or []
                    joined = ''.join(str(getattr(part, 'text', '')) for part in parts)
                    if joined.strip():
                        return joined
                raise RuntimeError(f'Gemini returned no text for task_id={task_id}')

            return await asyncio.to_thread(_call)
        except Exception as exc:
            logger.warning('hermes_worker_failed', task_id=task_id, provider='gemini', error_type=type(exc).__name__)
            raise
