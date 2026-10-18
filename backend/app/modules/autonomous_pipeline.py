"""
Pipeline Autônomo e Motor de Breaking News (Furos de Reportagem).

Responsável por orquestrar a passagem imediata de notícias descobertas por todas as etapas:
1. Verificação Factual e Clusterização (Agrupamento com outras fontes).
2. Avaliação de Breaking News / Furo Urgente (Multi-fontes cobrindo em tempo real).
3. Produção Editorial e Roteirização Jornalística.
4. Renderização Multimídia (Vídeo / Áudio / Legendas).
5. Despacho e Publicação Automática (se risco LOW e confiança >= 80% no modo AUTONOMOUS).
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.entities import (
    NewsItem, ContentProject, PublishingAccount, PublishingJob,
    ProcessingStatus, RiskLevel, VerificationResult
)
from app.modules.verification.engine import FactVerificationEngine
from app.modules.content.engine import ContentProductionEngine
from app.modules.video.pipeline import VideoProductionPipeline
from app.modules.publishing.dispatcher import PublishingDispatcher

logger = logging.getLogger(__name__)


class AutonomousNewsPipeline:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.verifier = FactVerificationEngine(db)
        self.producer = ContentProductionEngine(db)

    async def process_item(self, item: NewsItem) -> Dict[str, Any]:
        """
        Executa o fluxo completo para uma notícia individual.
        Retorna relatório de execução.
        """
        result: Dict[str, Any] = {
            "news_id": item.id,
            "title": item.title,
            "verified": False,
            "produced": False,
            "published": False,
            "status": item.status,
            "is_breaking": False
        }

        # 1. VERIFICAÇÃO FACTUAL
        ver_res: VerificationResult = await self.verifier.verify_news_item(item)
        result["verified"] = True
        result["confidence_score"] = ver_res.confidence_score
        result["verdict"] = ver_res.verdict
        result["risk_level"] = item.risk_level

        # Re-verifica cluster se pertencer a um
        if item.cluster_id:
            await self.verifier.reverify_cluster(item.cluster_id)

        # Se for Quarentena ou Bloqueado, encerra o fluxo com segurança
        if item.status in [ProcessingStatus.QUARANTINED, ProcessingStatus.BLOCKED]:
            result["status"] = item.status
            result["reason"] = "Item retido por segurança (quarentena ou bloqueio)"
            return result

        # 2. PRODUÇÃO EDITORIAL & ROTEIRO
        project = await self.producer.produce_content(item)
        result["produced"] = True
        result["project_id"] = project.id

        # 3. VERIFICAÇÃO SE REQUER APROVAÇÃO HUMANA
        # Se for Risco Alto ou Médio com baixa confiança, retém para o editor
        if item.status == ProcessingStatus.APPROVAL_REQUIRED or project.requires_human_approval:
            result["status"] = ProcessingStatus.APPROVAL_REQUIRED
            result["reason"] = "Retido para aprovação da equipe editorial"
            return result

        # 4. DISPARO AUTÔNOMO DE PUBLICAÇÃO (se configurado)
        if settings.AGENT_MODE in ["AUTONOMOUS", "SIMULATION"] and settings.AUTONOMOUS_AUTO_PUBLISH_LOW_RISK:
            # Critério de ouro: Confiança >= 80% e Risco LOW (ou modo simulação)
            can_publish = (
                settings.AGENT_MODE == "SIMULATION" or
                (item.risk_level == RiskLevel.LOW and ver_res.confidence_score >= 80.0)
            )

            if can_publish and not settings.EMERGENCY_STOP:
                # Localiza contas ativas
                acc_stmt = select(PublishingAccount).where(PublishingAccount.is_active == True)
                accounts = (await self.db.execute(acc_stmt)).scalars().all()

                published_dests = []
                for acc in accounts:
                    if acc.is_paused:
                        continue

                    job = PublishingJob(
                        id=str(uuid.uuid4()),
                        content_project_id=project.id,
                        account_id=acc.id,
                        status=ProcessingStatus.READY_TO_PUBLISH,
                        idempotency_key=f"auto_job_{project.id}_{acc.id}_{int(datetime.now(timezone.utc).timestamp())}"
                    )
                    self.db.add(job)
                    await self.db.flush()

                    is_vert = (settings.AUTONOMOUS_PUBLISH_FORMAT == "vertical")
                    dispatcher = PublishingDispatcher(acc, db=self.db, is_vertical=is_vert)
                    dispatch_res = await dispatcher.publish(job, project)
                    published_dests.append({
                        "platform": acc.platform,
                        "account": acc.account_name,
                        "status": job.status,
                        "details": dispatch_res
                    })

                await self.db.commit()
                result["published"] = any(d["details"].get("success") for d in published_dests)
                result["published_destinations"] = published_dests
                result["status"] = ProcessingStatus.PUBLISHED if result["published"] else ProcessingStatus.FAILED
                logger.info("[Autonomous Pipeline] Notícia %s: published=%s", item.id, result["published"])
            else:
                result["reason"] = f"Não atende aos critérios de publicação automática (Score: {ver_res.confidence_score}%, Risco: {item.risk_level})"

        return result


async def trigger_autonomous_pipeline(limit: int = 50) -> Dict[str, Any]:
    """
    Varre itens pendentes e processa-os através do pipeline autônomo.
    """
    if not settings.AUTONOMOUS_PIPELINE_ENABLED:
        return {"processed": 0, "message": "Pipeline autônomo desativado nas configurações."}

    async with AsyncSessionLocal() as db:
        stmt = (
            select(NewsItem)
            .where(NewsItem.status == ProcessingStatus.PENDING)
            .order_by(desc(NewsItem.collected_at))
            .limit(limit)
        )
        pending_items = (await db.execute(stmt)).scalars().all()

        if not pending_items:
            return {"processed": 0, "message": "Nenhuma notícia pendente encontrada."}

        pipeline = AutonomousNewsPipeline(db)
        results = []
        for item in pending_items:
            try:
                res = await pipeline.process_item(item)
                results.append(res)
            except Exception as e:
                logger.exception("[Autonomous Pipeline] Erro processando notícia ID %s", item.id)
                await db.rollback()
                results.append({"news_id": item.id, "error": str(e)})

        return {
            "processed": len(results),
            "details": results
        }
