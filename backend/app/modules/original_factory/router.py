from datetime import datetime, timedelta, timezone
import secrets

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.core.security import decrypt_secret
from app.models.entities import (OriginalTopic, FactoryProduction, FactoryUsage, ContentProject,
    PublishingAccount, PublishingJob, ProcessingStatus)
from app.modules.original_factory.schemas import TopicInput, Approval, Category
from app.modules.original_factory.engine import OriginalContentFactory
from app.modules.original_factory.services import FactoryError, get_allowed_hosts, register_source_host
from app.modules.original_factory.media import thumbnail_path
from app.modules.publishing.youtube import YouTubePublisher

router = APIRouter(prefix="/api/v1/factory", tags=["OriginalContentFactory"])
key_header = APIKeyHeader(name="X-Factory-Key", auto_error=False)


def require_factory(key: str | None = Depends(key_header)):
    if not settings.FACTORY_ENABLED:
        raise HTTPException(503, "Fábrica desativada. Configure FACTORY_ENABLED.")
    expected = settings.FACTORY_ADMIN_KEY
    if not expected or len(expected) < 32:
        raise HTTPException(503, "Configure FACTORY_ADMIN_KEY com pelo menos 32 caracteres.")
    if not key or not secrets.compare_digest(key.encode(), expected.encode()):
        raise HTTPException(401, "Chave de administração da fábrica inválida.")


@router.get("/status")
async def status():
    import shutil
    return {"enabled": settings.FACTORY_ENABLED, "scheduler_enabled": settings.FACTORY_SCHEDULER_ENABLED,
        "categories": [c.value for c in Category], "research_hosts": sorted(list(get_allowed_hosts())),
        "capabilities": {"gemini_configured": bool(settings.GEMINI_API_KEY),
            "ffmpeg": bool(shutil.which("ffmpeg")), "ffprobe": bool(shutil.which("ffprobe")),
            "human_review_required": True, "visuals": "owned_animated_graphics",
            "music": "disabled_no_license_configured", "trends_api": False},
        "auto_publish_after_approval": settings.FACTORY_AUTO_PUBLISH,
        "privacy_status": settings.FACTORY_YOUTUBE_PRIVACY,
        "daily_call_limit": settings.FACTORY_DAILY_CALL_LIMIT,
        "daily_budget_microusd": settings.FACTORY_DAILY_BUDGET_MICROUSD,
        "score_weights": settings.FACTORY_SCORE_WEIGHTS,
        "notification_webhook_configured": bool(settings.FACTORY_NOTIFICATION_WEBHOOK)}


class HostInput(BaseModel):
    host: str = Field(min_length=3, max_length=253)


@router.post("/hosts", dependencies=[Depends(require_factory)], status_code=201)
async def add_source_host(data: HostInput):
    try:
        registered = register_source_host(data.host)
        return {"registered": registered, "allowed_hosts": sorted(list(get_allowed_hosts()))}
    except FactoryError as exc:
        raise HTTPException(400, str(exc)) from exc


async def production_or_404(db, production_id):
    production = await db.get(FactoryProduction, production_id)
    if not production:
        raise HTTPException(404, "Produção não encontrada.")
    return production


def serialized(production, topic):
    return {"id": production.id, "topic_id": topic.id, "title": topic.title,
        "category": topic.category, "nature": topic.nature, "score": topic.score,
        "score_breakdown": topic.score_breakdown, "origin": topic.origin,
        "created_at": topic.created_at, "source_urls": topic.source_urls,
        "phase": production.phase, "is_vertical": production.is_vertical,
        "project_id": production.content_project_id, "error": production.error_message,
        "research": production.research, "draft": production.draft,
        "quality_report": production.quality_report, "metrics": production.metrics,
        "approved_by": production.approved_by, "approved_at": production.approved_at,
        "attempts": production.attempts}


@router.get("/productions", dependencies=[Depends(require_factory)])
async def productions(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(FactoryProduction, OriginalTopic).join(OriginalTopic)
        .order_by(FactoryProduction.created_at.desc()).limit(100))).all()
    usage = await db.get(FactoryUsage, datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    accounts = (await db.execute(select(PublishingAccount).where(PublishingAccount.platform == "YOUTUBE", PublishingAccount.is_active == True))).scalars().all()
    return {"items": [serialized(p, t) for p, t in rows],
        "usage": {"calls": usage.calls if usage else 0, "reserved_microusd": usage.reserved_microusd if usage else 0},
        "accounts": [{"id": a.id, "name": a.account_name} for a in accounts]}


@router.post("/topics", dependencies=[Depends(require_factory)], status_code=201)
async def create_topic(data: TopicInput, db: AsyncSession = Depends(get_db)):
    from sqlalchemy.exc import IntegrityError
    try:
        production = await OriginalContentFactory(db).create_topic(data)
    except (FactoryError, IntegrityError) as exc:
        await db.rollback()
        raise HTTPException(409, str(exc) if isinstance(exc, FactoryError) else "Tema duplicado.") from exc
    return {"id": production.id, "phase": production.phase}


@router.post("/discover", dependencies=[Depends(require_factory)])
async def discover(db: AsyncSession = Depends(get_db)):
    return {"created": await OriginalContentFactory(db).discover()}


@router.post("/run-next", dependencies=[Depends(require_factory)])
async def run_next(db: AsyncSession = Depends(get_db)):
    try:
        return await OriginalContentFactory(db).process_next()
    except FactoryError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/productions/{production_id}/approve", dependencies=[Depends(require_factory)])
async def approve(production_id: str, data: Approval, db: AsyncSession = Depends(get_db)):
    await production_or_404(db, production_id)
    try:
        production = await OriginalContentFactory(db).approve(production_id, data)
    except FactoryError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"phase": production.phase}


