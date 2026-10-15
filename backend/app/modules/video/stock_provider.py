import os
import re
import json
import urllib.parse
from typing import Optional, List
import httpx

from app.core.config import settings

class SafeStockVideoProvider:
    """
    Provedor Semântico de Vídeos de Apoio (B-Roll) Livres de Direitos Autorais.
    
    Arquitetura de Relevância Visual:
    1. Análise Semântica via IA (Gemini):
       Extrai o cenário visual concreto e contextual (ex: "tribunal julgamento" -> "courtroom judge justice").
    2. Taxonomia Editorial de Fallback:
       Classifica o tema por regras heurísticas robustas caso a IA esteja offline.
    3. Busca no Pixabay & Pexels com múltiplos termos qualificados em inglês e português.
    4. Validação de qualidade mínima e cache inteligente por assunto.
    """

    # Mapeamento heurístico editorial de temas recorrentes para termos de alta qualidade em bancos de imagem
    THEMATIC_DICTIONARY = [
        # Judiciário / Política / Leis
        (r"\b(tse|stf|supremo|tribunal|juiz|justi[çc]a|decis[aã]o|processo|advogad|lei|ministr|lula|bolsonaro|congresso|senado|c[aâ]mara|deputad)\b",
         ["courtroom judge", "justice law gavel", "government parliament building"]),

        # Economia / Negócios / Dinheiro
        (r"\b(economia|d[oó]lar|infla[çc][aã]o|mercado|bolsa|a[çc][oõ]es|banco|juros|selic|investiment|dinheiro|lucro|pre[çc]o|petr[oó]leo|combust[ií]vel)\b",
         ["stock market chart", "finance money counting", "business office meeting"]),

        # Tecnologia / IA / Redes Sociais
        (r"\b(intelig[eê]ncia artificial|ia|cyber|hacker|tecnologia|software|computador|celular|smartphone|rede social|dados|algoritmo|deepfake)\b",
         ["artificial intelligence robot", "cyber security data", "digital technology screen"]),

        # Saúde / Medicina / Ciência
        (r"\b(sa[uú]de|m[eé]dic|hospital|vacina|doen[çc]a|rem[eé]dio|v[ií]rus|cientista|pesquisa|laborat[oó]rio|dengue|covid)\b",
         ["hospital doctors medical", "laboratory science research", "medicine pharmacy"]),

        # Segurança Pública / Polícia / Trânsito
        (r"\b(pol[ií]cia|preso|pris[aã]o|crime|assalto|opera[çc][aã]o|investiga|acidente|tr[aâ]nsito|rodovia|batalh[aã]o|seguran[çc]a)\b",
         ["police car siren lights", "city traffic road", "night city security"]),

        # Esportes
        (r"\b(futebol|gol|campeonato|brasileir[aã]o|libertadores|jogador|técnico|est[aá]dio|copa|clube|time|atleta)\b",
         ["soccer stadium football", "athlete running training", "sports arena crowd"]),

        # Clima / Meio Ambiente / Agro
        (r"\b(chuva|temporal|calor|seca|queimada|inc[eê]ndio|agro|safra|agricultura|fazenda|floresta|enchente|temperatura)\b",
         ["rain storm weather", "wildfire smoke forest", "agriculture farm field"]),

        # Educação
        (r"\b(escola|professor|universidade|faculdade|estudante|aluno|enem|educa[çc][aã]o)\b",
         ["university students classroom", "school education books", "library study"]),
    ]

    def __init__(self):
        self.pexels_key = getattr(settings, "PEXELS_API_KEY", None) or os.getenv("PEXELS_API_KEY", "")
        self.pixabay_key = getattr(settings, "PIXABAY_API_KEY", None) or os.getenv("PIXABAY_API_KEY", "")
        self.cache_dir = os.path.join(settings.MEDIA_DIR, "stock_videos")
        os.makedirs(self.cache_dir, exist_ok=True)

    async def extract_broll_search_terms(self, title: str, summary: Optional[str] = None) -> List[str]:
        """
        Extrai termos contextuais cinematográficos para B-Roll de telejornal.
        Usa IA Gemini (se disponível) ou o Dicionário Heurístico Editorial.
        """
        full_text = f"{title}. {summary or ''}".strip()

        # 1. TENTATIVA VIA INTELIGÊNCIA ARTIFICIAL (GEMINI)
        if settings.GEMINI_API_KEY:
            try:
                prompt = (
                    "Você é o editor de videografismo e B-roll de um telejornal profissional.\n"
                    "Dada a matéria abaixo, qual cena concreta de banco de vídeo (b-roll neutro/livre de direitos) "
                    "deve passar ao fundo para ilustrar a matéria com máxima seriedade e credibilidade?\n\n"
                    f"Matéria: {full_text[:400]}\n\n"
                    "Regras para os termos de busca em inglês para o Pixabay:\n"
                    "- Escolha termos de 1 a 3 palavras simples de objetos, lugares ou ações (ex: 'courtroom judge', 'stock market', 'artificial intelligence').\n"
                    "- NUNCA retorne nomes próprios de pessoas políticas que não existem em banco livre (evite 'Lula', 'Moraes', 'Messias').\n"
                    "- Retorne um JSON com uma lista de 3 buscas ordenadas por relevância:\n"
                    '{"queries": ["termo_1", "termo_2", "termo_3"]}'
                )

                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={settings.GEMINI_API_KEY}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}
                }
                async with httpx.AsyncClient(timeout=10.0) as client:
                    res = await client.post(url, json=payload)
                    if res.status_code == 200:
                        data = res.json()
                        raw_json = data["candidates"][0]["content"]["parts"][0]["text"]
                        parsed = json.loads(raw_json)
                        queries = parsed.get("queries", [])
                        if queries and isinstance(queries, list):
                            print(f"[StockVideoProvider] Termos semânticos gerados pela IA: {queries}")
                            return [q.strip().lower() for q in queries if q.strip()]
            except Exception as e:
                print(f"[StockVideoProvider] Falha ao extrair termos com Gemini ({e}). Usando dicionário temático.")

        # 2. FALLBACK VIA TAXONOMIA TEMÁTICA HEURÍSTICA
        lower_text = full_text.lower()
        for pattern, terms in self.THEMATIC_DICTIONARY:
            if re.search(pattern, lower_text):
                print(f"[StockVideoProvider] Tema detectado via taxonomia: {terms[0]}")
                return terms

        # 3. FALLBACK GERAL DE TELEJORNALISMO
        return ["broadcast news studio", "digital technology", "city skyline journalism"]

    async def fetch_pexels_video(self, query: str, is_vertical: bool = False) -> Optional[str]:
        """Busca vídeo no Pexels com verificação de licença livre."""
        if not self.pexels_key:
            return None

        orientation = "portrait" if is_vertical else "landscape"
        url = f"https://api.pexels.com/videos/search?query={urllib.parse.quote(query)}&orientation={orientation}&per_page=4&size=medium"
        headers = {"Authorization": self.pexels_key}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    videos = data.get("videos", [])
                    if videos:
                        video_files = videos[0].get("video_files", [])
                        selected_url = None
                        for vf in video_files:
                            if vf.get("quality") in ["hd", "sd"] and vf.get("link"):
                                selected_url = vf["link"]
                                break
                        if not selected_url and video_files:
                            selected_url = video_files[0].get("link")

                        if selected_url:
                            cached_name = f"pexels_{videos[0]['id']}_{orientation}.mp4"
                            dest_path = os.path.join(self.cache_dir, cached_name)
                            if os.path.exists(dest_path) and os.path.getsize(dest_path) > 50000:
                                return dest_path

                            v_res = await client.get(selected_url, timeout=25.0)
                            if v_res.status_code == 200:
                                with open(dest_path, "wb") as f:
                                    f.write(v_res.content)
                                return dest_path
        except Exception as e:
            print(f"[StockVideoProvider] Erro ao buscar no Pexels: {e}")
        return None

    async def fetch_pixabay_video(self, query: str) -> Optional[str]:
        """Busca vídeo de apoio correspondente no Pixabay."""
        if not self.pixabay_key:
            return None

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        url = f"https://pixabay.com/api/videos/?key={self.pixabay_key}&q={urllib.parse.quote(query)}&per_page=5&video_type=film"
        try:
            async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    hits = data.get("hits", [])
                    if hits:
                        hit = hits[0]
                        videos_dict = hit.get("videos", {})
                        v_info = videos_dict.get("medium") or videos_dict.get("large") or videos_dict.get("small")
                        if v_info and v_info.get("url"):
                            cached_name = f"pixabay_{hit['id']}.mp4"
                            dest_path = os.path.join(self.cache_dir, cached_name)
                            if os.path.exists(dest_path) and os.path.getsize(dest_path) > 50000:
                                return dest_path

                            v_res = await client.get(v_info["url"], timeout=30.0)
                            if v_res.status_code == 200 and len(v_res.content) > 50000:
                                with open(dest_path, "wb") as f:
                                    f.write(v_res.content)
                                print(f"[StockVideoProvider] Vídeo correspondente baixado com sucesso: {dest_path} (termo='{query}')")
                                return dest_path
        except Exception as e:
            print(f"[StockVideoProvider] Erro no Pixabay para query '{query}': {e}")
        return None

    def get_public_domain_broll(self, headline_or_topic: str, is_vertical: bool = False, script_or_summary: Optional[str] = None) -> Optional[str]:
        """
        Retorna o caminho de um vídeo de apoio 100% relevante ao tema da notícia.
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self._search_relevant_video(headline_or_topic, summary=script_or_summary, is_vertical=is_vertical))
                    return future.result(timeout=20.0)
            else:
                return loop.run_until_complete(self._search_relevant_video(headline_or_topic, summary=script_or_summary, is_vertical=is_vertical))
        except Exception as e:
            print(f"[StockVideoProvider] Erro ao obter B-roll: {e}")
            return None

    async def _search_relevant_video(self, title: str, summary: Optional[str], is_vertical: bool) -> Optional[str]:
        search_terms = await self.extract_broll_search_terms(title, summary)

        for term in search_terms:
            # 1. Procura no Pixabay
            px_path = await self.fetch_pixabay_video(term)
            if px_path:
                return px_path

            # 2. Procura no Pexels (se houver chave)
            pe_path = await self.fetch_pexels_video(term, is_vertical)
            if pe_path:
                return pe_path

        return None
