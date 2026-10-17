import os
import json
import logging
import urllib.parse
import httpx
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class YouTubePublisher:
    """Cliente oficial para upload e publicação de vídeos no YouTube via YouTube Data API v3."""

    TOKEN_URL = "https://oauth2.googleapis.com/token"
    UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"

    def __init__(self, client_id: str, client_secret: str, credentials_json: str):
        self.client_id = client_id
        self.client_secret = client_secret
        try:
            self.creds = json.loads(credentials_json) if isinstance(credentials_json, str) else credentials_json
        except Exception:
            self.creds = {}

    async def get_valid_access_token(self) -> Optional[str]:
        """Obtém um access token válido, renovando pelo refresh token se necessário."""
        refresh_token = self.creds.get("refresh_token")
        if not refresh_token:
            return self.creds.get("access_token")

        # Renova o token de acesso
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(self.TOKEN_URL, data=data)
                res_data = res.json()
                if res.status_code == 200 and "access_token" in res_data:
                    self.creds["access_token"] = res_data["access_token"]
                    return res_data["access_token"]
                else:
                    logger.error(f"[YouTubePublisher] Falha ao renovar token: {res_data}")
        except Exception as e:
            logger.error(f"[YouTubePublisher] Erro ao renovar token: {e}")

        return self.creds.get("access_token")

    async def upload_video(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: Optional[list] = None,
        privacy_status: str = "public",
        category_id: str = "25"
    ) -> Dict[str, Any]:
        """
        Faz upload de arquivo de vídeo para o canal do YouTube usando protocolo resumable.
        """
        if not os.path.exists(video_path):
            return {
                "success": False,
                "error": f"Arquivo de vídeo não encontrado em: {video_path}"
            }

        access_token = await self.get_valid_access_token()
        if not access_token:
            return {
                "success": False,
                "error": "Não foi possível obter Access Token válido para o YouTube."
            }

        file_size = os.path.getsize(video_path)
        if tags is None:
            tags = ["noticias", "jornalismo", "urgente"]

        # 1. Iniciar sessão de upload resumable
        metadata = {
            "snippet": {
                "title": title[:100],  # Limite de 100 caracteres do YouTube
                "description": description[:5000],
                "tags": tags,
                "categoryId": category_id  # Categoria 25: Notícias e Política (News & Politics)
            },
            "status": {
                "privacyStatus": privacy_status,  # public, unlisted ou private
                "selfDeclaredMadeForKids": False
            }
        }

        init_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(file_size)
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                init_resp = await client.post(
                    self.UPLOAD_URL,
                    headers=init_headers,
                    content=json.dumps(metadata)
                )

                if init_resp.status_code not in (200, 201):
                    logger.error(f"[YouTubePublisher] Erro ao iniciar upload: {init_resp.text}")
                    return {
                        "success": False,
                        "error": f"Erro na inicialização do upload: {init_resp.status_code} - {init_resp.text}"
                    }

                upload_session_url = init_resp.headers.get("Location")
                if not upload_session_url:
                    return {
                        "success": False,
                        "error": "URL de sessão de upload não retornada pelo YouTube."
                    }

                # 2. Enviar bytes do vídeo
                with open(video_path, "rb") as video_file:
                    video_bytes = video_file.read()

                upload_headers = {
                    "Content-Type": "video/mp4",
                    "Content-Length": str(file_size)
                }

                upload_resp = await client.put(
                    upload_session_url,
                    headers=upload_headers,
                    content=video_bytes,
                    timeout=180.0
                )

                if upload_resp.status_code in (200, 201):
                    uploaded_data = upload_resp.json()
                    video_id = uploaded_data.get("id")
                    if not video_id:
                        return {"success": False, "error": "YouTube respondeu sem ID de vídeo; reconcilie a tentativa no canal."}
                    watch_url = f"https://www.youtube.com/watch?v={video_id}"
                    logger.info(f"[YouTubePublisher] Vídeo publicado com sucesso! ID={video_id} - {watch_url}")
                    return {
                        "success": True,
                        "video_id": video_id,
                        "url": watch_url,
                        "response": uploaded_data
                    }
                else:
                    logger.error(f"[YouTubePublisher] Erro ao enviar chunks do vídeo: {upload_resp.text}")
                    return {
                        "success": False,
                        "error": f"Falha no envio do vídeo: {upload_resp.status_code} - {upload_resp.text}"
                    }

        except Exception as ex:
            logger.error(f"[YouTubePublisher] Exceção durante upload: {ex}")
            return {
                "success": False,
                "error": str(ex)
            }


    async def video_statistics(self, video_id: str) -> Dict[str, Any]:
        """Actual YouTube counters; absent fields remain absent (no invented data)."""
        import re
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", video_id):
            raise ValueError("ID de vídeo inválido")
        token = await self.get_valid_access_token()
        if not token:
            raise ValueError("Credencial YouTube indisponível")
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get("https://www.googleapis.com/youtube/v3/videos",
                params={"part": "statistics", "id": video_id}, headers={"Authorization": f"Bearer {token}"})
            response.raise_for_status()
            items = response.json().get("items", [])
            if not items:
                raise ValueError("Métricas ainda indisponíveis para o vídeo")
            return {key: int(value) for key, value in items[0].get("statistics", {}).items()
                    if key in ("viewCount", "likeCount", "commentCount")}

    async def set_thumbnail(self, video_id: str, thumbnail_path: str) -> bool:
        """Optional, requires a channel eligible for custom thumbnails."""
        token = await self.get_valid_access_token()
        if not token:
            return False
        async with httpx.AsyncClient(timeout=30.0) as client:
            with open(thumbnail_path, "rb") as image:
                response = await client.post("https://www.googleapis.com/upload/youtube/v3/thumbnails/set",
                    params={"videoId": video_id, "uploadType": "media"}, content=image.read(),
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg"})
            return response.status_code == 200
