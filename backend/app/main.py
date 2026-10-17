import asyncio
import logging
import json
import urllib.parse
import httpx

from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from datetime import datetime
import uuid

from app.core.config import settings
from app.core.security import encrypt_secret
from app.db.session import get_db, engine, Base, AsyncSessionLocal

from app.db.schema_upgrade import upgrade_schema
from app.models.entities import (
    Category, Source, NewsItem, VerificationResult, ContentProject,
    PublishingAccount, PublishingJob, AuditLog, ProcessingStatus, RiskLevel
)

logger = logging.getLogger(__name__)
from app.modules.discovery.scheduler import run_discovery, discovery_scheduler_loop
from app.modules.verification.engine import FactVerificationEngine
from app.modules.content.engine import ContentProductionEngine
from app.modules.video.pipeline import VideoProductionPipeline
from app.modules.video.preview import cached_video, render_preview, fingerprint_for, script_for
from app.modules.publishing.dispatcher import PublishingDispatcher
from app.modules.publishing.attribution import project_source_url, youtube_description
from app.modules.original_factory.router import router as factory_router, require_factory, key_header
from app.modules.original_factory.scheduler import factory_scheduler_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="API Operacional do Agente Autônomo de Notícias"
)

app.include_router(factory_router)

# Habilitar CORS para permitir comunicação com o frontend Next.js
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000"
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    # Settings already loads and validates AGENT_MODE, including .env.

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(upgrade_schema)
    
    # Inicia categorias, fontes e contas padrão de forma independente (idempotente).
    # Usa AsyncSessionLocal (expire_on_commit=False): acessar `.id` após commit numa
    # sessão que expira objetos causava erro e deixava o banco sem nenhuma fonte.
    async with AsyncSessionLocal() as session:
        cat_count = (await session.execute(select(func.count(Category.id)))).scalar() or 0
        if cat_count == 0:
            session.add_all([
                Category(slug="politica", name="Política & Eleições", description="Cobertura política e judiciária", priority=1),
                Category(slug="economia", name="Economia & Finanças", description="Mercados, índices e inflação", priority=1),
                Category(slug="seguranca", name="Segurança Pública", description="Operações policiais e judiciais", priority=2),
                Category(slug="tecnologia", name="Tecnologia & IA", description="Inovações e inteligência artificial", priority=1),
                Category(slug="esportes", name="Esportes", description="Futebol e campeonatos", priority=2),
                Category(slug="saude", name="Saúde & Ciência", description="Descobertas e saúde pública", priority=2),
            ])
            await session.commit()

        categories = {c.slug: c.id for c in (await session.execute(select(Category))).scalars().all()}

        # Atualiza ou insere fontes RSS padrão de múltiplos veículos jornalísticos
        existing_sources = {s.feed_url: s for s in (await session.execute(select(Source))).scalars().all()}
        default_sources = [
            # Agência Brasil (EBC) - Pública / Oficial
            {"name": "Agência Brasil (Geral)", "publisher": "EBC", "feed_url": "https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml", "cat": "politica", "trust": 1.0},
            {"name": "Agência Brasil (Economia)", "publisher": "EBC", "feed_url": "https://agenciabrasil.ebc.com.br/rss/economia/feed.xml", "cat": "economia", "trust": 1.0},
            {"name": "Agência Brasil (Política)", "publisher": "EBC", "feed_url": "https://agenciabrasil.ebc.com.br/rss/politica/feed.xml", "cat": "politica", "trust": 1.0},
            {"name": "Agência Brasil (Saúde)", "publisher": "EBC", "feed_url": "https://agenciabrasil.ebc.com.br/rss/saude/feed.xml", "cat": "saude", "trust": 1.0},
            # Grupo Globo (G1)
            {"name": "G1 Economia", "publisher": "Globo", "feed_url": "https://g1.globo.com/rss/g1/economia/", "cat": "economia", "trust": 0.9},
            {"name": "G1 Tecnologia", "publisher": "Globo", "feed_url": "https://g1.globo.com/rss/g1/tecnologia/", "cat": "tecnologia", "trust": 0.9},
            {"name": "G1 Política", "publisher": "Globo", "feed_url": "https://g1.globo.com/rss/g1/politica/", "cat": "politica", "trust": 0.9},
            {"name": "G1 Saúde", "publisher": "Globo", "feed_url": "https://g1.globo.com/rss/g1/ciencia-e-saude/", "cat": "saude", "trust": 0.9},
            # Grupo Folha de S.Paulo
            {"name": "Folha Política / Poder", "publisher": "Folha", "feed_url": "https://feeds.folha.uol.com.br/poder/rss091.xml", "cat": "politica", "trust": 0.9},
            {"name": "Folha Mercado / Economia", "publisher": "Folha", "feed_url": "https://feeds.folha.uol.com.br/mercado/rss091.xml", "cat": "economia", "trust": 0.9},
            {"name": "Folha Tecnologia", "publisher": "Folha", "feed_url": "https://feeds.folha.uol.com.br/tec/rss091.xml", "cat": "tecnologia", "trust": 0.9},
            # UOL & Poder360
            {"name": "UOL Economia", "publisher": "UOL", "feed_url": "https://rss.uol.com.br/feed/economia.xml", "cat": "economia", "trust": 0.85},
            {"name": "Poder360 Notícias", "publisher": "Poder360", "feed_url": "https://www.poder360.com.br/feed/", "cat": "politica", "trust": 0.85},
            # Google News Brasil (Agregador Multi-Fonte)
            {"name": "Google News (Brasil Manchetes)", "publisher": "GoogleNews", "feed_url": "https://news.google.com/rss?hl=pt-BR&gl=BR&ceid=BR:pt-419", "cat": "politica", "trust": 0.85},
            {"name": "Google News (Tecnologia)", "publisher": "GoogleNews", "feed_url": "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=pt-BR&gl=BR&ceid=BR:pt-419", "cat": "tecnologia", "trust": 0.85},
            {"name": "Google News (Economia)", "publisher": "GoogleNews", "feed_url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=pt-BR&gl=BR&ceid=BR:pt-419", "cat": "economia", "trust": 0.85},
        ]

        for s_data in default_sources:
            if s_data["feed_url"] in existing_sources:
                # Atualiza metadados como publisher se estiver vazio
                src = existing_sources[s_data["feed_url"]]
                if not src.publisher:
                    src.publisher = s_data["publisher"]
            else:
                session.add(Source(
                    name=s_data["name"],
                    publisher=s_data["publisher"],
                    source_type="RSS",
                    feed_url=s_data["feed_url"],
                    category_id=categories.get(s_data["cat"]),
                    trust_weight=s_data["trust"]
                ))
        await session.commit()

        acc_count = (await session.execute(select(func.count(PublishingAccount.id)))).scalar() or 0
        if acc_count == 0:
            # Contas de simulação
            session.add_all([
                PublishingAccount(platform="YOUTUBE", account_name="Canal de Notícias Oficial", channel_id="UC123456", encrypted_credentials="sim_token_yt"),
                PublishingAccount(platform="INSTAGRAM", account_name="@noticias_hoje", channel_id="IG98765", encrypted_credentials="sim_token_ig"),
                PublishingAccount(platform="TIKTOK", account_name="@noticias_curtas", channel_id="TK54321", encrypted_credentials="sim_token_tk")
            ])
            await session.commit()

    if settings.FACTORY_ENABLED and settings.FACTORY_SCHEDULER_ENABLED:
        if settings.FACTORY_ADMIN_KEY and len(settings.FACTORY_ADMIN_KEY) >= 32:
            app.state.factory_task = asyncio.create_task(factory_scheduler_loop())
        else:
            logging.warning("Fábrica sem chave administrativa segura; agendador não iniciado.")

    # Coleta automática em segundo plano
    if settings.DISCOVERY_SCHEDULER_ENABLED:
        app.state.discovery_task = asyncio.create_task(discovery_scheduler_loop())

