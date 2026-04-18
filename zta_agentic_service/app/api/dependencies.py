from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from app.agents.executor import AgentExecutor
from app.agents.registry_loader import AgentRegistryLoader
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.integrations.ticketing import get_ticketing_client
from app.services.context_manager import ContextManager
from app.services.intent_resolver import IntentResolver
from app.services.orchestrator import ExecutionOrchestrator
from app.services.cache import RegistryCache
from app.services.registry_service import RegistryService
from app.services.state_machine import ExecutionStateMachine
from app.services.step_executor import StepExecutor


@lru_cache(maxsize=1)
def get_context_manager() -> ContextManager:
    return ContextManager()


@lru_cache(maxsize=1)
def get_step_executor() -> StepExecutor:
    return StepExecutor(approved_endpoints=[])


@lru_cache(maxsize=1)
def get_state_machine() -> ExecutionStateMachine:
    return ExecutionStateMachine()


@lru_cache(maxsize=1)
def get_registry_cache() -> RegistryCache:
    return RegistryCache()


def get_registry_service(
    db: Session = Depends(get_db_session),
    cache: RegistryCache = Depends(get_registry_cache),
) -> RegistryService:
    return RegistryService(db=db, cache=cache)


def get_agent_registry_loader(
    db: Session = Depends(get_db_session),
    cache: RegistryCache = Depends(get_registry_cache),
) -> AgentRegistryLoader:
    return AgentRegistryLoader(
        db_session=db,
        cache_client=cache.redis,
        handler_dependencies={},
    )


def get_agent_executor(
    db: Session = Depends(get_db_session),
    loader: AgentRegistryLoader = Depends(get_agent_registry_loader),
) -> AgentExecutor:
    return AgentExecutor(db_session=db, loader=loader)


def get_intent_resolver(settings: Settings = Depends(get_settings)) -> IntentResolver:
    return IntentResolver(settings=settings)


def get_orchestrator(
    settings: Settings = Depends(get_settings),
    state_machine: ExecutionStateMachine = Depends(get_state_machine),
    step_executor: StepExecutor = Depends(get_step_executor),
    context_manager: ContextManager = Depends(get_context_manager),
    cache: RegistryCache = Depends(get_registry_cache),
) -> ExecutionOrchestrator:
    return ExecutionOrchestrator(
        state_machine=state_machine,
        step_executor=step_executor,
        context_manager=context_manager,
        max_chain_depth=settings.max_chain_depth,
        redis_client=cache.redis,
        ticketing_client=get_ticketing_client(settings),
    )
