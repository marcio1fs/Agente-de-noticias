"""Source attribution is derived from the collected article, never from an LLM."""
from urllib.parse import urlsplit

from app.models.entities import NewsItem


def validated_source_url(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > 2000 or any(c.isspace() or ord(c) < 32 for c in value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            return None
        parsed.port  # Reject invalid port syntax, too.
    except ValueError:
        return None
    return value


async def project_source_url(project, db):
    if db is None or not project.news_item_id:
        return None
    news = await db.get(NewsItem, project.news_item_id)
    return validated_source_url(news.url) if news else None


def with_source(text: str | None, source_url: str, limit: int = 5000) -> str:
    """Put attribution first, reserving space so platform truncation cannot remove it."""
    source_url = validated_source_url(source_url)
    if not source_url:
        raise ValueError("A notícia precisa de uma URL de fonte HTTP/HTTPS válida.")
    block = f"Fonte da notícia original: {source_url}"
    if len(block) > limit:
        raise ValueError("Link da fonte excede o limite da plataforma.")
    body = text.strip() if isinstance(text, str) else ""
    body = body.replace(block, "").strip()
    if not body:
        return block
    return (block + "\n\n" + body[:max(0, limit - len(block) - 2)]).rstrip()


def youtube_description(project, source_url: str):
    captions = project.social_captions if isinstance(project.social_captions, dict) else {}
    caption = captions.get("youtube", "")
    body = "\n\n".join(part for part in (
        project.editorial_summary or "", caption if isinstance(caption, str) else "",
        "#noticias #urgente #jornalismo",
    ) if part)
    return with_source(body, source_url, limit=5000)
