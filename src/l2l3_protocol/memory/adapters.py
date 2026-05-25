from pathlib import Path
from typing import Any

import httpx
import yaml

from l2l3_protocol.config import Settings
from l2l3_protocol.core.schemas import MemoryLayer, MemoryWrite
from l2l3_protocol.logging import get_logger

logger = get_logger("protocol.events")


class AgentMemoryClient:
    def __init__(self, settings: Settings) -> None:
        self.enabled = settings.agentmemory_enabled
        self.base_url = settings.agentmemory_base_url.rstrip("/")
        self.secret = settings.agentmemory_secret

    def _headers(self) -> dict[str, str]:
        if not self.secret:
            return {}
        return {"Authorization": f"Bearer {self.secret}"}

    async def remember(self, write: MemoryWrite) -> None:
        if not self.enabled:
            return
        payload = {
            "content": write.content,
            "type": write.metadata.get("type", "observation"),
            "concepts": write.metadata.get("concepts", []),
            "metadata": {**write.metadata, "run_id": str(write.run_id), "task_id": str(write.task_id) if write.task_id else None},
        }
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.post(f"{self.base_url}/agentmemory/remember", json=payload, headers=self._headers())
                response.raise_for_status()
        except Exception as exc:
            logger.error("episodic_memory_write_failed", error_type=type(exc).__name__, run_id=str(write.run_id))
            raise

    async def observe(self, write: MemoryWrite) -> None:
        if not self.enabled:
            return
        payload = {
            "type": write.metadata.get("type", "event"),
            "content": write.content,
            "metadata": {**write.metadata, "run_id": str(write.run_id), "task_id": str(write.task_id) if write.task_id else None},
        }
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.post(f"{self.base_url}/agentmemory/observe", json=payload, headers=self._headers())
                response.raise_for_status()
        except Exception as exc:
            logger.error("episodic_observation_failed", error_type=type(exc).__name__, run_id=str(write.run_id))
            raise


class Mem0SemanticMemory:
    def __init__(self, settings: Settings) -> None:
        self.enabled = settings.mem0_enabled
        self.settings = settings
        self._memory: Any | None = None

    def _get_memory(self) -> Any:
        if self._memory is None:
            from mem0 import Memory

            config = {
                "vector_store": {
                    "provider": self.settings.mem0_vector_provider,
                    "config": {
                        "host": self.settings.mem0_qdrant_host,
                        "port": self.settings.mem0_qdrant_port,
                        "collection_name": self.settings.mem0_collection_name,
                        "embedding_model_dims": self.settings.mem0_embedding_dims,
                    },
                },
                "llm": {
                    "provider": self.settings.mem0_llm_provider,
                    "config": {
                        "model": self.settings.mem0_llm_model,
                        "api_key": self.settings.gemini_api_key,
                        "temperature": 0.1,
                    },
                },
                "embedder": {
                    "provider": self.settings.mem0_embedder_provider,
                    "config": {
                        "model": self.settings.mem0_embedder_model,
                        "api_key": self.settings.gemini_api_key,
                        "embedding_dims": self.settings.mem0_embedding_dims,
                        "output_dimensionality": self.settings.mem0_embedding_dims,
                    },
                },
            }
            self._memory = Memory.from_config(config)
        return self._memory

    async def add(self, write: MemoryWrite) -> None:
        if not self.enabled:
            return
        if not self.settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required when Mem0 semantic memory is enabled")
        try:
            memory = self._get_memory()
            memory.add(
                write.content,
                user_id=write.metadata.get("user_id", "abrt-ai-lab"),
                agent_id=write.metadata.get("agent_id", "l2-orchestrator"),
                run_id=str(write.run_id),
                metadata={**write.metadata, "layer": MemoryLayer.SEMANTIC.value},
            )
        except Exception as exc:
            logger.error("semantic_memory_write_failed", error_type=type(exc).__name__, run_id=str(write.run_id))
            raise


class ProceduralRegistry:
    def __init__(self, root: Path) -> None:
        self.root = root

    def load_playbook(self, key: str) -> dict[str, Any]:
        path = self.root / "playbooks" / key / "playbook.yaml"
        return self._load_yaml(path)

    def load_worker_profile(self, key: str) -> dict[str, Any]:
        return self._load_yaml(self.root / "worker-profiles" / f"{key}.yaml")

    def list_worker_profiles(self) -> dict[str, dict[str, Any]]:
        profiles: dict[str, dict[str, Any]] = {}
        for path in sorted((self.root / "worker-profiles").glob("*.yaml")):
            profile = self._load_yaml(path)
            key = profile.get("key") or path.stem
            profiles[key] = profile
        return profiles

    def load_eval_spec(self, key: str) -> dict[str, Any]:
        return self._load_yaml(self.root / "evals" / f"{key}.yaml")

    def list_tool_specs(self) -> dict[str, dict[str, Any]]:
        tools_dir = self.root / "tools"
        if not tools_dir.exists():
            return {}
        return self._load_keyed_dir(tools_dir)

    def list_failure_patterns(self) -> list[dict[str, Any]]:
        patterns_dir = self.root / "failure-patterns"
        if not patterns_dir.exists():
            return []
        return list(self._load_keyed_dir(patterns_dir).values())

    def _load_keyed_dir(self, path: Path) -> dict[str, dict[str, Any]]:
        items: dict[str, dict[str, Any]] = {}
        for item_path in sorted(path.glob("*.yaml")):
            item = self._load_yaml(item_path)
            key = item.get("key") or item.get("tool_id") or item.get("pattern_id")
            if not key:
                raise ValueError(f"registry item is missing explicit key: {item_path}")
            items[key] = item
        return items

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(path)
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict) or not loaded:
            raise ValueError(f"registry YAML is empty or invalid: {path}")
        return loaded


class MemoryRouter:
    def __init__(self, episodic: AgentMemoryClient, semantic: Mem0SemanticMemory) -> None:
        self.episodic = episodic
        self.semantic = semantic

    async def write(self, write: MemoryWrite) -> None:
        if write.layer == MemoryLayer.EPISODIC:
            await self.episodic.remember(write)
        elif write.layer == MemoryLayer.SEMANTIC:
            await self.semantic.add(write)
