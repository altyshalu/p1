from uuid import uuid4

import pytest
import respx
from httpx import Response

from l2l3_protocol.config import Settings
from l2l3_protocol.core.schemas import MemoryLayer, MemoryWrite
from l2l3_protocol.memory.adapters import AgentMemoryClient, Mem0SemanticMemory


def memory_write(layer: MemoryLayer) -> MemoryWrite:
    return MemoryWrite(
        layer=layer,
        run_id=uuid4(),
        content="memory write must be durable",
        metadata={"type": "fact", "concepts": ["l2-l3"]},
    )


@pytest.mark.asyncio
@respx.mock
async def test_agentmemory_write_failure_is_not_silently_swallowed() -> None:
    respx.post("http://agentmemory.test/agentmemory/remember").mock(return_value=Response(500))
    client = AgentMemoryClient(Settings(_env_file=None, agentmemory_enabled=True, agentmemory_base_url="http://agentmemory.test"))

    with pytest.raises(Exception):
        await client.remember(memory_write(MemoryLayer.EPISODIC))


@pytest.mark.asyncio
async def test_mem0_enabled_requires_gemini_key() -> None:
    semantic = Mem0SemanticMemory(Settings(_env_file=None, mem0_enabled=True, gemini_api_key=None))

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        await semantic.add(memory_write(MemoryLayer.SEMANTIC))
