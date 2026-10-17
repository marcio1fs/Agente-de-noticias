"""Shared validated render cache: preview and upload use the same artifact."""
import hashlib
import json
import os
import tempfile
import threading
from weakref import WeakValueDictionary
from pathlib import Path

from app.core.config import settings
from app.models.entities import ContentProject
from app.modules.video.pipeline import VideoProductionPipeline


def render_paths(project_id: str, is_vertical: bool):
    # Project identifiers are database values, but must never become paths.
    if not project_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in project_id):
        raise ValueError("Identificador de projeto inválido")
    root = Path(settings.VIDEO_DIR).resolve()
    aspect = "vertical_9_16" if is_vertical else "horizontal_16_9"
    video = root / f"video_{project_id}_{aspect}.mp4"
    manifest = root / (f"validated_{project_id}.json" if is_vertical else f"validated_{project_id}_horizontal.json")
    return video, manifest


def script_for(project: ContentProject, is_vertical: bool):
    return ((project.script_short_vertical if is_vertical else project.script_youtube_long)
            or project.editorial_summary or project.headline)


def fingerprint_for(project: ContentProject, is_vertical: bool):
    return hashlib.sha256(json.dumps(
        [("factory_v1_owned_media" if isinstance(project.social_captions, dict) and project.social_captions.get("_factory") else "relevance_v4_speech_numeric_por"), project.headline, script_for(project, is_vertical),
         "vertical" if is_vertical else "horizontal"], ensure_ascii=False
    ).encode()).hexdigest()


def cached_video(project: ContentProject, is_vertical: bool = True):
    video, manifest = render_paths(project.id, is_vertical)
    try:
        cached = json.loads(manifest.read_text())
        if (cached.get("fingerprint") == fingerprint_for(project, is_vertical)
                and video.is_file() and video.stat().st_size > 20000):
            return video
    except (OSError, ValueError):
        pass
    return None


_render_locks = WeakValueDictionary()
_lock_guard = threading.Lock()


def render_preview(project: ContentProject, is_vertical: bool = True):
    # API and publisher may request the same preview concurrently. Serialize
    # within this process so they cannot overwrite an in-progress artifact.
    key = (project.id, is_vertical)
    with _lock_guard:
        lock = _render_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _render_locks[key] = lock
    with lock:
        return _render_preview(project, is_vertical)


def _render_preview(project: ContentProject, is_vertical: bool):
    existing = cached_video(project, is_vertical)
    if existing:
        return str(existing)
    video, manifest = render_paths(project.id, is_vertical)
    # Invalidate the old marker before overwriting the media.
    manifest.unlink(missing_ok=True)
    factory = isinstance(project.social_captions, dict) and project.social_captions.get("_factory") is True
    options = {"original_content": True} if factory else {}
    result = VideoProductionPipeline().render_mock_or_ffmpeg(
        project.id, is_vertical=is_vertical, headline=project.headline,
        script_text=script_for(project, is_vertical), **options,
    )
    if Path(result["file_path"]).resolve() != video or not video.is_file() or video.stat().st_size <= 20000:
        raise RuntimeError("Renderização não gerou vídeo válido; upload bloqueado.")
    # Publish the cache marker atomically, only once rendering has succeeded.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=manifest.parent, delete=False) as output:
        temp = output.name
        json.dump({"fingerprint": fingerprint_for(project, is_vertical)}, output)
    try:
        os.replace(temp, manifest)
    finally:
        if os.path.exists(temp):
            os.remove(temp)
    return str(video)
