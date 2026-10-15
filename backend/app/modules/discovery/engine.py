import asyncio
import calendar
import hashlib
import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import httpx
from bs4 import BeautifulSoup
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.entities import NewsItem, Source, ProcessingStatus, RiskLevel

logger = logging.getLogger(__name__)

# Regras e palavras-chave de risco para classificação inicial
SENSITIVE_KEYWORDS_HIGH = [
    "assassinato", "homicídio", "tráfico", "operação policial", "mandado de prisão",
    "facção criminosa", "corrupção", "estupro", "sequestro", "investigado pela pf", "lavagem de dinheiro"
]

SENSITIVE_KEYWORDS_MEDIUM = [
    "eleição", "candidato", "congresso", "stf", "ministro", "inflação",
    "banco central", "taxa selic", "ações", "ibovespa", "igreja", "pastor", "bispo", "vaticano"
]

USER_AGENT = "Mozilla/5.0 (compatible; AutonomousNewsAgent/1.1)"

# Parâmetros de rastreamento removidos na normalização de URLs
TRACKING_PARAMS = {"fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "_ga", "cmpid", "ocid"}


# ---------------------------------------------------------------------------
# Utilitários puros (sem I/O) — fáceis de testar
# ---------------------------------------------------------------------------

def utcnow() -> datetime:
    """UTC 'naive' (compatível com as colunas DateTime existentes)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_text(text: str) -> str:
    """Minúsculas, sem acentos e com espaços colapsados."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    no_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(no_accents.lower().split())


def _compile_keywords(keywords: List[str]) -> re.Pattern:
    alternatives = "|".join(re.escape(normalize_text(k)) for k in keywords)
    return re.compile(rf"\b(?:{alternatives})\b")


_HIGH_RISK_RE = _compile_keywords(SENSITIVE_KEYWORDS_HIGH)
_MEDIUM_RISK_RE = _compile_keywords(SENSITIVE_KEYWORDS_MEDIUM)


def normalize_url(url: str) -> str:
    """
    Normaliza URLs para deduplicação: remove fragmento, parâmetros de rastreamento
    (utm_*, fbclid...), barra final e padroniza esquema/host em minúsculas.
    """
    url = (url or "").strip()
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return url
    query = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
    ]
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query, doseq=True), ""))


def clean_html(value: str) -> str:
    if not value:
        return ""
    if "<" in value or "&" in value:
        value = BeautifulSoup(value, "html.parser").get_text(" ")
    return " ".join(value.split())


def parse_entry_date(entry: Any) -> Optional[datetime]:
    """Extrai a data real de publicação da entrada do feed (UTC naive)."""
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                dt = datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc).replace(tzinfo=None)
            except (OverflowError, ValueError, TypeError):
                continue
            # Datas no futuro (fuso errado no feed) são limitadas ao "agora"
            now = utcnow()
            return now if dt > now + timedelta(hours=1) else dt
    return None


def parse_feed(content: bytes, max_items: int) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Converte o corpo bruto do feed em itens. Recebe *bytes* para que o feedparser
    detecte o encoding corretamente. Retorna (itens, feed_malformado).
    """
    feed = feedparser.parse(content)
    malformed = bool(feed.get("bozo")) and not feed.entries
    items: List[Dict[str, Any]] = []
    for entry in feed.entries[:max_items]:
        link = (entry.get("link") or "").strip()
        guid = (entry.get("id") or "").strip()
        if not link and guid.startswith("http"):
            link = guid
        items.append({
            "title": clean_html(entry.get("title", "")),
            "url": normalize_url(link) if link else "",
            "summary": clean_html(entry.get("summary", "") or entry.get("description", "")),
            "published_date": parse_entry_date(entry) or utcnow(),
            "guid": guid or None,
        })
    return items, malformed


def build_http_client() -> httpx.AsyncClient:
    """Client HTTP compartilhado por ciclo de coleta (reuso de conexões/TLS)."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.DISCOVERY_TIMEOUT_SECONDS),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8"},
        limits=httpx.Limits(max_connections=settings.DISCOVERY_CONCURRENCY * 2, max_keepalive_connections=settings.DISCOVERY_CONCURRENCY),
    )


