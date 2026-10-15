import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Boolean, Integer, Float, DateTime, ForeignKey, Enum as SQLEnum, JSON, Index
)
from sqlalchemy.orm import relationship
from app.db.session import Base
import enum

class RiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class ProcessingStatus(str, enum.Enum):
    PENDING = "PENDING"
    COLLECTING = "COLLECTING"
    VERIFYING = "VERIFYING"
    BLOCKED = "BLOCKED"
    QUARANTINED = "QUARANTINED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    PRODUCING = "PRODUCING"
    RENDERING = "RENDERING"
    READY_TO_PUBLISH = "READY_TO_PUBLISH"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class LicenseType(str, enum.Enum):
    PUBLIC_DOMAIN = "PUBLIC_DOMAIN"
    CREATIVE_COMMONS = "CREATIVE_COMMONS"
    EDITORIAL_PURCHASED = "EDITORIAL_PURCHASED"
    OWN_PRODUCTION = "OWN_PRODUCTION"
    AI_GENERATED = "AI_GENERATED"
    RESTRICTED = "RESTRICTED"

# 1. Usuários e Autenticação
class User(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    role = Column(String(50), default="editor") # admin, editor, viewer
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# 2. Categorias Editoriais
class Category(Base):
    __tablename__ = "source_categories"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    slug = Column(String(100), unique=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    keywords = Column(JSON, default=list) # lista de termos
    priority = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    auto_publish_low_risk = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# 3. Fontes de Notícias
class Source(Base):
    __tablename__ = "sources"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    category_id = Column(String(36), ForeignKey("source_categories.id"))
    source_type = Column(String(50)) # RSS, API, GOV_PORTAL, PRESS_RELEASE
    feed_url = Column(String(1000), nullable=False)
    website_url = Column(String(1000))
    publisher = Column(String(100), nullable=True) # Nome do veículo de imprensa (ex: EBC, Globo, Folha, Google)
    trust_weight = Column(Float, default=1.0) # 0.1 a 1.0 (peso de autoridade)
    check_interval_minutes = Column(Integer, default=15)
    is_active = Column(Boolean, default=True)
    last_checked_at = Column(DateTime)
    error_count = Column(Integer, default=0)  # falhas consecutivas (zera em caso de sucesso)
    # Saúde e cache HTTP da fonte (coleta incremental)
    etag = Column(String(255), nullable=True)           # para If-None-Match
    last_modified = Column(String(100), nullable=True)  # para If-Modified-Since
    last_status_code = Column(Integer, nullable=True)
    last_error = Column(Text, nullable=True)
    last_success_at = Column(DateTime, nullable=True)
    last_items_found = Column(Integer, default=0)
    next_check_at = Column(DateTime, nullable=True, index=True)  # agendamento com backoff
    created_at = Column(DateTime, default=datetime.utcnow)

# 4. Itens Coletados
class NewsItem(Base):
    __tablename__ = "news_items"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id = Column(String(36), ForeignKey("sources.id"), index=True)
    category_id = Column(String(36), ForeignKey("source_categories.id"), index=True)
    title = Column(String(500), nullable=False)
    url = Column(String(1000), unique=True, nullable=False, index=True)
    content_hash = Column(String(64), index=True)
    summary = Column(Text)
    full_text = Column(Text)
    published_date = Column(DateTime)
    collected_at = Column(DateTime, default=datetime.utcnow)
    status = Column(SQLEnum(ProcessingStatus), default=ProcessingStatus.PENDING)
    risk_level = Column(SQLEnum(RiskLevel), default=RiskLevel.MEDIUM)
    cluster_id = Column(String(36), index=True, nullable=True) # para agrupamento de matérias iguais

# 5. Afirmações / Fatos extraídos
class NewsClaim(Base):
    __tablename__ = "news_claims"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    news_item_id = Column(String(36), ForeignKey("news_items.id"), index=True)
    claim_text = Column(Text, nullable=False)
    claim_type = Column(String(50)) # FACT, ACCUSATION, OPINION, ESTIMATE
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# 6. Resultados de Verificação Editorial
class VerificationResult(Base):
    __tablename__ = "verification_results"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    news_item_id = Column(String(36), ForeignKey("news_items.id"), unique=True)
    confidence_score = Column(Float, default=0.0) # 0 a 100
    corroborating_sources_count = Column(Integer, default=0)
    verdict = Column(String(100)) # CORROBORATED, PARTIALLY_CONFIRMED, CONTRADICTORY, UNVERIFIED
    justification = Column(Text)
    has_prompt_injection = Column(Boolean, default=False)
    flagged_sensitive_topics = Column(JSON, default=list) # [crime, religion, politics]
    verified_at = Column(DateTime, default=datetime.utcnow)

# 7. Projetos de Conteúdo e Roteiros
class ContentProject(Base):
    __tablename__ = "content_projects"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    news_item_id = Column(String(36), ForeignKey("news_items.id"), index=True)
    category_id = Column(String(36), ForeignKey("source_categories.id"))
    headline = Column(String(300), nullable=False)
    editorial_summary = Column(Text)
    full_article = Column(Text)
    script_youtube_long = Column(Text)
    script_short_vertical = Column(Text) # Shorts / Reels / TikTok
    social_captions = Column(JSON, default=dict) # {youtube: "...", instagram: "...", twitter: "..."}
    status = Column(SQLEnum(ProcessingStatus), default=ProcessingStatus.PRODUCING)
    requires_human_approval = Column(Boolean, default=True)
    approved_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# 8. Mídias e Licenças de Direitos Autorais
class MediaAsset(Base):
    __tablename__ = "media_assets"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    file_path = Column(String(1000), nullable=False)
    media_type = Column(String(50)) # IMAGE, AUDIO, VIDEO, SUBTITLE
    license_type = Column(SQLEnum(LicenseType), default=LicenseType.OWN_PRODUCTION)
    source_attribution = Column(String(500))
    is_ai_generated = Column(Boolean, default=False)
    ai_disclosure_text = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

# 9. Contas de Publicação (YouTube, Insta, TikTok, X, etc.)
class PublishingAccount(Base):
    __tablename__ = "publishing_accounts"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    platform = Column(String(50), nullable=False) # YOUTUBE, INSTAGRAM, TIKTOK, TWITTER, TELEGRAM, PORTAL
    account_name = Column(String(255), nullable=False)
    channel_id = Column(String(255))
    encrypted_credentials = Column(Text, nullable=False) # Token/OAuth criptografado
    is_active = Column(Boolean, default=True)
    is_paused = Column(Boolean, default=False)
    daily_post_limit = Column(Integer, default=10)
    posts_today = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

# 10. Fila e Tarefas de Publicação (Jobs)
class PublishingJob(Base):
    __tablename__ = "publishing_jobs"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    content_project_id = Column(String(36), ForeignKey("content_projects.id"), index=True)
    account_id = Column(String(36), ForeignKey("publishing_accounts.id"), index=True)
    status = Column(SQLEnum(ProcessingStatus), default=ProcessingStatus.READY_TO_PUBLISH)
    platform_post_id = Column(String(255))
    post_url = Column(String(1000))
    idempotency_key = Column(String(128), unique=True, index=True)
    scheduled_for = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

# 11. Métricas de Desempenho
class PostMetric(Base):
    __tablename__ = "post_metrics"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), ForeignKey("publishing_jobs.id"), index=True)
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    collected_at = Column(DateTime, default=datetime.utcnow)

# 12. Auditoria e Rastreabilidade Completa
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    action = Column(String(100), nullable=False)
    entity_type = Column(String(100))
    entity_id = Column(String(36))
    user_id = Column(String(36), nullable=True)
    details = Column(JSON, default=dict)
    ip_address = Column(String(45))
    created_at = Column(DateTime, default=datetime.utcnow)

# 13. Custos de IA e Renderização
class CostRecord(Base):
    __tablename__ = "cost_records"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    service_name = Column(String(100)) # OPENAI, GEMINI, ELEVENLABS, SERVER
    operation = Column(String(100)) # SUMMARY, VERIFY, SCRIPT, TTS, RENDER
    tokens_used = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
