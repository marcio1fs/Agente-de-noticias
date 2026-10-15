# Manual de Operação e Documentação Técnica: Redação Digital IA

Este documento reúne a arquitetura, instruções de execução, segurança e operação contínua do **Agente Autônomo de Notícias e Distribuição Multiplataforma**.

---

## 1. Visão Geral da Arquitetura

O sistema opera no ciclo contínuo:
$$\text{COLETAR} \longrightarrow \text{VERIFICAR} \longrightarrow \text{PRODUZIR} \longrightarrow \text{RENDERIZAR} \longrightarrow \text{PUBLICAR} \longrightarrow \text{AUDITAR}$$

- **Backend**: Python 3.14 / FastAPI assíncrono com SQLAlchemy 2.0 e Pydantic v2.
- **Frontend**: Next.js 14 (TypeScript / Tailwind CSS) com Dashboard responsivo em Português.
- **Banco de Dados**: SQLite local (desenvolvimento) ou PostgreSQL (produção).
- **Processamento de Vídeo**: Pipeline integrado com suporte a FFmpeg (16:9 horizontal e 9:16 vertical Shorts/Reels).
- **Segurança**: Criptografia Fernet em repouso para tokens de redes sociais e sanitização contra ataques de *Prompt Injection* em fontes web.

---

## 2. Inicialização Rápida no Ambiente Local

### Passo 1: Backend
```powershell
cd "c:\agente de noticias\backend"
.\venv\Scripts\Activate.ps1
$env:PYTHONPATH="."
uvicorn app.main:app --reload --port 8000
```
- Documentação interativa da API (Swagger): `http://localhost:8000/docs`
- Health check: `http://localhost:8000/api/health`

### Passo 2: Testes Automatizados
```powershell
cd "c:\agente de noticias\backend"
$env:PYTHONPATH="."
.\venv\Scripts\pytest tests/ -v
```

### Passo 3: Frontend (Dashboard)
```powershell
cd "c:\agente de noticias\frontend"
npm run dev
```
- Acesse o painel em: `http://localhost:3000`

---

## 3. Modos de Operação do Agente

O comportamento do sistema é configurado via variável de ambiente `AGENT_MODE`:

1. **`SIMULATION` (Padrão de Segurança)**:
   - Coleta notícias reais, gera resumos e renderiza vídeos normalmente.
   - Emite registros de publicação simulados sem despachar tráfego para APIs de redes sociais reais.
2. **`ASSISTED`**:
   - Processa todo o fluxo e coloca os conteúdos com status `APPROVAL_REQUIRED`. A publicação só ocorre após clique de aprovação no painel.
3. **`AUTONOMOUS`**:
   - Publica automaticamente conteúdos com classificação de risco **LOW** e pontuação de confiança igual ou superior a 80%.
   - Conteúdos de risco **HIGH** (crimes, investigações, denúncias) são retidos obrigatoriamente para revisão humana.

---

## 4. Botão de Pânico / Parada de Emergência

O painel administrativo possui um controle de parada global (`EMERGENCY_STOP`):
- Ao acionar o botão vermelho no menu lateral do dashboard ou enviar `POST /api/v1/system/emergency-stop?active=true`, **todas as publicações pendentes e em execução são imediatamente canceladas**, garantindo segurança absoluta diante de imprevistos.

---

## 5. Execução em Produção via Docker Compose

Para subir toda a infraestrutura com PostgreSQL, Redis, Backend (com FFmpeg embutido) e volumes persistentes:
```powershell
cd "c:\agente de noticias"
docker-compose up -d --build
```
