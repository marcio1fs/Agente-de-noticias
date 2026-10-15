import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.db.session import Base
from app.models.entities import Source, NewsItem, RiskLevel, ProcessingStatus
from app.modules.verification.engine import (
    FactVerificationEngine, calculate_title_similarity, extract_significant_tokens
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session_maker() as session:
        yield session
    await engine.dispose()

def test_extract_significant_tokens_removes_stopwords():
    tokens = extract_significant_tokens("Dólar sobe após decisão do Banco Central sobre a taxa Selic")
    assert "sobre" not in tokens
    assert "apos" not in tokens
    assert "dolar" in tokens
    assert "banco" in tokens
    assert "selic" in tokens

def test_similarity_calculation():
    sim_high = calculate_title_similarity(
        "Banco Central mantém taxa Selic em 10,50%",
        "Copom decide manter juros básicos da Selic em 10,50%"
    )
    sim_low = calculate_title_similarity(
        "Banco Central mantém taxa Selic",
        "Vasco vence clássico no Maracanã com gol nos acréscimos"
    )
    assert sim_high > 0.40
    assert sim_low < 0.15

@pytest.mark.asyncio
async def test_corroboration_across_independent_publishers(async_session):
    # Fonte 1: EBC
    src_ebc = Source(id="src_ebc", name="Agência Brasil", publisher="EBC", feed_url="https://ebc.com/feed", trust_weight=1.0)
    # Fonte 2: Globo
    src_globo = Source(id="src_globo", name="G1 Economia", publisher="Globo", feed_url="https://g1.com/feed", trust_weight=0.9)
    # Fonte 3: Folha
    src_folha = Source(id="src_folha", name="Folha Mercado", publisher="Folha", feed_url="https://folha.com/feed", trust_weight=0.9)
    
    async_session.add_all([src_ebc, src_globo, src_folha])
    await async_session.commit()

    verifier = FactVerificationEngine(async_session)

    # Item inicial publicado pela EBC
    item1 = NewsItem(
        id="item_1",
        source_id="src_ebc",
        title="Inflação oficial IPCA sobe 0,44% em setembro",
        url="https://ebc.com/1",
        risk_level=RiskLevel.LOW,
        published_date=datetime.utcnow()
    )
    async_session.add(item1)
    await async_session.commit()

    # 1ª verificação: notícia isolada
    res1 = await verifier.verify_news_item(item1)
    assert res1.verdict == "UNVERIFIED"
    assert res1.corroborating_sources_count == 0
    assert item1.status == ProcessingStatus.QUARANTINED

    # Agora o G1 publica sobre o mesmo fato
    item2 = NewsItem(
        id="item_2",
        source_id="src_globo",
        title="IPCA acelera e sobe 0,44% em setembro, revela IBGE",
        url="https://g1.com/2",
        risk_level=RiskLevel.LOW,
        published_date=datetime.utcnow()
    )
    async_session.add(item2)
    await async_session.commit()

    # Verifica item 2 e re-verifica o cluster
    res2 = await verifier.verify_news_item(item2)
    assert item2.cluster_id == item1.id or item2.cluster_id == item1.cluster_id
    assert res2.corroborating_sources_count == 1
    assert res2.verdict == "PARTIALLY_CONFIRMED"

    # Reavalia o item 1 (re-verificação automática do cluster)
    await verifier.reverify_cluster(item1.cluster_id)
    assert item1.status == ProcessingStatus.APPROVAL_REQUIRED

    # Agora a Folha também publica (3º veículo independente)
    item3 = NewsItem(
        id="item_3",
        source_id="src_folha",
        title="Inflação medida pelo IPCA fica em 0,44% em setembro",
        url="https://folha.com/3",
        risk_level=RiskLevel.LOW,
        published_date=datetime.utcnow()
    )
    async_session.add(item3)
    await async_session.commit()

    res3 = await verifier.verify_news_item(item3)
    assert res3.corroborating_sources_count >= 2
    assert res3.verdict == "CORROBORATED"
    assert item3.status == ProcessingStatus.READY_TO_PUBLISH

    # Re-verifica todo o cluster
    await verifier.reverify_cluster(item1.cluster_id)
    assert item1.status == ProcessingStatus.READY_TO_PUBLISH
