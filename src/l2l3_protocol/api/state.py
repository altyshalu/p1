from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from l2l3_protocol.config import Settings
from l2l3_protocol.memory.adapters import AgentMemoryClient, Mem0SemanticMemory, MemoryRouter, ProceduralRegistry
from l2l3_protocol.runtime.hermes import HermesRuntime


@dataclass
class AppState:
    settings: Settings | None = None
    engine: AsyncEngine | None = None
    session_factory: async_sessionmaker[AsyncSession] | None = None
    memory_router: MemoryRouter | None = None
    registry: ProceduralRegistry | None = None
    hermes: HermesRuntime | None = None


app_state = AppState()


def build_memory_router(settings: Settings) -> MemoryRouter:
    return MemoryRouter(
        episodic=AgentMemoryClient(settings),
        semantic=Mem0SemanticMemory(settings),
    )
