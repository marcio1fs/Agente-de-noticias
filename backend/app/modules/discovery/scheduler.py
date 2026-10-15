"""
Agendador da coleta de notícias.

Roda em segundo plano no processo da API: a cada DISCOVERY_TICK_SECONDS procura fontes
ativas cuja `next_check_at` venceu e coleta todas em paralelo. O intervalo de cada fonte
vem de `Source.check_interval_minutes`, com backoff exponencial em caso de falha.
"""
import asyncio
import logging
from typing import Any, Dict

from sqlalchemy import or_, select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.entities import Source
from app.modules.discovery.engine import NewsDiscoveryEngine, utcnow

logger = logging.getLogger(__name__)

# Impede ciclos sobrepostos (agendador x botão "Coletar agora")
discovery_lock = asyncio.Lock()


async def run_discovery(force: bool = False) -> Dict[str, Any]:
    """
    Executa um ciclo de coleta.
    force=False: apenas fontes vencidas (uso do agendador).
    force=True: todas as fontes ativas (uso do botão manual).
    """
    async with discovery_lock:
        async with AsyncSessionLocal() as db:
            query = select(Source).where(Source.is_active == True)  # noqa: E712
            if not force:
                query = query.where(or_(Source.next_check_at.is_(None), Source.next_check_at <= utcnow()))
            sources = (await db.execute(query)).scalars().all()
            return await NewsDiscoveryEngine(db).run_discovery_cycle(sources)


async def discovery_scheduler_loop() -> None:
    logger.info("[Scheduler] Coleta automática iniciada (tick=%ss)", settings.DISCOVERY_TICK_SECONDS)
    while True:
        try:
            report = await run_discovery(force=False)
            if report["sources_checked"]:
                logger.info(
                    "[Scheduler] %s fontes checadas | %s novas | %s sem mudança (304) | %s falhas | %sms",
                    report["sources_checked"], report["new_items_count"],
                    report["sources_not_modified"], report["sources_failed"], report["elapsed_ms"],
                )

            # Aciona o pipeline autônomo imediato se houver notícias novas ou no modo autônomo
            if settings.AUTONOMOUS_PIPELINE_ENABLED:
                from app.modules.autonomous_pipeline import trigger_autonomous_pipeline
                auto_report = await trigger_autonomous_pipeline(limit=30)
                if auto_report.get("processed", 0) > 0:
                    logger.info("[Scheduler] Pipeline autônomo processou %s notícias.", auto_report["processed"])
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[Scheduler] Erro inesperado no ciclo de coleta")
        await asyncio.sleep(max(5, settings.DISCOVERY_TICK_SECONDS))
