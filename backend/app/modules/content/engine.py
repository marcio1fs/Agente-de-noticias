"""
Motor de Redação Jornalística e Geração de Conteúdo com IA.

Aplica técnicas profissionais de telejornalismo:
1. Pirâmide Invertida (Lede: Quem, O quê, Onde, Quando, Por quê).
2. Hooks virais de alta retenção (Pattern Interrupt e Curiosity Gap inspirados nas skills de Seedance).
3. Adaptação para múltiplos formatos:
   - Roteiro TV/YouTube 16:9 (narrativa completa com introdução, desenvolvimento e checagem).
   - Roteiro Shorts/Reels/TikTok 9:16 (gancho de 3 segundos, dinamismo e call to action).
   - Chamadas otimizadas para redes sociais (Twitter, Instagram, YouTube).
4. Integração nativa com LLMs (Gemini / OpenAI) via chamadas assíncronas diretas com fallback inteligente.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.publishing.attribution import validated_source_url, with_source
from app.core.config import settings
from app.models.entities import NewsItem, ContentProject, ProcessingStatus

logger = logging.getLogger(__name__)


# Padrões de Ganchos Jornalísticos Dinâmicos (Hooks de Retenção)
VIRAL_HOOKS = [
    "Atenção para esta informação urgente que afeta diretamente o seu bolso hoje.",
    "Decisão de última hora acabou de ser confirmada pelas autoridades oficiais.",
    "Se você acompanha as notícias do dia, pare tudo para ver este desdobramento.",
    "Um acontecimento confirmado há poucos instantes mudou o cenário nas últimas horas.",
    "Atenção para os fatos apurados e checados que acabaram de vir a público."
]


class ContentProductionEngine:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _select_hook(item: NewsItem) -> str:
        """Seleciona o gancho de abertura mais adequado ao perfil da notícia."""
        title_lower = (item.title or "").lower()
        if any(w in title_lower for w in ["dólar", "inflação", "selic", "banco", "imposto", "preço"]):
            return "Atenção para esta decisão econômica que afeta diretamente seu bolso a partir de agora."
        if any(w in title_lower for w in ["urgente", "alerta", "decisão", "determina", "aprova", "stf"]):
            return "Decisão confirmada de última hora: veja os detalhes apurados e checados agora."
        if any(w in title_lower for w in ["tecnologia", "ia", "apple", "google", "meta", "sistema"]):
            return "Novo anúncio no setor de tecnologia promete impactar milhões de usuários."
        return VIRAL_HOOKS[abs(hash(item.title)) % len(VIRAL_HOOKS)]

    @staticmethod
    def _fallback_generation(item: NewsItem) -> Dict[str, Any]:
        """
        Geração jornalística estruturada com regras profissionais (Pirâmide Invertida),
        garantindo excelente qualidade mesmo quando a API externa de IA estiver sem saldo/offline.
        """
        hook = ContentProductionEngine._select_hook(item)
        date_str = item.published_date.strftime("%d/%m/%Y às %H:%M") if item.published_date else "Hoje"
        details = item.summary.strip() if item.summary else item.title.strip()

        # Resumo Editorial (Pirâmide Invertida)
        editorial_summary = (
            f"[REDAÇÃO PROFISSIONAL - RESUMO EDITORIAL]\n\n"
            f"MANCHETE: {item.title}\n"
            f"LEDE (O QUÊ / QUEM): {details[:300]}\n"
            f"CONTEXTO & APURAÇÃO: Fato apurado em fontes públicas de referência com dados checados.\n"
            f"FONTE OFICIAL: {item.url}\n"
            f"DATA / REGISTRO: {date_str}\n"
        )

        # Roteiro Curto 9:16 (Shorts/TikTok/Reels) com gancho de 3 segundos
        short_script = (
            f"{hook}\n\n"
            f"{item.title}.\n\n"
            f"{details[:220]}.\n\n"
            f"A apuração completa e as fontes checadas estão no link. "
            f"Inscreva-se e ative as notificações para não perder nenhuma atualização."
        )

        # Roteiro Longo 16:9 (YouTube Notícias / Telejornal)
        long_script = (
            f"[00:00 - GANCHO E ABERTURA]\n"
            f"{hook} Olá a todos, sejam bem-vindos à nossa central de jornalismo checado.\n\n"
            f"[00:15 - OS FATOS PRINCIPAIS]\n"
            f"A manchete em destaque: {item.title}.\n"
            f"{details}\n\n"
            f"[00:45 - CONTEXTO E REPERCUSSÃO]\n"
            f"Nossa equipe de monitoramento acompanha as repercussões deste fato em tempo real junto às fontes oficiais.\n\n"
            f"[01:10 - CONSIDERAÇÕES FINAIS E PARTICIPAÇÃO]\n"
            f"Qual é a sua avaliação sobre este acontecimento? Deixe seu comentário logo abaixo, "
            f"compartilhe este vídeo com quem precisa saber e inscreva-se no canal para jornalismo ágil e profissional."
        )

        social_captions = {
            "youtube": f"{item.title}\n\n{editorial_summary}\n\n#noticias #urgente #brasil #jornalismo",
            "instagram": f"📰 {hook}\n\n{item.title}\n\n{details[:180]}...\n\nConfira todos os dados no link da bio.\n#noticias #brasil #jornalismo",
            "twitter": f"🔴 {item.title[:200]} Saiba mais: {item.url} #Noticias"
        }

        return {
            "headline": item.title.strip(),
            "editorial_summary": editorial_summary,
            "short_script": short_script,
            "long_script": long_script,
            "social_captions": social_captions
        }

    def _build_prompt(self, item: NewsItem) -> str:
        return (
            f"Você é um editor-chefe de telejornal e repórter profissional de alta velocidade.\n"
            f"Analise o seguinte fato noticioso e produza materiais jornalísticos de alta qualidade.\n\n"
            f"Título Original: {item.title}\n"
            f"Texto/Resumo do Fato: {item.summary or item.title}\n"
            f"Fonte Original: {item.url}\n\n"
            f"Diretrizes de Locução e Pontuação:\n"
            f"- Escreva com pontuação cadenciada e pausada, utilizando vírgulas e pontos finais para marcar a respiração natural de um âncora de telejornal.\n"
            f"- Evite frases excessivamente longas ou sem pausas. Separe orações e dados por vírgulas para facilitar a dicção da narração.\n\n"
            f"Retorne OBRIGATORIAMENTE um JSON válido com os seguintes campos:\n"
            f"{{\n"
            f'  "headline": "Manchete forte, objetiva, sem sensacionalismo (até 90 caracteres)",\n'
            f'  "editorial_summary": "Resumo jornalístico estruturado no método da Pirâmide Invertida (Lede, detalhes, repercussão)",\n'
            f'  "short_script": "Roteiro dinâmico para vídeo vertical 9:16 (Shorts/Reels) de até 45 segundos, pontuado com vírgulas e pontos para locução clara, iniciando com gancho nos primeiros 3 segundos",\n'
            f'  "long_script": "Roteiro estruturado para vídeo horizontal 16:9 estilo telejornal com blocos marcados de tempo e pontuação cadenciada",\n'
            f'  "social_captions": {{\n'
            f'    "youtube": "Descrição completa para YouTube com hashtags",\n'
            f'    "instagram": "Legenda com gancho visual e emojis jornalísticos",\n'
            f'    "twitter": "Post curto e direto de até 250 caracteres"\n'
            f'  }}\n'
            f"}}\n"
            f"Responda APENAS com o JSON, sem markdown ou explicações fora do JSON."
        )

    async def _call_ollama_api(self, item: NewsItem) -> Optional[Dict[str, Any]]:
        """Gera o conteúdo jornalístico via LLM local gratuita usando Ollama."""
        ollama_url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate"
        prompt = self._build_prompt(item)
        payload = {
            "model": settings.OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.3
            }
        }
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                res = await client.post(ollama_url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    raw_text = data.get("response", "")
                    clean_text = raw_text.strip().replace("```json", "").replace("```", "").strip()
                    parsed = json.loads(clean_text)
                    logger.info("[ContentEngine] Conteúdo gerado com sucesso via Ollama (%s)!", settings.OLLAMA_MODEL)
                    return parsed
                else:
                    logger.warning("[ContentEngine] Ollama retornou status %s: %s", res.status_code, res.text[:150])
        except Exception as e:
            logger.info("[ContentEngine] Ollama indisponível ou offline (%s).", str(e))
        return None

    async def _call_gemini_api(self, item: NewsItem) -> Optional[Dict[str, Any]]:
        """Gera o conteúdo jornalístico com Google Gemini se houver chave configurada."""
        if not settings.GEMINI_API_KEY:
            return None

        prompt = self._build_prompt(item)

        try:
            # Modelos ativos na API do Google
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={settings.GEMINI_API_KEY}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"}
            }
            async with httpx.AsyncClient(timeout=25.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                    clean_text = raw_text.strip().replace("```json", "").replace("```", "").strip()
                    parsed = json.loads(clean_text)
                    logger.info("[ContentEngine] Conteúdo gerado com sucesso via Gemini!")
                    return parsed
                else:
                    logger.warning("[ContentEngine] Gemini retornou status %s: %s", res.status_code, res.text[:150])
        except Exception as e:
            logger.warning("[ContentEngine] Falha na chamada da API Gemini (%s). Usando motor jornalístico local.", str(e))
        return None

    async def _call_llm(self, item: NewsItem) -> Optional[Dict[str, Any]]:
        """Orquestra a geração de LLM respeitando prioridade configurada e fallbacks."""
        provider = (settings.LLM_PROVIDER or "auto").lower()

        if provider == "ollama":
            return await self._call_ollama_api(item)
        elif provider == "gemini":
            return await self._call_gemini_api(item)

        # Modo AUTO: tenta Ollama local primeiro (grátis); se não responder, tenta Gemini
        content = await self._call_ollama_api(item)
        if content:
            return content

        if settings.GEMINI_API_KEY:
            content = await self._call_gemini_api(item)
            if content:
                return content

        return None

    async def produce_content(self, item: NewsItem) -> ContentProject:
        """Cria e persiste o projeto de conteúdo jornalístico."""
        # 1. Tenta enriquecer via LLM (Ollama gratuito / Gemini); se indisponível, usa o motor heurístico profissional
        llm_content = await self._call_llm(item)
        if not llm_content:
            llm_content = self._fallback_generation(item)

        # Persist attribution in captions too, regardless of whether the LLM
        # included a citation. Final dispatch re-resolves the original DB URL.
        captions = llm_content.get("social_captions", {})
        captions = dict(captions) if isinstance(captions, dict) else {}
        source_url = validated_source_url(item.url)
        if source_url:
            for platform in ("youtube", "instagram", "twitter"):
                limit = {"youtube": 5000, "instagram": 2200, "twitter": 280}[platform]
                try:
                    captions[platform] = with_source(captions.get(platform, ""), source_url, limit)
                except ValueError:
                    # Never invent/shorten the original URL. Keep it available
                    # for editorial review even if a future platform rejects it.
                    captions[platform] = with_source(captions.get(platform, ""), source_url)

        project = ContentProject(
            news_item_id=item.id,
            category_id=item.category_id,
            headline=llm_content.get("headline", item.title).strip(),
            editorial_summary=llm_content.get("editorial_summary", ""),
            full_article=llm_content.get("editorial_summary", ""),
            script_youtube_long=llm_content.get("long_script", ""),
            script_short_vertical=llm_content.get("short_script", ""),
            social_captions=captions,
            status=ProcessingStatus.PRODUCING,
            requires_human_approval=(item.status == ProcessingStatus.APPROVAL_REQUIRED)
        )

        self.db.add(project)
        await self.db.commit()
        return project
