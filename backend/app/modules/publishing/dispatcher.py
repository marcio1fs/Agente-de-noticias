import os
import asyncio
from datetime import datetime
from typing import Dict, Any
from app.core.config import settings
from app.core.security import decrypt_secret
from app.models.entities import PublishingAccount, PublishingJob, ContentProject, ProcessingStatus
from app.modules.publishing.youtube import YouTubePublisher
from app.modules.video.preview import render_preview
from app.modules.publishing.attribution import project_source_url, youtube_description

class PublishingDispatcher:
    def __init__(self, account: PublishingAccount, db=None, is_vertical: bool = True, factory_authorized: bool = False):
        self.account = account
        self.db = db
        self.is_vertical = is_vertical
        self.factory_authorized = factory_authorized

    def get_decrypted_token(self) -> str:
        """Descriptografa com segurança os tokens da plataforma em memória."""
        return decrypt_secret(self.account.encrypted_credentials)

    def _find_or_create_video(self, project: ContentProject) -> str:
        """Localiza arquivo de vídeo renderizado para o projeto ou gera com o pipeline FFmpeg."""
        return render_preview(project, is_vertical=self.is_vertical)


    async def publish(self, job: PublishingJob, project: ContentProject) -> Dict[str, Any]:
        """
        Executa publicação respeitando:
        1. Modo de simulação vs modo autônomo.
        2. Botão de emergência global.
        3. Conta pausada.
        4. Limite diário de publicações.
        """
        factory = isinstance(project.social_captions, dict) and project.social_captions.get("_factory") is True
        if factory and not self.factory_authorized:
            job.status = ProcessingStatus.BLOCKED
            return {"success": False, "reason": "FACTORY_REVIEW_REQUIRED", "error": "Use o fluxo protegido de aprovação/publicação da fábrica."}

        if job.status == ProcessingStatus.PUBLISHED:
            return {"success": True, "post_id": job.platform_post_id, "url": job.post_url, "already_published": True}

        # Checagem de Botão de Pânico
        if settings.EMERGENCY_STOP:
            job.status = ProcessingStatus.CANCELLED
            job.error_message = "Publicação cancelada pelo Botão de Emergência Global."
            return {"success": False, "reason": "EMERGENCY_STOP_ACTIVE"}

        # Checagem de Conta Pausada
        if self.account.is_paused:
            job.status = ProcessingStatus.BLOCKED
            job.error_message = f"Conta {self.account.account_name} está pausada pelo administrador."
            return {"success": False, "reason": "ACCOUNT_PAUSED"}

        # Checagem de Quota Diária
        if self.account.posts_today >= self.account.daily_post_limit:
            job.status = ProcessingStatus.BLOCKED
            job.error_message = f"Limite diário de {self.account.daily_post_limit} publicações atingido."
            return {"success": False, "reason": "DAILY_LIMIT_REACHED"}

        source_url = await project_source_url(project, self.db)
        if not source_url:
            job.status = ProcessingStatus.FAILED
            job.error_message = "Publicação bloqueada: notícia original sem link de fonte válido."
            return {"success": False, "reason": "SOURCE_URL_MISSING", "error": job.error_message}
        description = youtube_description(project, source_url)

        # Identificador único seguro para o job
        job_key = (job.id[:8] if job.id else getattr(job, "idempotency_key", "job")[:8])

        # Modo de Simulação
        if settings.AGENT_MODE == "SIMULATION":
            job.status = ProcessingStatus.PUBLISHED
            job.platform_post_id = f"sim_{job_key}"
            job.post_url = f"https://simulation.local/{self.account.platform.lower()}/{job.platform_post_id}"
            job.published_at = datetime.utcnow()
            self.account.posts_today += 1
            return {
                "success": True,
                "mode": "SIMULATION",
                "source_url": source_url,
                "description": description,
                "post_id": job.platform_post_id,
                "url": job.post_url
            }

        # No modo REAL (AUTONOMOUS / ASSISTED)
        token = self.get_decrypted_token()

        # Publicação Real no YouTube se for a plataforma YOUTUBE e tiver tokens OAuth válidos
        if self.account.platform == "YOUTUBE" and settings.YOUTUBE_CLIENT_ID and settings.YOUTUBE_CLIENT_SECRET:
            try:
                # Prepara título e descrição
                title = project.headline or "Notícia Verificada"
                desc = description

                video_file = await asyncio.to_thread(self._find_or_create_video, project)
                # Rendering can take minutes; recheck safety before network upload.
                if settings.EMERGENCY_STOP or self.account.is_paused:
                    job.status = ProcessingStatus.CANCELLED
                    return {"success": False, "reason": "PUBLICATION_STOPPED_AFTER_RENDER"}

                yt_client = YouTubePublisher(
                    client_id=settings.YOUTUBE_CLIENT_ID,
                    client_secret=settings.YOUTUBE_CLIENT_SECRET,
                    credentials_json=token
                )

                upload_options = {"category_id": "27", "tags": ["ciencia", "curiosidades", "conteudooriginal"]} if factory else {}
                upload_res = await yt_client.upload_video(
                    video_path=video_file,
                    title=title,
                    description=desc,
                    privacy_status=settings.FACTORY_YOUTUBE_PRIVACY if factory else "public", **upload_options
                )

                if upload_res.get("success"):
                    job.status = ProcessingStatus.PUBLISHED
                    job.platform_post_id = upload_res["video_id"]
                    job.post_url = upload_res["url"]
                    job.published_at = datetime.utcnow()
                    self.account.posts_today += 1
                    return {
                        "success": True,
                        "mode": "PRODUCTION",
                        "source_url": source_url,
                        "post_id": job.platform_post_id,
                        "url": job.post_url
                    }
                else:
                    job.status = ProcessingStatus.FAILED
                    job.error_message = upload_res.get("error", "Falha no upload do YouTube.")
                    return {
                        "success": False,
                        "error": job.error_message
                    }

            except Exception as e:
                job.status = ProcessingStatus.FAILED
                job.error_message = str(e)
                return {"success": False, "error": str(e)}

        job.status = ProcessingStatus.FAILED
        job.error_message = "Plataforma não implementada ou credenciais de publicação ausentes."
        return {"success": False, "reason": "PUBLISHER_NOT_CONFIGURED", "error": job.error_message}
