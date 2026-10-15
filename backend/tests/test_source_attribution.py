from unittest.mock import AsyncMock, Mock

import pytest

from app.core.config import settings
from app.models.entities import ContentProject, NewsItem, PublishingAccount, PublishingJob, ProcessingStatus
from app.modules.publishing.attribution import validated_source_url, with_source, youtube_description
from app.modules.publishing.dispatcher import PublishingDispatcher
from app.modules.publishing.youtube import YouTubePublisher
from app.modules.content.engine import ContentProductionEngine


SOURCE = "https://jornal.example/noticias/materia-original?ref=rss"


@pytest.mark.parametrize("url", [None, "", "javascript:alert(1)", "file:///tmp/news", "https://", "https://user:secret@example.com", "https://example.com/\nforged", "https://example.com:bad/news"])
def test_invalid_source(url):
    assert validated_source_url(url) is None


def test_source_survives_description_truncation():
    project = ContentProject(editorial_summary="x" * 10000, social_captions={"youtube": "IA não citou a fonte"})
    description = youtube_description(project, SOURCE)
    assert description.startswith(f"Fonte da notícia original: {SOURCE}\n")
    assert len(description) == 5000
    assert with_source("texto", SOURCE, 280).startswith("Fonte da notícia original:")


def account():
    return PublishingAccount(platform="YOUTUBE", account_name="test", posts_today=0,
                             daily_post_limit=10, is_paused=False, encrypted_credentials="")


@pytest.mark.asyncio
async def test_real_upload_includes_original_database_source(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_MODE", "ASSISTED")
    monkeypatch.setattr(settings, "EMERGENCY_STOP", False)
    monkeypatch.setattr(settings, "YOUTUBE_CLIENT_ID", "test")
    monkeypatch.setattr(settings, "YOUTUBE_CLIENT_SECRET", "test")
    db = AsyncMock()
    db.get.return_value = NewsItem(url=SOURCE)
    project = ContentProject(id="project", news_item_id="news", headline="Manchete", editorial_summary="Resumo", social_captions={})
    dispatcher = PublishingDispatcher(account(), db=db)
    monkeypatch.setattr(dispatcher, "_find_or_create_video", lambda _: "video.mp4")
    upload = AsyncMock(return_value={"success": True, "video_id": "yt1", "url": "https://youtube.com/watch?v=yt1"})
    monkeypatch.setattr(YouTubePublisher, "upload_video", upload)
    result = await dispatcher.publish(PublishingJob(id="job", status=ProcessingStatus.READY_TO_PUBLISH), project)
    assert result["success"] is True
    assert result["source_url"] == SOURCE
    assert upload.await_args.kwargs["description"].startswith(f"Fonte da notícia original: {SOURCE}")
    db.get.assert_awaited_once_with(NewsItem, "news")


@pytest.mark.asyncio
async def test_simulation_reports_source_and_description_without_upload(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_MODE", "SIMULATION")
    monkeypatch.setattr(settings, "EMERGENCY_STOP", False)
    db = AsyncMock()
    db.get.return_value = NewsItem(url=SOURCE)
    upload = AsyncMock()
    monkeypatch.setattr(YouTubePublisher, "upload_video", upload)
    project = ContentProject(news_item_id="news", editorial_summary="Resumo")
    result = await PublishingDispatcher(account(), db=db).publish(PublishingJob(id="job"), project)
    assert result["success"] is True
    assert result["source_url"] == SOURCE
    assert SOURCE in result["description"]
    upload.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_source_blocks_publication(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_MODE", "AUTONOMOUS")
    monkeypatch.setattr(settings, "EMERGENCY_STOP", False)
    db = AsyncMock()
    db.get.return_value = None
    acc = account()
    job = PublishingJob(id="job")
    result = await PublishingDispatcher(acc, db=db).publish(job, ContentProject(news_item_id="missing"))
    assert result["reason"] == "SOURCE_URL_MISSING"
    assert job.status == ProcessingStatus.FAILED
    assert acc.posts_today == 0


@pytest.mark.asyncio
async def test_ai_captions_receive_source_even_when_model_omits_it(monkeypatch):
    db = AsyncMock()
    db.add = Mock()
    producer = ContentProductionEngine(db)
    monkeypatch.setattr(producer, "_call_gemini_api", AsyncMock(return_value={
        "headline": "Manchete", "editorial_summary": "Resumo", "social_captions": {"youtube": "Legenda da IA"},
    }))
    project = await producer.produce_content(NewsItem(id="news", title="Manchete", url=SOURCE))
    for platform in ("youtube", "instagram", "twitter"):
        assert SOURCE in project.social_captions[platform]
