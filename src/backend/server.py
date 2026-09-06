from __future__ import annotations

import os
from http.server import ThreadingHTTPServer

from auth.service import AuthService, UserRepository
from repositories.memory import InMemoryUserRepository
from repositories.postgres import PostgresUserRepository
from repositories.pattern_queries import InMemoryPatternQueryRepository, PostgresPatternQueryRepository
from repositories.market_data import PostgresMarketDataRepository
from repositories.patterns import InMemoryPatternRepository, PostgresPatternRepository
from repositories.research import InMemoryResearchRepository, PostgresResearchRepository
from repositories.admin_pipeline import PostgresAdminPipelineRepository
from repositories.operations import PostgresOperationsRepository
from data_pipeline.history_backfill import HistoryBackfillService
from data_pipeline.nse_api import NseApiClient
from operations.admin_pipeline import AdminPipelineService, DisabledAdminPipelineService
from operations.monitoring import StructuredEventLogger
from operations.recovery import RecoveryService
from pattern_engine.configuration import load_pattern_engine_configuration
from pattern_engine.query_service import PatternQueryService
from pattern_engine.research import BacktestService, PatternReplayEvaluator
from pattern_engine.runner import PatternEngineRunner
from server_http.api import ApiHandler

HOST = "127.0.0.1"
PORT = 9004
DEVELOPMENT_JWT_SECRET = "change-this-tradelens-development-jwt-secret"


def load_local_environment() -> None:
    """Load backend/.env for local development.

    The checked-out local configuration is deliberately authoritative so another
    project-level DATABASE_URL in a developer shell cannot point TradeLens at a
    different database.
    """
    environment_file = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(environment_file):
        return
    with open(environment_file, encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", maxsplit=1)
            os.environ[key.strip()] = value.strip()


load_local_environment()


def build_repository() -> UserRepository:
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        return PostgresUserRepository(dsn)
    return InMemoryUserRepository()


def create_server(host: str = HOST, port: int = PORT, repository: UserRepository | None = None, pattern_repository=None, research_repository=None, replay_evaluator=None, admin_pipeline_service=None) -> ThreadingHTTPServer:
    use_configured_database = repository is None
    dsn = os.getenv("DATABASE_URL")
    repository = repository or build_repository()
    service = AuthService(repository, os.getenv("JWT_SECRET", DEVELOPMENT_JWT_SECRET))
    if pattern_repository is None:
        pattern_repository = PostgresPatternQueryRepository(dsn) if dsn and use_configured_database else InMemoryPatternQueryRepository()
    pattern_service = PatternQueryService(pattern_repository)
    if research_repository is None:
        research_repository = PostgresResearchRepository(dsn, apply_migrations=False) if dsn and use_configured_database else InMemoryResearchRepository()
    configuration_version = None
    configuration = market_repository = runner = None
    if dsn and use_configured_database:
        configuration = load_pattern_engine_configuration()
        configuration_version = configuration.version
        market_repository = PostgresMarketDataRepository(dsn, apply_migrations=False)
        live_pattern_repository = PostgresPatternRepository(dsn, apply_migrations=False)
        runner = PatternEngineRunner(market_repository, live_pattern_repository, market_repository, configuration)
        if replay_evaluator is None:
            replay_evaluator = PatternReplayEvaluator(runner)
    research_service = BacktestService(
        research_repository, replay_evaluator,
        configuration_version=configuration_version,
    )
    if admin_pipeline_service is None and dsn and use_configured_database:
        operations_repository = PostgresOperationsRepository(dsn, apply_migrations=False)
        event_logger = StructuredEventLogger(operations_repository)
        nse_client = NseApiClient()
        admin_pipeline_service = AdminPipelineService(
            PostgresAdminPipelineRepository(dsn, apply_migrations=False),
            HistoryBackfillService(market_repository, nse_client, event_logger=event_logger),
            RecoveryService(market_repository, runner, configuration, logger=event_logger),
            configuration, logger=event_logger,
            max_workers=max(1, min(8, int(os.getenv("ADMIN_PIPELINE_WORKERS", "3")))),
        )
    admin_pipeline_service = admin_pipeline_service or DisabledAdminPipelineService()

    class ConfiguredApiHandler(ApiHandler):
        pass

    ConfiguredApiHandler.service = service
    ConfiguredApiHandler.pattern_service = pattern_service
    ConfiguredApiHandler.research_service = research_service
    ConfiguredApiHandler.admin_pipeline_service = admin_pipeline_service
    return ThreadingHTTPServer((host, port), ConfiguredApiHandler)
