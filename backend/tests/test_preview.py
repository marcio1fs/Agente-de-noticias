import json
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import settings
from app.db.session import Base, get_db
from app.main import app
from app.models.entities import ContentProject
from app.modules.video.preview import cached_video, fingerprint_for, render_paths, render_preview
from app.modules.video.pipeline import VideoProductionPipeline
from app.modules.publishing.dispatcher import PublishingDispatcher
from app.models.entities import PublishingAccount


@pytest_asyncio.fixture
async def preview_api(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "VIDEO_DIR", str(tmp_path))
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with maker() as session:
        project = ContentProject(id="preview-test", headline="Chuva na Bahia", editorial_summary="Resumo", script_short_vertical="Chuva", script_youtube_long="Chuva longa", requires_human_approval=True)
        session.add(project)
        await session.commit()
        async def override():
            yield session
        app.dependency_overrides[get_db] = override
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                yield client, project
        finally:
            app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


@pytest.mark.asyncio
async def test_unrendered_preview_and_missing_project(preview_api):
    client, project = preview_api
    response = await client.get(f"/api/v1/content-projects/{project.id}/preview")
    assert response.status_code == 200
    assert response.json()["headline"] == project.headline
    assert response.json()["ready"] is False
    assert response.json()["video_url"] is None
    assert (await client.get(f"/api/v1/content-projects/{project.id}/preview/video")).status_code == 404
    assert (await client.get("/api/v1/content-projects/unknown/preview")).status_code == 404


@pytest.mark.asyncio
async def test_render_preview_upload_reuses_file_and_range(preview_api, monkeypatch):
    client, project = preview_api
    renders = []
    def render(self, project_id, **kwargs):
        renders.append(kwargs)
        video, _ = render_paths(project_id, kwargs["is_vertical"])
        video.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"x" * 60000)
        return {"file_path": str(video)}
    monkeypatch.setattr(VideoProductionPipeline, "render_mock_or_ffmpeg", render)
    response = await client.post(f"/api/v1/actions/render-video/{project.id}?is_vertical=true")
    assert response.status_code == 200
    preview = (await client.get(f"/api/v1/content-projects/{project.id}/preview")).json()
    assert preview["ready"] is True
    video = await client.get(preview["video_url"], headers={"Range": "bytes=0-31"})
    assert video.status_code == 206
    assert len(video.content) == 32
    assert video.headers["content-type"] == "video/mp4"
    assert video.headers["cache-control"] == "no-store"
    uploaded_path = PublishingDispatcher(PublishingAccount())._find_or_create_video(project)
    assert uploaded_path == str(cached_video(project))
    assert len(renders) == 1
    horizontal = (await client.get(f"/api/v1/content-projects/{project.id}/preview?is_vertical=false")).json()
    assert horizontal["ready"] is False
    project.headline = "Manchete editada"
    assert cached_video(project) is None
    assert (await client.get(preview["video_url"])).status_code == 404


@pytest.mark.asyncio
async def test_render_failure_does_not_offer_preview(preview_api, monkeypatch):
    client, project = preview_api
    def fail(*args, **kwargs):
        raise RuntimeError("FFmpeg não instalado")
    monkeypatch.setattr(VideoProductionPipeline, "render_mock_or_ffmpeg", fail)
    response = await client.post(f"/api/v1/actions/render-video/{project.id}?is_vertical=true")
    assert response.status_code == 503
    assert "FFmpeg" in response.json()["detail"]
    assert cached_video(project) is None


@pytest.mark.parametrize("project_id", ["../../secret", "a/b", "a\\b", "", "."])
def test_path_injection_rejected(project_id):
    with pytest.raises(ValueError):
        render_paths(project_id, True)
