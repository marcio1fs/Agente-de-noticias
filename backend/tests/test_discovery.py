from datetime import datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.session import Base
from app.models.entities import NewsItem, RiskLevel, Source
from app.modules.discovery.engine import (
    NewsDiscoveryEngine, normalize_url, parse_feed, utcnow,
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def make_rss(n: int, prefix: str = "https://site.com/noticia", encoding: str = "utf-8") -> bytes:
    items = "".join(
        f"<item><title>Notícia número {i} sobre economia</title>"
        f"<link>{prefix}-{i}?utm_source=rss</link>"
        f"<description>&lt;p&gt;Resumo {i} com acentuação&lt;/p&gt;</description>"
        f"<pubDate>Sat, 10 Oct 2026 12:{i % 60:02d}:00 GMT</pubDate></item>"
        for i in range(n)
    )
    xml = f'<?xml version="1.0" encoding="{encoding}"?><rss version="2.0"><channel><title>T</title>{items}</channel></rss>'
    return xml.encode(encoding)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with maker() as session:
        yield session
    await engine.dispose()


async def count_items(db) -> int:
    return (await db.execute(select(func.count(NewsItem.id)))).scalar()


# --- Utilitários puros ------------------------------------------------------

def test_normalize_url_removes_tracking_fragment_and_trailing_slash():
    assert normalize_url("HTTPS://Site.com/a/b/?utm_source=x&id=7&fbclid=abc#topo") == "https://site.com/a/b?id=7"
    assert normalize_url("https://site.com/") == "https://site.com/"


@pytest.mark.parametrize("title,expected", [
    ("Manifestações pacíficas reúnem milhares", RiskLevel.LOW),   # antes: MEDIUM por 'ações'
    ("Doações de sangue crescem", RiskLevel.LOW),
    ("Polícia investiga homicidio na zona sul", RiskLevel.HIGH),  # sem acento
    ("Ibovespa fecha em alta", RiskLevel.MEDIUM),
    ("Ações da Petrobras sobem", RiskLevel.MEDIUM),
])
def test_risk_classification_uses_whole_words_without_accents(title, expected):
    assert NewsDiscoveryEngine.classify_initial_risk(title, "") == expected


def test_parse_feed_reads_all_entries_real_dates_and_encoding():
    items, malformed = parse_feed(make_rss(120, encoding="iso-8859-1"), max_items=150)
    assert not malformed
    assert len(items) == 120  # antes: cortado em 20
    first = items[0]
    assert first["title"] == "Notícia número 0 sobre economia"
    assert first["summary"] == "Resumo 0 com acentuação"  # HTML limpo
    assert first["url"] == "https://site.com/noticia-0"   # utm removido
    assert first["published_date"] == datetime(2026, 10, 10, 12, 0, 0)  # data real do feed


def test_parse_feed_respects_max_items():
    items, _ = parse_feed(make_rss(50), max_items=10)
    assert len(items) == 10


# --- Ingestão ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_dedups_normalized_urls_within_batch_and_against_db(db):
    src = Source(id="s1", name="S1", feed_url="https://s1/feed")
    db.add(src)
    await db.commit()
    engine = NewsDiscoveryEngine(db)

    batch = [
        {"title": "Fato A", "url": "https://s.com/a?utm_medium=x", "summary": "x"},
        {"title": "Fato A (cópia)", "url": "https://s.com/a#comentarios", "summary": "y"},
        {"title": "Fato B", "url": "https://s.com/b", "summary": "z"},
    ]
    assert await engine.ingest_items(src, batch) == 2
    assert await engine.ingest_items(src, batch) == 0
    assert await count_items(db) == 2


@pytest.mark.asyncio
async def test_persist_items_falls_back_per_item_on_unique_conflict(db):
    src = Source(id="s1", name="S1", feed_url="https://s1/feed")
    db.add_all([src, NewsItem(source_id="s1", title="Existente", url="https://s.com/dup")])
    await db.commit()
    engine = NewsDiscoveryEngine(db)

    new = [
        NewsItem(source_id="s1", title="Nova 1", url="https://s.com/n1"),
        NewsItem(source_id="s1", title="Duplicada", url="https://s.com/dup"),  # viola UNIQUE(url)
        NewsItem(source_id="s1", title="Nova 2", url="https://s.com/n2"),
    ]
    assert await engine._persist_items(new, "S1") == 2
    await db.commit()
    assert await count_items(db) == 3


# --- Ciclo completo com HTTP simulado ---------------------------------------

@pytest.mark.asyncio
async def test_cycle_uses_conditional_get_and_isolates_failing_sources(db):
    calls = {"ok": 0, "bad": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "ok.com":
            calls["ok"] += 1
            if request.headers.get("if-none-match") == '"v1"':
                return httpx.Response(304)
            return httpx.Response(200, content=make_rss(30, prefix="https://ok.com/n"), headers={"ETag": '"v1"'})
        calls["bad"] += 1
        return httpx.Response(500)

    ok = Source(id="ok", name="OK", feed_url="https://ok.com/feed", check_interval_minutes=10)
    bad = Source(id="bad", name="BAD", feed_url="https://bad.com/feed", check_interval_minutes=10)
    db.add_all([ok, bad])
    await db.commit()

    engine = NewsDiscoveryEngine(db)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        first = await engine.run_discovery_cycle([ok, bad], client=client)
        second = await engine.run_discovery_cycle([ok, bad], client=client)

    # 1º ciclo: fonte boa ingere tudo, fonte ruim não derruba o ciclo
    assert first["new_items_count"] == 30
    assert first["sources_failed"] == 1
    assert ok.etag == '"v1"' and ok.error_count == 0 and ok.last_items_found == 30

    # 2º ciclo: 304 Not Modified, nada baixado/reprocessado
    assert second["sources_not_modified"] == 1
    assert second["new_items_count"] == 0
    assert await count_items(db) == 30

    # Falhas persistidas com backoff exponencial (2^2 = 4x o intervalo)
    assert bad.error_count == 2
    assert bad.last_error == "HTTP 500"
    assert bad.last_status_code == 500
    delta = bad.next_check_at - bad.last_checked_at
    assert delta == timedelta(minutes=40)
    assert ok.next_check_at - ok.last_checked_at == timedelta(minutes=10)


@pytest.mark.asyncio
async def test_cycle_handles_network_errors_without_raising(db):
    def handler(request):
        raise httpx.ConnectTimeout("timeout", request=request)

    src = Source(id="t", name="Timeout", feed_url="https://slow.com/feed")
    db.add(src)
    await db.commit()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        report = await NewsDiscoveryEngine(db).run_discovery_cycle([src], client=client)

    assert report["sources_failed"] == 1
    assert src.error_count == 1
    assert "ConnectTimeout" in src.last_error
    assert src.next_check_at > utcnow()
