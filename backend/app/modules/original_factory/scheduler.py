import asyncio
import logging
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.modules.original_factory.engine import OriginalContentFactory

logger = logging.getLogger(__name__)


async def factory_scheduler_loop():
    """Persisted status claims prevent overlapping workers processing one item.

    No automatic recovery of interrupted uploads: reconcile with YouTube first.
    """
    while True:
        try:
            if settings.FACTORY_ENABLED and not settings.EMERGENCY_STOP:
                async with AsyncSessionLocal() as db:
                    factory = OriginalContentFactory(db)
                    await factory.discover()
                    await factory.process_next()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Never log request bodies, auth headers or generated provider errors.
            logger.warning("Factory cycle failed (%s)", type(exc).__name__)
        await asyncio.sleep(settings.FACTORY_INTERVAL_SECONDS)
