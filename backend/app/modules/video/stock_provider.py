"""Conservative, metadata-validated illustrative footage selection.

Stock footage illustrates a subject; it is never evidence of the reported event.
Unknown subjects or missing metadata intentionally produce no footage.
"""
import asyncio
import hashlib
import json
import logging
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, unquote

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def tokens(text: str) -> set[str]:
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return set(re.findall(r"[a-z]{3,}", text))


# Each visual concept has its own trigger and metadata vocabulary. Do not fall
# back from, e.g., interest rates to office meetings or from rain to wildfires.
CONCEPTS = [
    ("enchente inundacao inundacoes alagamento alagamentos", "flood flooded street", "flood flooded flooding"),
    ("chuva chuvas temporal tempestade", "rain storm", "rain rainy rainfall storm thunderstorm"),
    ("queimada queimadas incendio incendios", "wildfire forest fire", "wildfire fire burning"),
    ("seca estiagem", "drought dry land", "drought dry arid"),
    ("calor temperatura temperaturas", "thermometer heat", "thermometer heat temperature"),
    ("selic juros copom inflacao", "interest rate inflation", "interest inflation finance financial banking"),
    ("dolar cambio", "dollar currency", "dollar dollars currency"),
    ("ibovespa", "stock market trading", "stock stocks trading"),
    ("petroleo combustivel gasolina diesel", "oil refinery fuel", "oil refinery fuel petrol gasoline"),
    ("dengue mosquito", "mosquito", "mosquito mosquitoes"),
    ("vacina vacinas vacinacao", "vaccination injection", "vaccination vaccine injection"),
    ("hospital hospitais medico medicos", "hospital medical", "hospital medical doctor doctors"),
    ("futebol brasileirao libertadores", "soccer football", "soccer football"),
    ("rodovia transito congestionamento", "road traffic", "traffic road highway"),
    ("policia policial policiais prisao preso presos", "police patrol", "police patrol"),
    ("stf tse tribunal julgamento juiz juiza justica", "courtroom justice", "court courtroom judge justice judicial"),
    ("senado congresso parlamento deputados", "parliament", "parliament parliamentary congress"),
    ("inteligencia artificial", "artificial intelligence", "artificial intelligence robot robotics"),
    ("hacker hackers ciberataque ciberseguranca", "cyber security", "cyber cybersecurity hacker hacking"),
    ("escola escolas aluno alunos professor professores", "school classroom", "school classroom teacher pupils"),
    ("universidade universidades faculdade", "university campus", "university campus college"),
    ("safra agricultura agricola", "agriculture harvest", "agriculture agricultural harvest farming"),
    ("foguete foguetes espacial", "rocket space launch", "rocket spacecraft launch"),
]


