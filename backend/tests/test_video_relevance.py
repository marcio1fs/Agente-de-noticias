import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import settings
from app.modules.video.stock_provider import SafeStockVideoProvider
from app.modules.publishing.dispatcher import PublishingDispatcher
from app.models.entities import PublishingAccount, PublishingJob, ContentProject, ProcessingStatus


@pytest.fixture
def provider(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "PIXABAY_API_KEY", "test")
    monkeypatch.setattr(settings, "PEXELS_API_KEY", "test")
    return SafeStockVideoProvider()


@pytest.mark.asyncio
@pytest.mark.parametrize("headline,expected", [
    ("Chuvas fortes atingem Bahia", ["rain storm"]),
    ("Queimadas avançam pela floresta", ["wildfire forest fire"]),
    ("Copom mantém taxa Selic", ["interest rate inflation"]),
    ("Campanha de vacinação começa amanhã", ["vaccination injection"]),
    ("STF inicia julgamento", ["courtroom justice"]),
    ("Time de futebol vence campeonato", ["soccer football"]),
    ("Novidade sem tema reconhecido", []),
    ("Chuva e incêndio atingem região", []),
])
async def test_specific_search_terms(provider, headline, expected):
    assert await provider.extract_broll_search_terms(headline) == expected


@pytest.mark.asyncio
async def test_headline_priority(provider):
    assert await provider.extract_broll_search_terms(
        "Copom mantém juros", "Polícia controla trânsito próximo à reunião"
    ) == ["interest rate inflation"]


@pytest.mark.parametrize("query,metadata,accepted", [
    ("rain storm", "rain storm weather", True),
    ("rain storm", "wildfire forest fire", False),
    ("rain storm", "rain wildfire fire", False),
    ("interest rate inflation", "business office meeting", False),
    ("soccer football", "running athlete training", False),
    ("courtroom justice", "", False),
])
def test_metadata_filter(provider, query, metadata, accepted):
    assert (provider._score(query, metadata) > 0) is accepted


@pytest.mark.asyncio
async def test_unknown_topic_never_queries_providers(provider, monkeypatch):
    px = AsyncMock()
    pe = AsyncMock()
    monkeypatch.setattr(provider, "fetch_pixabay_video", px)
    monkeypatch.setattr(provider, "fetch_pexels_video", pe)
    assert await provider._search_relevant_video("Tema desconhecido", None, False) is None
    px.assert_not_awaited()
    pe.assert_not_awaited()


def test_sync_adapter_without_event_loop(provider, monkeypatch):
    monkeypatch.setattr(provider, "_search_relevant_video", AsyncMock(return_value="video.mp4"))
    assert provider.get_public_domain_broll("Chuva") == "video.mp4"


@pytest.mark.asyncio
async def test_sync_adapter_does_not_block_event_loop(provider, monkeypatch):
    search = AsyncMock()
    monkeypatch.setattr(provider, "_search_relevant_video", search)
    assert provider.get_public_domain_broll("Chuva") is None
    search.assert_not_awaited()


@pytest.mark.asyncio
async def test_pixabay_ranks_metadata_not_first_hit(provider, monkeypatch):
    hits = [
        {"tags": "wildfire forest", "videos": {"medium": {"width": 1280, "height": 720, "url": "https://cdn.pixabay.com/wrong.mp4"}}},
        {"tags": "rain storm", "videos": {"medium": {"width": 1280, "height": 720, "url": "https://cdn.pixabay.com/right.mp4"}}},
    ]
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"hits": hits}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=transport, **kwargs))
    download = AsyncMock(return_value="right.mp4")
    monkeypatch.setattr(provider, "_download", download)
    assert await provider.fetch_pixabay_video("rain storm") == "right.mp4"
    assert download.await_args.args[1] == "https://cdn.pixabay.com/right.mp4"
    download.reset_mock()
    assert await provider.fetch_pixabay_video("rain storm", is_vertical=True) is None
    download.assert_not_awaited()


@pytest.mark.asyncio
async def test_download_rejects_html_and_does_not_cache(provider):
    transport = httpx.MockTransport(lambda req: httpx.Response(200, headers={"content-type": "text/html"}, content=b"x" * 60000))
    async with httpx.AsyncClient(transport=transport) as client:
        assert await provider._download(client, "https://cdn.pixabay.com/a.mp4", "pixabay", "rain storm") is None
    from pathlib import Path
    assert not list(Path(provider.cache_dir).iterdir())