@app.on_event("shutdown")
async def shutdown_event():
    for name in ("discovery_task", "factory_task"):
        task = getattr(app.state, name, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

@app.get("/api/health")
async def health_check():
    return {
        "status": "online",
        "agent_mode": settings.AGENT_MODE,
        "emergency_stop": settings.EMERGENCY_STOP,
        "version": settings.VERSION
    }

# --- STATS / VISÃO GERAL ---
@app.get("/api/v1/dashboard/stats")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    total_news = (await db.execute(select(func.count(NewsItem.id)))).scalar() or 0
    total_verified = (await db.execute(select(func.count(VerificationResult.id)))).scalar() or 0
    total_projects = (await db.execute(select(func.count(ContentProject.id)))).scalar() or 0
    total_published = (await db.execute(select(func.count(PublishingJob.id)).where(PublishingJob.status == ProcessingStatus.PUBLISHED))).scalar() or 0
    total_quarantined = (await db.execute(select(func.count(NewsItem.id)).where(NewsItem.status == ProcessingStatus.QUARANTINED))).scalar() or 0
    total_blocked = (await db.execute(select(func.count(NewsItem.id)).where(NewsItem.status == ProcessingStatus.BLOCKED))).scalar() or 0
    total_pending = (await db.execute(select(func.count(NewsItem.id)).where(NewsItem.status == ProcessingStatus.PENDING))).scalar() or 0

    return {
        "total_news_collected": total_news,
        "total_news_verified": total_verified,
        "total_content_produced": total_projects,
        "total_published": total_published,
        "total_quarantined": total_quarantined,
        "total_blocked": total_blocked,
        "total_pending": total_pending,
        "emergency_stop_active": settings.EMERGENCY_STOP,
        "agent_mode": settings.AGENT_MODE,
        "total_cost_usd": 0.42
    }

# --- AÇÃO: COLETAR NOTÍCIAS AGORA ---
@app.post("/api/v1/actions/trigger-discovery")
async def trigger_discovery():
    """Coleta imediata de todas as fontes ativas (em paralelo, com GET condicional)."""
    report = await run_discovery(force=True)
    total_ingested = report["new_items_count"]
    message = (
        f"Coleta finalizada! {total_ingested} novas notícias foram descobertas e armazenadas "
        f"({report['sources_checked']} fontes, {report['sources_not_modified']} sem mudanças, "
        f"{report['sources_failed']} com falha, {report['elapsed_ms']} ms)."
    )
    return {"success": True, "message": message, **report}

# --- LISTAGEM DE NOTÍCIAS COM DETALHES ---
@app.get("/api/v1/news")
async def list_news(
    limit: int = 50,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(NewsItem).order_by(desc(NewsItem.collected_at)).limit(limit)
    if status and status != "ALL":
        query = query.where(NewsItem.status == status)
    
    items = (await db.execute(query)).scalars().all()
    if not items:
        return []

    item_ids = [it.id for it in items]

    # Carrega verificações e projetos em lote indexados por news_item_id
    ver_stmt = select(VerificationResult).where(VerificationResult.news_item_id.in_(item_ids))
    ver_rows = (await db.execute(ver_stmt)).scalars().all()
    ver_map = {v.news_item_id: v for v in ver_rows}

    proj_stmt = (
        select(ContentProject)
        .where(ContentProject.news_item_id.in_(item_ids))
        .order_by(desc(ContentProject.created_at))
    )
    proj_rows = (await db.execute(proj_stmt)).scalars().all()
    proj_map = {}
    for p in proj_rows:
        if p.news_item_id not in proj_map:
            proj_map[p.news_item_id] = p  # Mantém o mais recente
    
    result = []
    for it in items:
        ver_res = ver_map.get(it.id)
        proj_res = proj_map.get(it.id)

        result.append({
            "id": it.id,
            "title": it.title,
            "url": it.url,
            "summary": it.summary,
            "status": it.status,
            "risk_level": it.risk_level,
            "cluster_id": it.cluster_id,
            "collected_at": it.collected_at.isoformat() if it.collected_at else None,
            "confidence_score": ver_res.confidence_score if ver_res else None,
            "verdict": ver_res.verdict if ver_res else None,
            "has_content": proj_res is not None,
            "project_id": proj_res.id if proj_res else None
        })
    return result

# --- AÇÃO: VERIFICAR NOTÍCIA INDIVIDUAL OU TODAS PENDENTES ---
@app.post("/api/v1/actions/verify/{item_id}")
async def verify_single_news(item_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(NewsItem).where(NewsItem.id == item_id)
    item = (await db.execute(stmt)).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Notícia não encontrada.")
    
    verifier = FactVerificationEngine(db)
    result = await verifier.verify_news_item(item)
    
    # Se a notícia pertencer a um cluster, re-verifica os outros itens do cluster
    if item.cluster_id:
        await verifier.reverify_cluster(item.cluster_id)

    return {
        "success": True,
        "news_id": item.id,
        "cluster_id": item.cluster_id,
        "score": result.confidence_score,
        "verdict": result.verdict,
        "justification": result.justification,
        "status": item.status
    }

@app.post("/api/v1/actions/verify-all-pending")
async def verify_all_pending(db: AsyncSession = Depends(get_db)):
    """Verifica automaticamente todas as notícias pendentes no sistema."""
    stmt = select(NewsItem).where(NewsItem.status == ProcessingStatus.PENDING).limit(100)
    pending_items = (await db.execute(stmt)).scalars().all()
    
    verifier = FactVerificationEngine(db)
    verified_count = 0
    clusters_to_reverify = set()

    for item in pending_items:
        res = await verifier.verify_news_item(item)
        if item.cluster_id:
            clusters_to_reverify.add(item.cluster_id)
        verified_count += 1

    for cid in clusters_to_reverify:
        await verifier.reverify_cluster(cid)

    return {
        "success": True,
        "message": f"{verified_count} notícias verificadas com sucesso!",
        "verified_count": verified_count
    }

# --- AÇÃO: DISPARAR PIPELINE AUTÔNOMO COMPLETO ---
@app.post("/api/v1/actions/run-autonomous-pipeline")
async def run_autonomous_pipeline_endpoint(limit: int = 30):
    """
    Executa o ciclo autônomo completo (Verificação -> Produção -> Publicação)
    para as notícias mais recentes.
    """
    from app.modules.autonomous_pipeline import trigger_autonomous_pipeline
    report = await trigger_autonomous_pipeline(limit=limit)
    return {
        "success": True,
        "processed_count": report.get("processed", 0),
        "details": report.get("details", [])
    }

# --- AÇÃO: PRODUZIR CONTEÚDO E ROTEIROS ---
@app.post("/api/v1/actions/produce-content/{item_id}")
async def produce_content_for_news(item_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(NewsItem).where(NewsItem.id == item_id)
    item = (await db.execute(stmt)).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Notícia não encontrada.")
    
    producer = ContentProductionEngine(db)
    project = await producer.produce_content(item)
    return {
        "success": True,
        "project_id": project.id,
        "headline": project.headline,
        "script_short": project.script_short_vertical,
        "script_long": project.script_youtube_long,
        "social_captions": project.social_captions
    }

# --- AÇÃO: RENDERIZAR VÍDEO (SRT + MP4) ---
@app.post("/api/v1/actions/render-video/{project_id}")
async def render_video_endpoint(project_id: str, is_vertical: bool = False, db: AsyncSession = Depends(get_db)):
    stmt = select(ContentProject).where(ContentProject.id == project_id)
    project = (await db.execute(stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projeto de conteúdo não encontrado.")

    if isinstance(project.social_captions, dict) and project.social_captions.get("_factory"):
        raise HTTPException(409, "Use a renderização protegida da fábrica após aprovação editorial.")

    try:
        path = await asyncio.to_thread(render_preview, project, is_vertical)
    except (RuntimeError, ValueError, OSError) as exc:
        logger.error("[RenderVideo] Falha esperada na renderização de %s: %s", project_id, exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[RenderVideo] Erro inesperado na renderização de %s: %s", project_id, exc)
        raise HTTPException(status_code=500, detail=f"Erro interno na renderização: {str(exc)}") from exc
    pipeline = VideoProductionPipeline()
    srt_path = pipeline.generate_srt_subtitles(script_for(project, is_vertical) or project.headline)
    return {
        "success": True,
        "video_path": path,
        "video_url": f"/api/v1/content-projects/{project.id}/preview/video?is_vertical={str(is_vertical).lower()}&v={fingerprint_for(project, is_vertical)}",
        "resolution": "1080x1920" if is_vertical else "1920x1080",
        "format": "vertical_9_16" if is_vertical else "horizontal_16_9",
        "subtitles_srt": srt_path,
        "has_ffmpeg": True,
    }


@app.get("/api/v1/content-projects/{project_id}/preview")
async def get_content_preview(project_id: str, is_vertical: bool = True, db: AsyncSession = Depends(get_db), key: str | None = Depends(key_header)):
    project = (await db.execute(select(ContentProject).where(ContentProject.id == project_id))).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    if isinstance(project.social_captions, dict) and project.social_captions.get("_factory"):
        require_factory(key)
    ready = cached_video(project, is_vertical) is not None
    source_url = await project_source_url(project, db)
    return {
        "project_id": project.id,
        "headline": project.headline,
        "summary": project.editorial_summary,
        "source_url": source_url,
        "publication_description": youtube_description(project, source_url) if source_url else None,
        "requires_human_approval": project.requires_human_approval,
        "ready": ready,
        "video_url": (f"/api/v1/content-projects/{project.id}/preview/video?is_vertical={str(is_vertical).lower()}&v={fingerprint_for(project, is_vertical)}" if ready else None),
    }


@app.get("/api/v1/content-projects/{project_id}/preview/video")
async def get_preview_video(project_id: str, is_vertical: bool = True, db: AsyncSession = Depends(get_db), key: str | None = Depends(key_header)):
    project = (await db.execute(select(ContentProject).where(ContentProject.id == project_id))).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    if isinstance(project.social_captions, dict) and project.social_captions.get("_factory"):
        require_factory(key)
    video = cached_video(project, is_vertical)
    if not video:
        raise HTTPException(status_code=404, detail="Prévia não gerada ou desatualizada. Gere o vídeo novamente.")
    # FileResponse supports byte ranges for seeking; never expose storage or
    # accept a client-supplied filesystem path.
    return FileResponse(video, media_type="video/mp4", headers={"Cache-Control": "no-store"})

# --- AÇÃO: DISPARAR PUBLICAÇÃO ---
@app.post("/api/v1/actions/publish/{project_id}")
async def publish_content(project_id: str, is_vertical: bool = False, db: AsyncSession = Depends(get_db)):
    stmt = select(ContentProject).where(ContentProject.id == project_id)
    project = (await db.execute(stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")

    accounts = (await db.execute(select(PublishingAccount).where(PublishingAccount.is_active == True))).scalars().all()
    if not accounts:
        raise HTTPException(status_code=400, detail="Nenhuma conta de publicação configurada.")

    published_results = []
    for acc in accounts:
        job = PublishingJob(
            id=str(uuid.uuid4()),
            content_project_id=project.id,
            account_id=acc.id,
            status=ProcessingStatus.READY_TO_PUBLISH,
            idempotency_key=f"job_{project.id}_{acc.id}_{int(datetime.utcnow().timestamp())}"
        )
        db.add(job)
        await db.commit()

        dispatcher = PublishingDispatcher(acc, db=db, is_vertical=is_vertical)
        dispatch_res = await dispatcher.publish(job, project)
        await db.commit()
        published_results.append({
            "platform": acc.platform,
            "account": acc.account_name,
            "status": job.status,
            "details": dispatch_res
        })

    return {
        "success": any(r["details"].get("success") for r in published_results),
        "project_id": project.id,
        "published_destinations": published_results
    }

# --- AÇÃO: ALTERNAR MODO DE OPERAÇÃO ---
class ModeUpdate(BaseModel):
    mode: str

@app.post("/api/v1/system/agent-mode")
async def update_agent_mode(data: ModeUpdate):
    if data.mode not in ["SIMULATION", "ASSISTED", "AUTONOMOUS"]:
        raise HTTPException(status_code=400, detail="Modo inválido. Escolha SIMULATION, ASSISTED ou AUTONOMOUS.")
    settings.AGENT_MODE = data.mode
    return {
        "success": True,
        "agent_mode": settings.AGENT_MODE,
        "message": f"Modo alterado para {settings.AGENT_MODE}."
    }

# --- AÇÃO: PARADA DE EMERGÊNCIA ---
@app.post("/api/v1/system/emergency-stop")
async def toggle_emergency_stop(active: bool):
    settings.EMERGENCY_STOP = active
    return {
        "emergency_stop": settings.EMERGENCY_STOP,
        "message": "Parada de emergência ATIVADA! Todas as publicações estão suspensas." if active else "Parada de emergência DESATIVADA. Fluxo liberado."
    }

# --- LISTAR FONTES ---
@app.get("/api/v1/sources")
async def list_sources(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Source))
    return result.scalars().all()

# --- LISTAR CATEGORIAS ---
@app.get("/api/v1/categories")
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category))
    return result.scalars().all()

# --- CONTAS DE PUBLICAÇÃO ---
@app.get("/api/v1/publishing-accounts")
async def list_publishing_accounts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PublishingAccount).order_by(PublishingAccount.created_at.desc()))
    accounts = result.scalars().all()
    return [
        {
            "id": a.id,
            "platform": a.platform,
            "account_name": a.account_name,
            "channel_id": a.channel_id,
            "is_active": a.is_active,
            "is_paused": a.is_paused,
            "daily_post_limit": a.daily_post_limit,
            "posts_today": a.posts_today,
            "created_at": a.created_at.isoformat() if a.created_at else None
        }
        for a in accounts
    ]

@app.post("/api/v1/publishing-accounts/{account_id}/reset-counter")
async def reset_account_counter(account_id: str, new_limit: Optional[int] = 50, db: AsyncSession = Depends(get_db)):
    account = (await db.execute(select(PublishingAccount).where(PublishingAccount.id == account_id))).scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada.")
    account.posts_today = 0
    if new_limit:
        account.daily_post_limit = new_limit
    await db.commit()
    return {
        "success": True,
        "message": f"Contador de {account.account_name} zerado com sucesso! Limite definido para {account.daily_post_limit}."
    }


# --- AUTENTICAÇÃO OAUTH YOUTUBE ---
YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]

@app.get("/api/v1/auth/youtube/login")
async def youtube_oauth_login():
    """Inicia o fluxo OAuth 2.0 gerando a URL de autorização do Google."""
    client_id = settings.YOUTUBE_CLIENT_ID
    if not client_id or not settings.YOUTUBE_CLIENT_SECRET:
        raise HTTPException(
            status_code=400,
            detail="YOUTUBE_CLIENT_ID ou YOUTUBE_CLIENT_SECRET não configurados no arquivo .env"
        )
    
    redirect_uri = "http://localhost:8000/api/v1/auth/youtube/callback"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(YOUTUBE_SCOPES),
        "access_type": "offline",
        "prompt": "consent"
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    return {"auth_url": auth_url}

@app.get("/api/v1/auth/youtube/callback")
async def youtube_oauth_callback(
    code: Optional[str] = None,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Callback chamado pelo Google após o usuário autorizar o canal."""
    if error:
        return RedirectResponse(url=f"http://localhost:3000?youtube_auth=error&reason={error}")
    if not code:
        return RedirectResponse(url="http://localhost:3000?youtube_auth=error&reason=no_code")

    redirect_uri = "http://localhost:8000/api/v1/auth/youtube/callback"

    # Troca o código de autorização por Access Token e Refresh Token
    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        "code": code,
        "client_id": settings.YOUTUBE_CLIENT_ID,
        "client_secret": settings.YOUTUBE_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_resp = await client.post(token_url, data=token_data)
            tokens = token_resp.json()

        if "error" in tokens:
            err_desc = urllib.parse.quote(tokens.get("error_description", tokens["error"]))
            return RedirectResponse(url=f"http://localhost:3000?youtube_auth=error&reason={err_desc}")

        access_token = tokens.get("access_token")
        
        # Obter dados do canal no YouTube (ID e Nome)
        channel_name = "Canal do YouTube"
        channel_id = "UC_CANAL_CONECTADO"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                ch_resp = await client.get(
                    "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                if ch_resp.status_code == 200:
                    ch_data = ch_resp.json()
                    items = ch_data.get("items", [])
                    if items:
                        channel_id = items[0].get("id", channel_id)
                        channel_name = items[0].get("snippet", {}).get("title", channel_name)
        except Exception as e:
            logging.warning(f"Não foi possível buscar detalhes do canal: {e}")

        # Salva o token criptografado
        encrypted_creds = encrypt_secret(json.dumps(tokens))

        # Atualiza ou cria a PublishingAccount
        existing = (await db.execute(
            select(PublishingAccount).where(
                PublishingAccount.platform == "YOUTUBE"
            )
        )).scalars().first()

        if existing:
            existing.account_name = channel_name
            existing.channel_id = channel_id
            existing.encrypted_credentials = encrypted_creds
            existing.is_active = True
            existing.is_paused = False
        else:
            new_acc = PublishingAccount(
                platform="YOUTUBE",
                account_name=channel_name,
                channel_id=channel_id,
                encrypted_credentials=encrypted_creds,
                is_active=True,
                is_paused=False,
                daily_post_limit=10
            )
            db.add(new_acc)

        await db.commit()
        return RedirectResponse(url=f"http://localhost:3000?youtube_auth=success&channel={urllib.parse.quote(channel_name)}")

    except Exception as exc:
        logging.error(f"Erro no callback do YouTube: {exc}")
        return RedirectResponse(url=f"http://localhost:3000?youtube_auth=error&reason={urllib.parse.quote(str(exc))}")