class SafeStockVideoProvider:
    def __init__(self):
        self.pexels_key = settings.PEXELS_API_KEY
        self.pixabay_key = settings.PIXABAY_API_KEY
        self.cache_dir = os.path.join(settings.MEDIA_DIR, "stock_videos")
        os.makedirs(self.cache_dir, exist_ok=True)

    @staticmethod
    def _concepts(text: str):
        words = tokens(text)
        matches = []
        for triggers, query, vocabulary in CONCEPTS:
            # Multiword AI trigger requires both words, not merely 'artificial'.
            if triggers == "inteligencia artificial":
                matched = tokens(triggers) <= words
            else:
                matched = bool(tokens(triggers) & words)
            if matched:
                matches.append((query, tokens(vocabulary)))
        return matches

    async def extract_broll_search_terms(self, title: str, summary: Optional[str] = None) -> list[str]:
        # Headline is authoritative: a secondary subject in the script must not
        # override it. Ambiguous headlines fail closed rather than guessing.
        concepts = self._concepts(title)
        if len(concepts) != 1:
            return []
        return [concepts[0][0]]

    @staticmethod
    def _score(query: str, metadata: str) -> float:
        vocabulary = next((tokens(v) for _, q, v in CONCEPTS if q == query), set())
        words = tokens(metadata)
        if not vocabulary or not words & vocabulary:
            return 0.0
        # Reject evidence for a different visual subject, even if a broad tag
        # contains one word from the requested topic.
        for _, other_query, other_vocabulary in CONCEPTS:
            if other_query != query and words & (tokens(other_vocabulary) - vocabulary):
                return 0.0
        return len(words & tokens(query)) / max(1, len(tokens(query))) + 0.5

    @staticmethod
    def _safe_url(url: str, provider: str) -> bool:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        domains = {"pixabay": ("pixabay.com",), "pexels": ("pexels.com",)}[provider]
        return (parsed.scheme == "https" and not parsed.username and not parsed.password
                and parsed.port in (None, 443)
                and any(host == d or host.endswith("." + d) for d in domains))

    async def _download(self, client, url: str, provider: str, query: str) -> Optional[str]:
        if not self._safe_url(url, provider):
            return None
        key = hashlib.sha256(url.encode()).hexdigest()[:24]
        dest = Path(self.cache_dir) / f"validated_v2_{provider}_{key}.mp4"
        if dest.exists() and dest.stat().st_size > 50000:
            return str(dest)
        temp = None
        try:
            # No implicit redirects to untrusted hosts; bounded streaming avoids
            # loading entire clips into RAM and partial files never enter cache.
            async with client.stream("GET", url, timeout=30.0) as response:
                response.raise_for_status()
                if response.headers.get("content-type", "").split(";")[0] not in ("video/mp4", "application/octet-stream"):
                    return None
                size = 0
                with tempfile.NamedTemporaryFile(dir=self.cache_dir, suffix=".part", delete=False) as output:
                    temp = output.name
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > 80 * 1024 * 1024:
                            return None
                        output.write(chunk)
                with open(temp, "rb") as stream:
                    header = stream.read(32)
                if size <= 50000 or b"ftyp" not in header:
                    return None
                os.replace(temp, dest)
                Path(str(dest) + ".json").write_text(json.dumps({
                    "provider": provider, "query": query, "source_url": url,
                    "illustrative": True, "validation": "metadata_v2",
                }), encoding="utf-8")
                return str(dest)
        finally:
            if temp and os.path.exists(temp):
                os.remove(temp)

    async def fetch_pixabay_video(self, query: str, is_vertical: bool = False) -> Optional[str]:
        if not self.pixabay_key:
            return None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get("https://pixabay.com/api/videos/", params={
                    "key": self.pixabay_key, "q": query, "per_page": 12,
                    "video_type": "film", "safesearch": "true",
                })
                res.raise_for_status()
                candidates = []
                for hit in res.json().get("hits", []):
                    score = self._score(query, hit.get("tags", ""))
                    info = hit.get("videos", {}).get("medium") or {}
                    w, h = info.get("width", 0), info.get("height", 0)
                    if score > 0 and min(w, h) >= 480 and (h > w) == is_vertical:
                        candidates.append((score, info.get("url", "")))
                for _, url in sorted(candidates, key=lambda c: c[0], reverse=True):
                    path = await self._download(client, url, "pixabay", query)
                    if path:
                        return path
        except (httpx.HTTPError, ValueError, TypeError, KeyError, OSError):
            logger.warning("Pixabay indisponível ou resposta inválida; sem vídeo não validado")
        return None

    async def fetch_pexels_video(self, query: str, is_vertical: bool = False) -> Optional[str]:
        if not self.pexels_key:
            return None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get("https://api.pexels.com/videos/search", params={
                    "query": query, "orientation": "portrait" if is_vertical else "landscape", "per_page": 12,
                }, headers={"Authorization": self.pexels_key})
                res.raise_for_status()
                candidates = []
                for video in res.json().get("videos", []):
                    # Search rank alone is not relevance evidence. Pexels often
                    # exposes the descriptive slug in the canonical page URL.
                    metadata = f"{video.get('tags', '')} {unquote(urlparse(video.get('url', '')).path)}"
                    score = self._score(query, metadata)
                    for info in video.get("video_files", []):
                        w, h = info.get("width", 0), info.get("height", 0)
                        if score > 0 and info.get("file_type") == "video/mp4" and min(w, h) >= 480 and (h > w) == is_vertical:
                            candidates.append((score, w * h, info.get("link", "")))
                for _, _, url in sorted(candidates, key=lambda c: (-c[0], c[1])):
                    path = await self._download(client, url, "pexels", query)
                    if path:
                        return path
        except (httpx.HTTPError, ValueError, TypeError, KeyError, OSError):
            logger.warning("Pexels indisponível ou resposta inválida; sem vídeo não validado")
        return None

    async def _search_relevant_video(self, title: str, summary: Optional[str], is_vertical: bool) -> Optional[str]:
        if not self.pixabay_key and not self.pexels_key:
            return None
        async with asyncio.timeout(45):
            for term in await self.extract_broll_search_terms(title, summary):
                path = await self.fetch_pixabay_video(term, is_vertical)
                if not path:
                    path = await self.fetch_pexels_video(term, is_vertical)
                if path:
                    return path
        return None

    def get_public_domain_broll(self, headline_or_topic: str, is_vertical: bool = False,
                               script_or_summary: Optional[str] = None) -> Optional[str]:
        """Legacy name: provider licenses apply; these clips are not necessarily CC0.

        Call this synchronous adapter from a worker, never from the ASGI loop.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            try:
                return asyncio.run(self._search_relevant_video(headline_or_topic, script_or_summary, is_vertical))
            except TimeoutError:
                logger.warning("Tempo limite de busca; usando cartela editorial")
                return None
        logger.warning("Busca síncrona chamada no event loop; usando cartela editorial")
        return None