@dataclass
class FetchResult:
    items: List[Dict[str, Any]] = field(default_factory=list)
    status_code: Optional[int] = None
    not_modified: bool = False
    error: Optional[str] = None
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    elapsed_ms: int = 0


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class NewsDiscoveryEngine:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    @staticmethod
    def compute_content_hash(text: str) -> str:
        """Gera um hash SHA-256 para prevenir duplicação de notícias."""
        normalized = " ".join(text.lower().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def classify_initial_risk(title: str, text: str) -> RiskLevel:
        """Classificação por palavra inteira, sem acento (evita 'ações' casar com 'manifestações')."""
        combined = normalize_text(f"{title} {text}")
        if _HIGH_RISK_RE.search(combined):
            return RiskLevel.HIGH
        if _MEDIUM_RISK_RE.search(combined):
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    # --- Rede -------------------------------------------------------------

    async def fetch_feed(self, client: httpx.AsyncClient, source: Source) -> FetchResult:
        """
        Baixa um feed com GET condicional (ETag / Last-Modified). Nunca lança exceção:
        erros são devolvidos em FetchResult.error para serem registrados na fonte.
        """
        feed_url, etag, last_modified = source.feed_url, source.etag, source.last_modified
        headers = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        started = time.perf_counter()
        try:
            response = await client.get(feed_url, headers=headers)
            elapsed = int((time.perf_counter() - started) * 1000)

            if response.status_code == 304:
                return FetchResult(status_code=304, not_modified=True, etag=etag,
                                   last_modified=last_modified, elapsed_ms=elapsed)
            if response.status_code != 200:
                return FetchResult(status_code=response.status_code,
                                   error=f"HTTP {response.status_code}", elapsed_ms=elapsed)

            items, malformed = await asyncio.to_thread(
                parse_feed, response.content, settings.DISCOVERY_MAX_ITEMS_PER_FEED
            )
            return FetchResult(
                items=items,
                status_code=200,
                error="Feed inválido ou malformado" if malformed else None,
                etag=response.headers.get("etag"),
                last_modified=response.headers.get("last-modified"),
                elapsed_ms=elapsed,
            )
        except Exception as e:  # rede, timeout, parsing...
            return FetchResult(error=f"{type(e).__name__}: {e}"[:1000],
                               elapsed_ms=int((time.perf_counter() - started) * 1000))

    # --- Persistência -----------------------------------------------------

    async def ingest_items(self, source: Source, items: List[Dict[str, Any]]) -> int:
        """
        Salva notícias novas em lote, rejeitando duplicadas por URL normalizada ou hash
        de conteúdo — tanto contra o banco quanto dentro do próprio lote.
        Usa 1 consulta por lote em vez de 2 por item.
        """
        candidates = []
        seen_urls, seen_hashes = set(), set()
        for data in items:
            title = (data.get("title") or "").strip()
            url = normalize_url(data.get("url") or "")
            if not url or not title:
                continue
            summary = data.get("summary") or ""
            content_hash = self.compute_content_hash(f"{title} {summary}")
            if url in seen_urls or content_hash in seen_hashes:
                continue
            seen_urls.add(url)
            seen_hashes.add(content_hash)
            candidates.append((url, content_hash, title, summary, data))

        if not candidates:
            return 0

        existing = await self.db.execute(
            select(NewsItem.url, NewsItem.content_hash).where(
                or_(NewsItem.url.in_(seen_urls), NewsItem.content_hash.in_(seen_hashes))
            )
        )
        known_urls, known_hashes = set(), set()
        for url, content_hash in existing.all():
            known_urls.add(url)
            known_hashes.add(content_hash)

        new_items: List[NewsItem] = []
        for url, content_hash, title, summary, data in candidates:
            if url in known_urls or content_hash in known_hashes:
                continue
            new_items.append(NewsItem(
                source_id=source.id,
                category_id=source.category_id,
                title=title[:500],
                url=url,
                content_hash=content_hash,
                summary=summary,
                full_text=summary,  # ampliado no scraper completo
                published_date=data.get("published_date") or utcnow(),
                status=ProcessingStatus.PENDING,
                risk_level=self.classify_initial_risk(title, summary),
            ))

        if not new_items:
            return 0
        inserted = await self._persist_items(new_items, source.name)
        await self.db.commit()
        return inserted

    async def _persist_items(self, new_items: List[NewsItem], source_name: str) -> int:
        """
        Insere o lote dentro de um SAVEPOINT. Em conflito de unicidade (corrida rara),
        recua só o savepoint e tenta item a item — sem expirar a sessão nem perder o lote.
        """
        try:
            async with self.db.begin_nested():
                self.db.add_all(new_items)
            return len(new_items)
        except IntegrityError:
            logger.warning("[Discovery] Conflito de unicidade no lote da fonte %s; inserindo item a item", source_name)

        saved = 0
        for item in new_items:
            try:
                async with self.db.begin_nested():
                    self.db.add(item)
                saved += 1
            except IntegrityError:
                continue
        return saved

    @staticmethod
    def apply_fetch_result(source: Source, result: FetchResult) -> None:
        """Atualiza saúde da fonte e agenda a próxima checagem (com backoff exponencial em falhas)."""
        now = utcnow()
        source.last_checked_at = now
        source.last_status_code = result.status_code

        if result.error:
            source.error_count = (source.error_count or 0) + 1
            source.last_error = result.error
            backoff = min(2 ** source.error_count, settings.DISCOVERY_MAX_BACKOFF_FACTOR)
            logger.warning("[Discovery] Falha na fonte %s (%sx seguidas): %s",
                           source.name, source.error_count, result.error)
        else:
            source.error_count = 0
            source.last_error = None
            source.last_success_at = now
            backoff = 1
            if not result.not_modified:
                source.etag = result.etag
                source.last_modified = result.last_modified
                source.last_items_found = len(result.items)

        interval = source.check_interval_minutes or settings.DISCOVERY_DEFAULT_INTERVAL_MINUTES
        source.next_check_at = now + timedelta(minutes=interval * backoff)

    # --- Orquestração -----------------------------------------------------

    async def run_discovery_cycle(
        self, sources: Sequence[Source], client: Optional[httpx.AsyncClient] = None
    ) -> Dict[str, Any]:
        """
        Busca todas as fontes em paralelo (limitado por semáforo) e persiste em sequência
        (uma AsyncSession não pode ser usada concorrentemente).
        """
        started = time.perf_counter()
        report: Dict[str, Any] = {
            "sources_checked": len(sources), "sources_failed": 0, "sources_not_modified": 0,
            "items_seen": 0, "new_items_count": 0, "per_source": [],
        }
        if not sources:
            report["elapsed_ms"] = 0
            return report

        semaphore = asyncio.Semaphore(max(1, settings.DISCOVERY_CONCURRENCY))
        owns_client = client is None
        http = client or build_http_client()

        async def guarded(src: Source) -> FetchResult:
            async with semaphore:
                return await self.fetch_feed(http, src)

        try:
            results = await asyncio.gather(*(guarded(s) for s in sources))
        finally:
            if owns_client:
                await http.aclose()

        for source, result in zip(sources, results):
            inserted = 0
            if result.items and not result.error:
                inserted = await self.ingest_items(source, result.items)
            self.apply_fetch_result(source, result)

            report["items_seen"] += len(result.items)
            report["new_items_count"] += inserted
            report["sources_failed"] += 1 if result.error else 0
            report["sources_not_modified"] += 1 if result.not_modified else 0
            report["per_source"].append({
                "source_id": source.id, "name": source.name, "status_code": result.status_code,
                "not_modified": result.not_modified, "items_seen": len(result.items),
                "inserted": inserted, "error": result.error, "elapsed_ms": result.elapsed_ms,
            })

        await self.db.commit()
        report["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        return report
