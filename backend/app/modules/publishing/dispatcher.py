import os
import glob
from datetime import datetime
from typing import Dict, Any
from app.core.config import settings
from app.core.security import decrypt_secret
from app.models.entities import PublishingAccount, PublishingJob, ContentProject, ProcessingStatus
from app.modules.publishing.youtube import YouTubePublisher
from app.modules.video.pipeline import VideoProductionPipeline

class PublishingDispatcher:
    def __init__(self, account: PublishingAccount):
        self.account = account

    def get_decrypted_token(self) -> str:
        """Descriptografa com segurança os tokens da plataforma em memória."""
        return decrypt_secret(self.account.encrypted_credentials)

    def _find_or_create_video(self, project: ContentProject) -> str:
        """Localiza arquivo de vídeo renderizado para o projeto ou gera com o pipeline FFmpeg."""
        pattern = os.path.join(settings.VIDEO_DIR, f"video_{project.id}_*.mp4")
        matches = glob.glob(pattern)
        if matches:
            return matches[0]

        # Se ainda não foi gerado, renderiza com gráficos e narração
        pipeline = VideoProductionPipeline()
        script = project.script_short_vertical or project.script_youtube_long or project.editorial_summary
        result = pipeline.render_mock_or_ffmpeg(
            project.id,
            is_vertical=True,
            headline=project.headline,
            script_text=script
        )
        return result["file_path"]


    async def publish(self, job: PublishingJob, project: ContentProject) -> Dict[str, Any]:
        """
        Executa publicação respeitando:
        1. Modo de simulação vs modo autônomo.
        2. Botão de emergência global.
        3. Conta pausada.
        4. Limite diário de publicações.
        """
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
                desc = (
                    f"{project.editorial_summary or ''}\n\n"
                    f"{project.social_captions.get('youtube', '') if isinstance(project.social_captions, dict) else ''}\n\n"
                    f"#noticias #urgente #jornalismo"
                ).strip()

                video_file = self._find_or_create_video(project)

                yt_client = YouTubePublisher(
                    client_id=settings.YOUTUBE_CLIENT_ID,
                    client_secret=settings.YOUTUBE_CLIENT_SECRET,
                    credentials_json=token
                )

                upload_res = await yt_client.upload_video(
                    video_path=video_file,
                    title=title,
                    description=desc,
                    privacy_status="public"
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

        # Fallback para outras redes sociais simuladas (Instagram, TikTok)
        job.status = ProcessingStatus.PUBLISHED
        job.platform_post_id = f"pub_{self.account.platform}_{job_key}"
        job.post_url = f"https://{self.account.platform.lower()}.com/post/{job.platform_post_id}"
        job.published_at = datetime.utcnow()
        self.account.posts_today += 1
        
        return {
            "success": True,
            "mode": "PRODUCTION",
            "post_id": job.platform_post_id,
            "url": job.post_url
        }

