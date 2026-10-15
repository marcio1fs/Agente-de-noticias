# Manual de Operação e Documentação Técnica: Redação Digital IA

Este documento reúne a arquitetura, instruções de execução, segurança e operação contínua do **Agente Autônomo de Notícias e Distribuição Multiplataforma**.

---

## 1. Visão Geral da Arquitetura

O sistema opera no ciclo contínuo:
$$\text{COLETAR} \longrightarrow \text{VERIFICAR} \longrightarrow \text{PRODUZIR} \longrightarrow \text{RENDERIZAR} \longrightarrow \text{PUBLICAR} \longrightarrow \text{AUDITAR}$$

- **Backend**: Python 3.12 (Docker) / FastAPI assíncrono com SQLAlchemy 2.0 e Pydantic v2.
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
- Ao acionar o botão vermelho no menu lateral do dashboard ou enviar `POST /api/v1/system/emergency-stop?active=true`, novos despachos são bloqueados e a parada é rechecada após a renderização, antes do upload. Uploads já iniciados não são interrompidos; em múltiplos workers, o estado em memória não é compartilhado.

---

## 5. Execução em Produção via Docker Compose

Para subir toda a infraestrutura com PostgreSQL, Redis, Backend (com FFmpeg embutido) e volumes persistentes:
```powershell
cd "c:\agente de noticias"
docker-compose up -d --build
```


## 6. Seleção de vídeos relacionados e auditoria

O agente usa conceitos específicos da **manchete** e valida os metadados dos candidatos
Pixabay/Pexels antes de baixar. Não escolhe automaticamente o primeiro resultado e não
usa vídeos genéricos de outro assunto quando a busca falha. Manchetes desconhecidas,
ambíguas, candidatos sem metadados ou falta de chave resultam em **cartela editorial
com a notícia**, sem imagens de banco. Os clipes são ilustrativos, não registros
comprovados do acontecimento. As licenças de cada provedor devem ser respeitadas.

Renders anteriores à nova política não são reutilizados automaticamente na publicação.
O modo padrão é `SIMULATION`; redes sem integração real retornam falha fora desse modo.

Veja [AUDITORIA.md](AUDITORIA.md) para correções, testes e pendências de segurança.
**Não exponha a API administrativa publicamente sem autenticação.** A atualização
compatível do frontend ainda deixa alertas de dependências que exigem migração maior.

Testes em Linux, a partir da raiz:

```bash
python -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
PYTHONPATH=backend .venv/bin/pytest backend/tests -q
cd frontend
npm ci
npx tsc --noEmit
```


## 7. Quadro de prévia no painel

O quadro **Prévia antes de publicar** permite selecionar uma notícia com roteiro,
gerar/assistir ao vídeo 9:16 ou 16:9 e conferir a manchete e o resumo. Os botões
**Prévia** da lista abrem o mesmo quadro. Após reproduzir o vídeo, marque
**Revisei esta notícia e este vídeo** e confirme o envio (simulado em SIMULATION).
A publicação atual usa a versão 9:16, por isso a confirmação exige revisar esse formato.

A prévia não publica nada: gerar vídeo e publicar são ações separadas. Para garantir
revisão humana antes do envio automático, selecione **ASSISTED**; o modo AUTONOMOUS
não aguarda a confirmação visual deste quadro. A confirmação do painel não substitui
controles de autorização na API.

O frontend usa `/api` na mesma origem e encaminha ao backend via Next.js. Por padrão,
o destino interno é `http://127.0.0.1:8000`. Em instalações com serviços separados,
configure `BACKEND_URL` no ambiente do servidor frontend (por exemplo,
`http://backend:8000`) e reinicie-o. Essa URL não é exposta ao navegador.

O vídeo é servido por endpoint dedicado com suporte a busca por trecho (HTTP Range).
Prévia e upload reutilizam o mesmo render validado; se manchete ou roteiro mudar,
é necessário gerar a prévia novamente. É necessário FFmpeg no backend.


## 8. Link automático da fonte

A descrição enviada ao YouTube começa com **Fonte da notícia original: URL**.
O endereço vem diretamente da notícia coletada no banco (`NewsItem.url`), não da
resposta da IA. O link também é incluído nas legendas geradas e aparece no quadro
de prévia, junto à descrição que será enviada ao YouTube. A fonte é preservada
mesmo quando a descrição precisa ser truncada para caber no limite da plataforma.

Notícias sem URL HTTP/HTTPS válida têm a publicação bloqueada, inclusive na
simulação. Projetos antigos vinculados a uma notícia válida recebem a fonte no
próximo envio, sem precisar gerar novamente o texto. Posts já publicados não são
editados retroativamente. A integração real atual continua sendo apenas YouTube;
legendas preparadas para outras redes não significam publicação nessas redes.
