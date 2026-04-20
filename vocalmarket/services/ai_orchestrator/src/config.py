from pydantic_settings import BaseSettings


class OrchestratorSettings(BaseSettings):
    # Enthusiast backend
    enthusiast_base_url: str = "http://api:8000"
    enthusiast_api_key: str = ""

    # Hermes (V2)
    hermes_model: str = "NousResearch/Hermes-3-Llama-3.1-8B"
    hermes_base_url: str = ""       # Empty = use local vLLM
    hermes_api_key: str = ""

    # Memory (V2)
    memory_db_url: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/vocalmarket"
    redis_url: str = "redis://redis:6379/1"

    # Telemetry
    otel_endpoint: str = "http://otel-collector:4317"
    service_name: str = "vocalmarket-ai-orchestrator"

    class Config:
        env_prefix = "ORCHESTRATOR_"


settings = OrchestratorSettings()
