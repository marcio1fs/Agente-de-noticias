import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List, Optional, Literal

class Settings(BaseSettings):
    PROJECT_NAME: str = "Agente Autônomo de Notícias"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Segurança e Criptografia
    SECRET_KEY: str = "dev-secret-key-change-in-production-super-secret-key-32bytes"
    ENCRYPTION_KEY: str = "dev-fernet-key-32bytes-base64-needs-to-be-generated-or-set=="
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    
    # Banco de Dados
    DATABASE_URL: str = "sqlite+aiosqlite:///./news_agent.db"
    
    # Redis para cache e filas
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Modo de Operação do Agente: 'SIMULATION', 'ASSISTED', 'AUTONOMOUS'
    AGENT_MODE: Literal["SIMULATION", "ASSISTED", "AUTONOMOUS"] = "SIMULATION"
    
    # Botão de Emergência Global (se True, nenhuma publicação é despachada)
    EMERGENCY_STOP: bool = False
    
    # Pipeline Autônomo de Ponta a Ponta
    AUTONOMOUS_PIPELINE_ENABLED: bool = True       # Dispara verificação e produção assim que novas notícias chegam
    AUTONOMOUS_AUTO_PUBLISH_LOW_RISK: bool = True  # Publica automaticamente se risco for LOW e confiança >= 80%
    BREAKING_NEWS_INTERVAL_SECONDS: int = 120     # Intervalo ágil para checagem de furos de reportagem
    
    # Coleta de notícias (Discovery)
    DISCOVERY_SCHEDULER_ENABLED: bool = True      # agendador automático de coleta
    DISCOVERY_TICK_SECONDS: int = 60              # frequência com que o agendador procura fontes vencidas
    DISCOVERY_CONCURRENCY: int = 8                # requisições simultâneas a feeds
    DISCOVERY_TIMEOUT_SECONDS: float = 15.0       # timeout por requisição HTTP
    DISCOVERY_MAX_ITEMS_PER_FEED: int = 150       # teto de entradas lidas por feed
    DISCOVERY_DEFAULT_INTERVAL_MINUTES: int = 15  # usado quando a fonte não define intervalo
    DISCOVERY_MAX_BACKOFF_FACTOR: int = 32        # multiplicador máximo do intervalo após falhas seguidas

    # Diretórios de armazenamento
    STORAGE_DIR: str = "./storage"
    MEDIA_DIR: str = "./storage/media"
    VIDEO_DIR: str = "./storage/videos"
    AUDIO_DIR: str = "./storage/audio"
    
    # Provedores de IA (configuráveis via variáveis de ambiente)
    OPENAI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    
    # YouTube OAuth 2.0 Credentials
    YOUTUBE_CLIENT_ID: Optional[str] = None
    YOUTUBE_CLIENT_SECRET: Optional[str] = None

    # Bancos de Vídeos Livres de Direitos Autorais (B-Roll CC0 / Gratuitos)
    PEXELS_API_KEY: Optional[str] = None
    PIXABAY_API_KEY: Optional[str] = None

    # OriginalContentFactory: opt-in, independent of the news scheduler.
    FACTORY_ENABLED: bool = False
    FACTORY_ADMIN_KEY: Optional[str] = None
    FACTORY_SCHEDULER_ENABLED: bool = False
    FACTORY_YOUTUBE_ACCOUNT_ID: Optional[str] = None
    FACTORY_YOUTUBE_PRIVACY: Literal["private", "unlisted", "public"] = "private"
    FACTORY_AUTO_PUBLISH: bool = False  # Only after recorded human approval.
    FACTORY_INTERVAL_SECONDS: int = Field(default=60, ge=10, le=86400)
    FACTORY_DAILY_CALL_LIMIT: int = Field(default=0, ge=0, le=1000)
    FACTORY_DAILY_BUDGET_MICROUSD: int = Field(default=0, ge=0)
    FACTORY_CALL_RESERVATION_MICROUSD: int = Field(default=100000, ge=1)
    FACTORY_MAX_ATTEMPTS: int = Field(default=3, ge=1, le=5)
    FACTORY_GEMINI_MODEL: str = "gemini-2.5-flash"
    FACTORY_SOURCE_HOSTS: List[str] = ["www.nasa.gov", "science.nasa.gov", "www.esa.int", "arxiv.org"]
    FACTORY_SCORE_WEIGHTS: dict[str, float] = {"curiosity": 0.3, "evidence": 0.4, "novelty": 0.2, "evergreen": 0.1}

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

settings = Settings()

# Assegurar que os diretórios essenciais existam
for path in [settings.STORAGE_DIR, settings.MEDIA_DIR, settings.VIDEO_DIR, settings.AUDIO_DIR]:
    os.makedirs(path, exist_ok=True)