@pytest.mark.asyncio
async def test_download_atomic_cache(provider):
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(200, headers={"content-type": "video/mp4"}, content=b"\x00\x00\x00\x18ftypisom" + b"x" * 60000)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        path = await provider._download(client, "https://cdn.pixabay.com/a.mp4", "pixabay", "rain storm")
        assert path
        assert await provider._download(client, "https://cdn.pixabay.com/a.mp4", "pixabay", "rain storm") == path
    assert len(calls) == 1
    from pathlib import Path
    assert json.loads(Path(path + ".json").read_text())["illustrative"] is True
    assert not list(Path(provider.cache_dir).glob("*.part"))


@pytest.mark.parametrize("url", ["http://cdn.pixabay.com/a.mp4", "https://pixabay.com.evil.test/a.mp4", "https://127.0.0.1/a.mp4", "file:///etc/passwd"])
def test_download_host_allowlist(provider, url):
    assert not provider._safe_url(url, "pixabay")


@pytest.mark.asyncio
async def test_unimplemented_platform_not_reported_as_published(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_MODE", "AUTONOMOUS")
    monkeypatch.setattr(settings, "EMERGENCY_STOP", False)
    account = PublishingAccount(platform="INSTAGRAM", account_name="test", is_paused=False,
                                posts_today=0, daily_post_limit=5, encrypted_credentials="")
    job = PublishingJob(id="job", status=ProcessingStatus.READY_TO_PUBLISH)
    db = AsyncMock()
    from app.models.entities import NewsItem
    db.get.return_value = NewsItem(url="https://example.com/news")
    result = await PublishingDispatcher(account, db=db).publish(job, ContentProject(news_item_id="news"))
    assert result["reason"] == "PUBLISHER_NOT_CONFIGURED"
    assert result["success"] is False
    assert job.status == ProcessingStatus.FAILED
    assert account.posts_today == 0


@pytest.mark.asyncio
async def test_published_job_does_not_publish_twice(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_MODE", "SIMULATION")
    account = PublishingAccount(posts_today=1)
    job = PublishingJob(id="job", status=ProcessingStatus.PUBLISHED, platform_post_id="already")
    result = await PublishingDispatcher(account).publish(job, ContentProject())
    assert result["already_published"] is True
    assert account.posts_today == 1

@pytest.mark.asyncio
async def test_unknown_headline_does_not_use_secondary_script_topic(provider):
    assert await provider.extract_broll_search_terms("Novo anúncio confirmado", "O trânsito perto do local está normal") == []
    assert await provider.extract_broll_search_terms("Bolsa de estudos para alunos") == ["school classroom"]


def test_missing_ffmpeg_is_failure(tmp_path, monkeypatch):
    from app.modules.video.pipeline import VideoProductionPipeline
    monkeypatch.setattr(settings, "VIDEO_DIR", str(tmp_path / "video"))
    monkeypatch.setattr(settings, "AUDIO_DIR", str(tmp_path / "audio"))
    monkeypatch.setattr(settings, "MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.setattr(VideoProductionPipeline, "is_ffmpeg_installed", lambda self: False)
    with pytest.raises(RuntimeError, match="FFmpeg"):
        VideoProductionPipeline().render_mock_or_ffmpeg("test", headline="Chuva")


def test_legacy_render_not_reused(tmp_path, monkeypatch):
    from app.modules.video.pipeline import VideoProductionPipeline
    monkeypatch.setattr(settings, "VIDEO_DIR", str(tmp_path))
    legacy = tmp_path / "video_project_vertical_9_16.mp4"
    legacy.write_bytes(b"x" * 60000)
    def failed_render(*args, **kwargs):
        raise RuntimeError("render failed")
    monkeypatch.setattr(VideoProductionPipeline, "render_mock_or_ffmpeg", failed_render)
    with pytest.raises(RuntimeError, match="render failed"):
        PublishingDispatcher(PublishingAccount())._find_or_create_video(
            ContentProject(id="project", headline="Chuva")
        )