@router.post("/productions/{production_id}/render", dependencies=[Depends(require_factory)])
async def render(production_id: str, db: AsyncSession = Depends(get_db)):
    await production_or_404(db, production_id)
    try:
        production = await OriginalContentFactory(db).render(production_id)
    except FactoryError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"phase": production.phase, "error": production.error_message}


class PublishInput(BaseModel):
    account_id: str = Field(min_length=1, max_length=36)


@router.post("/productions/{production_id}/publish", dependencies=[Depends(require_factory)])
async def publish(production_id: str, data: PublishInput, db: AsyncSession = Depends(get_db)):
    await production_or_404(db, production_id)
    try:
        return await OriginalContentFactory(db).publish(production_id, data.account_id)
    except FactoryError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/productions/{production_id}/retry", dependencies=[Depends(require_factory)])
async def retry(production_id: str, db: AsyncSession = Depends(get_db)):
    production = await production_or_404(db, production_id)
    if production.phase == "SIMULATED" and settings.AGENT_MODE != "SIMULATION":
        production.phase = "READY"
        OriginalContentFactory(db).audit(production.id, "real_send_requested_after_simulation")
        await db.commit()
        return {"phase": production.phase}
    # Safe recovery of interrupted local work only. Never retry ambiguous upload.
    if production.phase in ("GENERATING", "RENDERING"):
        if not production.started_at or production.started_at > datetime.now(timezone.utc) - timedelta(minutes=30):
            raise HTTPException(409, "Execução ainda pode estar ativa. Aguarde 30 minutos antes de recuperar.")
    elif production.phase not in ("FAILED", "RENDER_FAILED"):
        raise HTTPException(409, "Esta fase não pode ser repetida automaticamente.")
    if production.phase in ("FAILED", "GENERATING") and production.attempts >= settings.FACTORY_MAX_ATTEMPTS:
        raise HTTPException(409, "Número máximo de tentativas atingido.")
    production.phase = "APPROVED" if production.approved_at else "QUEUED"
    production.next_retry_at = None
    production.error_message = None
    OriginalContentFactory(db).audit(production.id, "retry_requested")
    await db.commit()
    return {"phase": production.phase}


@router.post("/productions/{production_id}/metrics", dependencies=[Depends(require_factory)])
async def metrics(production_id: str, db: AsyncSession = Depends(get_db)):
    production = await production_or_404(db, production_id)
    if production.phase != "PUBLISHED":
        raise HTTPException(409, "Métricas disponíveis somente após uma publicação real.")
    job = (await db.execute(select(PublishingJob).where(
        PublishingJob.content_project_id == production.content_project_id,
        PublishingJob.status == ProcessingStatus.PUBLISHED,
        PublishingJob.idempotency_key.like("factory:%"),
    ).order_by(PublishingJob.published_at.desc()).limit(1))).scalar_one_or_none()
    if not job or not job.platform_post_id or job.platform_post_id.startswith("sim_"):
        raise HTTPException(409, "Não há upload real para consultar.")
    account = await db.get(PublishingAccount, job.account_id)
    client = YouTubePublisher(settings.YOUTUBE_CLIENT_ID, settings.YOUTUBE_CLIENT_SECRET, decrypt_secret(account.encrypted_credentials))
    try:
        values = await client.video_statistics(job.platform_post_id)
    except Exception as exc:
        raise HTTPException(502, "YouTube não retornou métricas. Verifique credenciais e disponibilidade.") from exc
    production.metrics = {"youtube": values, "collected_at": datetime.now(timezone.utc).isoformat(), "video_id": job.platform_post_id}
    OriginalContentFactory(db).audit(production.id, "metrics_collected")
    await db.commit()
    return production.metrics


@router.get("/productions/{production_id}/thumbnail", dependencies=[Depends(require_factory)])
async def thumbnail(production_id: str, db: AsyncSession = Depends(get_db)):
    production = await production_or_404(db, production_id)
    if not production.content_project_id or not thumbnail_path(production.content_project_id).is_file():
        raise HTTPException(404, "Miniatura ainda não gerada.")
    return FileResponse(thumbnail_path(production.content_project_id), media_type="image/jpeg", headers={"Cache-Control": "no-store"})
