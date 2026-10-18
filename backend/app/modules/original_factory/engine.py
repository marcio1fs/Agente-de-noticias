"""Persistent, opt-in orchestration reusing ContentProject, render and dispatcher."""
import asyncio
from datetime import datetime, timedelta, timezone
import logging
from difflib import SequenceMatcher

import httpx
from sqlalchemy import select, update, or_, case
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.models.entities import (OriginalTopic, FactoryProduction, FactoryUsage, ContentProject,
    NewsItem, PublishingAccount, PublishingJob, ProcessingStatus, AuditLog)
from app.modules.original_factory.schemas import TopicInput, OriginalDraft
from app.modules.original_factory.services import (FactoryError, TopicScoringService, ResearchService,
    OriginalScriptService, EditorialQualityService, topic_key, allowed_source)
from app.modules.verification.engine import calculate_title_similarity
from app.modules.video.preview import render_preview, fingerprint_for
from app.modules.publishing.attribution import youtube_description

logger = logging.getLogger(__name__)


class OriginalContentFactory:
    def __init__(self, db):
        self.db = db

    def audit(self, production_id, action, details=None):
        self.db.add(AuditLog(action=f"factory.{action}", entity_type="FactoryProduction",
                             entity_id=production_id, details=details or {}))

    async def notify(self, event_type: str, production_id: str, payload: dict = None):
        webhook_url = settings.FACTORY_NOTIFICATION_WEBHOOK
        if not webhook_url:
            return
        body = {
            "source": "OriginalContentFactory",
            "event": event_type,
            "production_id": production_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": payload or {}
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(webhook_url, json=body)
        except Exception as exc:
            logger.warning("Falha ao enviar webhook da fábrica: %s", type(exc).__name__)

    async def create_topic(self, data: TopicInput, origin="manual"):
        if data.category.value == "hipoteses" and data.nature == "FACTUAL":
            raise FactoryError("Cenários hipotéticos precisam da natureza HYPOTHESIS ou FICTION.")
        for url in data.source_urls:
            allowed_source(url)
        existing = (await self.db.execute(select(OriginalTopic).order_by(OriginalTopic.created_at.desc()).limit(500))).scalars().all()
        if any(t.dedup_key == topic_key(data.title) or calculate_title_similarity(t.title, data.title) > 0.9 for t in existing):
            raise FactoryError("Tema igual ou muito semelhante já cadastrado; escolha uma abordagem diferente.")
        score, breakdown = TopicScoringService.score(data.title, len(set(data.source_urls)))
        topic = OriginalTopic(title=data.title.strip(), category=data.category.value, nature=data.nature,
                              source_urls=list(dict.fromkeys(data.source_urls)), dedup_key=topic_key(data.title),
                              origin=origin, score=score, score_breakdown=breakdown)
        self.db.add(topic)
        await self.db.flush()
        production = FactoryProduction(topic_id=topic.id, is_vertical=data.is_vertical, phase="QUEUED")
        self.db.add(production)
        await self.db.flush()
        self.audit(production.id, "created", {"origin": origin, "score": score})
        await self.db.commit()
        return production

    async def discover(self):
        # Reuse collected feeds instead of pretending to have a trends/search API.
        rows = (await self.db.execute(select(NewsItem).order_by(NewsItem.collected_at.desc()).limit(100))).scalars().all()
        from app.modules.discovery.engine import normalize_text
        from app.modules.original_factory.schemas import Category
        keywords = {"espaco": ("planeta", "universo", "espaco", "nasa"), "ciencia": ("cient", "pesquisa", "descoberta"),
                    "tecnologia": ("tecnolog", "inteligencia artificial"), "historia": ("arqueolog", "histor"),
                    "natureza": ("fenomeno", "vulcao", "oceano"), "cerebro": ("cerebro", "psicolog")}
        created = []
        for news in rows:
            if news.status in (ProcessingStatus.BLOCKED, ProcessingStatus.QUARANTINED):
                continue
            try:
                allowed_source(news.url)
            except FactoryError:
                continue
            title = normalize_text(news.title)
            category = next((k for k, terms in keywords.items() if any(term in title for term in terms)), None)
            if not category:
                continue
            try:
                production = await self.create_topic(TopicInput(title=f"Entenda: {news.title}"[:300], category=Category(category), source_urls=[news.url]), origin="existing_feed")
                created.append(production.id)
            except FactoryError:
                continue
            if len(created) >= 5:
                break
        return created

    async def reserve_call(self):
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if not await self.db.get(FactoryUsage, day):
            try:
                async with self.db.begin_nested():
                    self.db.add(FactoryUsage(day=day, calls=0, reserved_microusd=0))
            except IntegrityError:
                pass
        reservation = settings.FACTORY_CALL_RESERVATION_MICROUSD
        result = await self.db.execute(update(FactoryUsage).where(
            FactoryUsage.day == day,
            FactoryUsage.calls < settings.FACTORY_DAILY_CALL_LIMIT,
            FactoryUsage.reserved_microusd + reservation <= settings.FACTORY_DAILY_BUDGET_MICROUSD,
        ).values(calls=FactoryUsage.calls + 1, reserved_microusd=FactoryUsage.reserved_microusd + reservation))
        await self.db.commit()
        if result.rowcount != 1:
            raise FactoryError("Cota/orçamento diário esgotado ou não autorizado. Nenhuma chamada de IA efetuada.")

    async def claim(self, production_id, phases, target):
        result = await self.db.execute(update(FactoryProduction).where(
            FactoryProduction.id == production_id, FactoryProduction.phase.in_(phases),
        ).values(phase=target, started_at=datetime.now(timezone.utc), error_message=None))
        await self.db.commit()
        if result.rowcount != 1:
            raise FactoryError("Produção ocupada ou etapa incompatível com esta ação.")
        production = await self.db.get(FactoryProduction, production_id)
        await self.db.refresh(production)
        return production

    async def generate(self, production_id):
        if settings.EMERGENCY_STOP:
            raise FactoryError("Parada de emergência ativa.")
        production = await self.claim(production_id, ["QUEUED"], "GENERATING")
        production.attempts += 1
        await self.db.commit()
        try:
            if not settings.GEMINI_API_KEY:
                raise FactoryError("Configure GEMINI_API_KEY para gerar conteúdo original.")
            topic = await self.db.get(OriginalTopic, production.topic_id)
            sources = await ResearchService().fetch(topic.source_urls)
            production.research = sources
            await self.db.commit()
            if settings.EMERGENCY_STOP:
                raise FactoryError("Produção interrompida pela parada de emergência.")
            await self.reserve_call()
            draft = await OriginalScriptService().generate(topic, sources)
            production.draft = draft.model_dump()
            report = EditorialQualityService.check(topic, draft, sources)
            previous = (await self.db.execute(select(ContentProject).join(FactoryProduction,
                FactoryProduction.content_project_id == ContentProject.id).limit(100))).scalars().all()
            if any(SequenceMatcher(None, draft.short_script, old.script_short_vertical or "").ratio() > 0.85 for old in previous):
                report["passed"] = False
                report["issues"].append("Roteiro muito semelhante a uma produção anterior da fábrica.")
            production.quality_report = report
            if report["passed"]:
                sources_text = "\n".join(s["url"] for s in sources)
                disclosure = "Conteúdo original com roteiro e narração assistidos por IA. Imagens ilustrativas."
                if topic.nature != "FACTUAL":
                    disclosure += " Cenário hipotético/ficcional; não é previsão nem fato comprovado."
                description = f"{draft.description}\n\n{disclosure}\n\nFontes de pesquisa:\n{sources_text}\n\n" + " ".join(tag for tag in draft.hashtags if tag.startswith("#"))
                project = ContentProject(headline=draft.title, editorial_summary=draft.description,
                    script_short_vertical=draft.short_script, script_youtube_long=draft.long_script,
                    full_article=draft.description, requires_human_approval=True,
                    status=ProcessingStatus.APPROVAL_REQUIRED,
                    social_captions={"youtube": description, "_factory": True, "_nature": topic.nature})
                final_description = youtube_description(project, sources[0]["url"])
                if any(source["url"] not in final_description for source in sources):
                    raise FactoryError("Fontes excedem o espaço da descrição. Use URLs mais curtas sem perder a origem.")
                self.db.add(project)
                await self.db.flush()
                production.content_project_id = project.id
                production.phase = "REVIEW_REQUIRED"
            else:
                production.phase = "QUALITY_BLOCKED"
            self.audit(production.id, "generated", {"passed": report["passed"], "issues": report["issues"]})
            await self.db.commit()
            await self.notify(production.phase, production.id, {"title": topic.title, "passed": report["passed"], "issues": report["issues"]})
        except Exception as exc:
            # No provider response text/keys are exposed to the UI or audit log.
            await self.db.rollback()
            production = await self.db.get(FactoryProduction, production_id)
            await self.db.refresh(production)
            transient = isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)) or (
                isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (429, 500, 502, 503, 504))
            production.phase = "QUEUED" if transient and production.attempts < settings.FACTORY_MAX_ATTEMPTS else "FAILED"
            production.error_message = str(exc) if isinstance(exc, FactoryError) else f"Falha {type(exc).__name__}; consulte configuração/provedor e revise antes de repetir."
            production.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=60 * 2 ** production.attempts) if transient else None
            self.audit(production.id, "generation_failed", {"type": type(exc).__name__, "retry": production.phase == "QUEUED"})
            await self.db.commit()
        return production

    async def approve(self, production_id, approval):
        if not (approval.facts_checked and approval.rights_checked and approval.script_reviewed):
            raise FactoryError("Confirme a revisão factual, os direitos e o roteiro.")
        production = await self.db.get(FactoryProduction, production_id)
        if not production or production.phase != "REVIEW_REQUIRED" or not production.quality_report.get("passed"):
            raise FactoryError("Produção não está pronta para aprovação.")
        project = await self.db.get(ContentProject, production.content_project_id)
        production.approved_at = datetime.now(timezone.utc)
        production.approved_by = approval.reviewer
        production.phase = "APPROVED"
        production.quality_report = {**production.quality_report, "approved_fingerprint": fingerprint_for(project, production.is_vertical)}
        project.requires_human_approval = False
        self.audit(production.id, "approved", {"reviewer": approval.reviewer})
        await self.db.commit()
        return production

    async def render(self, production_id):
        if settings.EMERGENCY_STOP:
            raise FactoryError("Parada de emergência ativa.")
        production = await self.claim(production_id, ["APPROVED"], "RENDERING")
        try:
            from app.modules.original_factory.media import technical_quality, create_thumbnail
            project = await self.db.get(ContentProject, production.content_project_id)
            if production.quality_report.get("approved_fingerprint") != fingerprint_for(project, production.is_vertical):
                raise FactoryError("Roteiro alterado depois da aprovação; nova revisão necessária.")
            video = await asyncio.to_thread(render_preview, project, production.is_vertical)
            technical = await asyncio.to_thread(technical_quality, video, production.is_vertical)
            production.quality_report = {**production.quality_report, "technical": technical}
            if not technical["passed"]:
                raise FactoryError("Vídeo reprovado na checagem técnica: " + "; ".join(technical["issues"]))
            topic = await self.db.get(OriginalTopic, production.topic_id)
            await asyncio.to_thread(create_thumbnail, project.id, production.draft.get("thumbnail_text", project.headline), topic.category if topic else None)
            production.phase = "READY"
            project.status = ProcessingStatus.READY_TO_PUBLISH
            self.audit(production.id, "rendered", {"technical": technical})
            await self.db.commit()
        except Exception as exc:
            production.phase = "RENDER_FAILED"
            production.error_message = str(exc) if isinstance(exc, (FactoryError, RuntimeError)) else f"Renderização falhou ({type(exc).__name__})."
            self.audit(production.id, "render_failed", {"type": type(exc).__name__})
            await self.db.commit()
        return production

    async def publish(self, production_id, account_id):
        if settings.EMERGENCY_STOP:
            raise FactoryError("Parada de emergência ativa.")
        account = await self.db.get(PublishingAccount, account_id)
        if not account or account.platform != "YOUTUBE" or not account.is_active:
            raise FactoryError("Selecione uma conta YouTube ativa.")
        production = await self.claim(production_id, ["READY"], "PUBLISHING")
        project = await self.db.get(ContentProject, production.content_project_id)
        if (not production.approved_at or not production.quality_report.get("technical", {}).get("passed")
                or production.quality_report.get("approved_fingerprint") != fingerprint_for(project, production.is_vertical)):
            production.phase = "REVIEW_REQUIRED"
            await self.db.commit()
            raise FactoryError("Aprovação/qualidade inválida ou roteiro alterado; reveja o conteúdo.")
        key = f"factory:{production.id}:{account.id}:{settings.AGENT_MODE}"
        job = (await self.db.execute(select(PublishingJob).where(PublishingJob.idempotency_key == key))).scalar_one_or_none()
        if job and job.status != ProcessingStatus.PUBLISHED and not (job.error_message or "").startswith("FACTORY_PREFLIGHT:"):
            production.phase = "UPLOAD_UNKNOWN"
            await self.db.commit()
            raise FactoryError("Já houve tentativa de envio. Reconcilie no YouTube antes de repetir para evitar duplicatas.")
        if not job:
            job = PublishingJob(content_project_id=project.id, account_id=account.id,
                idempotency_key=key, status=ProcessingStatus.READY_TO_PUBLISH)
            self.db.add(job)
            await self.db.commit()
        from app.modules.publishing.dispatcher import PublishingDispatcher
        response = await PublishingDispatcher(account, db=self.db, is_vertical=production.is_vertical,
                                               factory_authorized=True).publish(job, project)
        safe_preflight = response.get("reason") in {"EMERGENCY_STOP_ACTIVE", "PUBLICATION_STOPPED_AFTER_RENDER", "ACCOUNT_PAUSED", "DAILY_LIMIT_REACHED", "PUBLISHER_NOT_CONFIGURED", "SOURCE_URL_MISSING"}
        production.phase = ("SIMULATED" if settings.AGENT_MODE == "SIMULATION" else "PUBLISHED") if response.get("success") else ("READY" if safe_preflight else "UPLOAD_UNKNOWN")
        if safe_preflight:
            job.error_message = "FACTORY_PREFLIGHT:" + response["reason"]
        production.error_message = None if response.get("success") else (response.get("error") or response.get("reason") if safe_preflight else "Envio não confirmado. Revise a tentativa no canal antes de repetir.")
        self.audit(production.id, "publish_result", {"success": response.get("success"), "mode": settings.AGENT_MODE, "job_id": job.id})
        await self.db.commit()
        if response.get("success") and settings.AGENT_MODE != "SIMULATION":
            from app.modules.publishing.youtube import YouTubePublisher
            from app.core.security import decrypt_secret
            from app.modules.original_factory.media import thumbnail_path
            client = YouTubePublisher(settings.YOUTUBE_CLIENT_ID, settings.YOUTUBE_CLIENT_SECRET, decrypt_secret(account.encrypted_credentials))
            try:
                response["thumbnail_uploaded"] = await client.set_thumbnail(job.platform_post_id, str(thumbnail_path(project.id)))
            except Exception:
                response["thumbnail_uploaded"] = False
            self.audit(production.id, "thumbnail_upload", {"success": response.get("thumbnail_uploaded")})
            await self.db.commit()
        return {"production_id": production.id, "phase": production.phase, "result": response}

    async def process_next(self):
        if settings.EMERGENCY_STOP:
            return {"processed": False, "reason": "EMERGENCY_STOP"}
        candidate = (await self.db.execute(select(FactoryProduction).join(OriginalTopic).where(
            FactoryProduction.phase.in_(["QUEUED", "APPROVED"] + (["READY"] if settings.FACTORY_AUTO_PUBLISH and settings.AGENT_MODE == "AUTONOMOUS" and settings.FACTORY_YOUTUBE_ACCOUNT_ID else [])),
            or_(FactoryProduction.next_retry_at.is_(None), FactoryProduction.next_retry_at <= datetime.now(timezone.utc)),
        ).order_by(case((FactoryProduction.phase == "READY", 0), (FactoryProduction.phase == "APPROVED", 1), else_=2), OriginalTopic.score.desc(), FactoryProduction.created_at).limit(1))).scalar_one_or_none()
        if not candidate:
            return {"processed": False}
        if candidate.phase == "QUEUED":
            await self.generate(candidate.id)
        elif candidate.phase == "APPROVED":
            await self.render(candidate.id)
        elif settings.FACTORY_AUTO_PUBLISH and settings.AGENT_MODE == "AUTONOMOUS":
            account = await self.db.get(PublishingAccount, settings.FACTORY_YOUTUBE_ACCOUNT_ID)
            if account:
                await self.publish(candidate.id, account.id)
        return {"processed": True, "production_id": candidate.id, "phase": candidate.phase}
