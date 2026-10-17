# Módulo 2 — Fábrica de Conteúdo Original (v1)

## 1. Diagnóstico realizado antes da implementação

- **Arquitetura:** Python/FastAPI, SQLAlchemy assíncrono, SQLite ou PostgreSQL; Next.js 14, React, TypeScript e Tailwind no painel. Docker usa Python 3.12.
- **Reutilização:** coleta RSS e notícias já armazenadas; sanitização/detecção de prompt injection; `ContentProject`; TTS; legendas, gráficos e render FFmpeg; cache validado e prévia; `PublishingDispatcher`, OAuth e `YouTubePublisher`; jobs e auditoria.
- **Adições:** tópicos, produções e uso diário em tabelas próprias; pesquisa com allowlist; critérios de pontuação; schema de roteiro; verificações de evidência e sobreposição textual; aprovação; render e miniatura tipográfica; métricas reais; agendador próprio; API protegida e aba do painel.
- **Serviços existentes:** Gemini é o gerador editorial já integrado. OpenAI/Anthropic aparecem na configuração, mas não há adaptador operacional para este módulo. Pexels/Pixabay existem no módulo de notícias, mas não são utilizados na fábrica v1: os gráficos são produzidos pelo próprio renderizador.
- **Ambiente auditado:** Python, Node e npm disponíveis; FFmpeg/ffprobe ausentes; nenhuma chave dos provedores encontrada no ambiente de processo. Não foram lidos/exibidos valores de credenciais. Integrações externas foram testadas com mocks, não ao vivo.
- **Fila existente:** o projeto não tem worker Redis/Celery operacional. A fábrica usa estados persistentes e atualização condicional de fase; não foi adicionada uma segunda infraestrutura de filas.
- **Segurança existente:** rotas antigas não têm autenticação aplicada, o botão de emergência é por processo, e há dependências frontend com alertas. Novos endpoints exigem chave própria; isso **não torna as rotas antigas seguras para exposição pública**.
- **Plano adotado:** extensão compatível, desativada por padrão, sem substituir o pipeline de notícias. Pesquisa e geração → revisão humana → render e verificação técnica → dispatcher existente → métricas.
- O prompt recebido terminava em “5.2 — Considerar:”. Os critérios restantes não foram presumidos: esta v1 usa pesos explícitos e configuráveis abaixo. Requisitos adicionais precisam de uma próxima iteração.

## 2. O que está implementado

A aba **Fábrica de Conteúdo Original** oferece as dez categorias pedidas, natureza factual/hipotética/ficcional, formato vertical ou horizontal, cadastro de URLs, descoberta a partir dos feeds existentes, fila, relatório editorial, revisão, renderização, prévia, miniatura, envio e métricas.

`OriginalContentFactory` coordena:

1. **TopicDiscoveryService** (método `discover`): seleciona candidatos científicos/tecnológicos/históricos em `NewsItem`, somente de domínios permitidos; não modifica essas notícias. Também aceita ideias cadastradas manualmente. Não existe API de tendências, perguntas frequentes ou pesquisa geral contratada; não são fabricadas tendências.
2. **TopicScoringService:** curiosidade 30%, evidências disponíveis 40%, novidade 20%, caráter atemporal 10%. Pontuação é uma heurística, não previsão de audiência. Pesos configuráveis via JSON; negativos, infinitos e conjuntos inválidos são rejeitados. Similaridade de títulos e chave normalizada evitam repetição, e roteiros anteriores são comparados localmente.
3. **ResearchService:** HTTPS em hosts exatos autorizados, verificação de DNS público, sem redirects, HTML até 1 MB/fonte, até cinco fontes, extração de texto, data/hash da consulta, rejeição de instruções suspeitas. Fontes sem conteúdo suficiente bloqueiam geração. PDFs exigem adaptador futuro.
4. **OriginalScriptService:** Gemini gera JSON validado com título, descrição, ambos os roteiros, afirmações classificadas, trechos de evidência, incertezas, plano de cenas, hashtags e texto para miniatura. Não existe fallback que invente conteúdo se o provedor faltar.
5. **EditorialQualityService:** valida trechos de evidência, tamanho dos roteiros, identificação de hipóteses, URLs e sobreposição com fontes. Uma correspondência literal **não comprova a interpretação nem a veracidade**: revisão humana obrigatória. Não é detector universal de plágio nem certificação de originalidade.
6. **Renderização:** reutiliza o pipeline audiovisual com identificação própria, sem tarjas de notícia verificada, sem imagens aleatórias de banco, sem reaproveitar um áudio gravado de outra matéria. Exige TTS bem-sucedido. Usa gráficos animados próprios e legendas proporcionais; miniatura tipográfica própria em JPEG.
7. **Qualidade técnica:** ffprobe verifica resolução, orientação, duração e faixa de áudio; FFmpeg tenta decodificar vídeo/áudio. Não é análise perceptual de silêncio, de conteúdo dos frames ou alinhamento fonético das legendas.
8. **Publicação:** mesmos OAuth, upload e jobs do sistema atual; categoria YouTube educação; privacidade **private** por padrão; fontes e divulgação de IA incluídas. Envio de miniatura é tentado após o upload; falha de miniatura não provoca novo upload do vídeo. Canais precisam ser elegíveis a miniaturas personalizadas.
9. **Métricas:** consulta real de visualizações, curtidas e comentários, armazenada com data no painel. Não inventa métricas em simulação. Não há otimização automática/aprendizado de ranking nem consultas periódicas de Analytics nesta v1; o relatório permite avaliação editorial.

**Música, SFX e imagens generativas:** não há provedor de imagem/vídeo generativo nem biblioteca musical licenciada configurada no projeto. Esta versão não adiciona trilhas/efeitos sem licença nem apresenta gráficos próprios como imagens reais. O plano de cenas gerado fica disponível para revisão, mas não dirige uma montagem multiclipes ou geração de imagens nesta v1. Esses recursos permanecem extensões pendentes, não integrações simuladas.

## 3. Configuração local (Windows)

Faça backup do banco e da pasta storage antes de atualizar. Novas tabelas são criadas pelo `Base.metadata.create_all` no startup; não é necessário apagar o banco. Nenhuma coluna existente é removida.

No ambiente virtual do backend:

```powershell
cd backend
.\venv\Scripts\Activate.ps1   # ajuste ao nome do ambiente que você utiliza
pip install -r requirements.txt
```

Instale FFmpeg/ffprobe e verifique `ffmpeg -version` e `ffprobe -version`. O Dockerfile já instala FFmpeg. O requirements agora inclui `edge-tts`, que antes era importado opcionalmente sem declarar a dependência.

No arquivo `.env` **do diretório de trabalho do backend** (normalmente `backend/.env`), configure:

```dotenv
AGENT_MODE=SIMULATION
FACTORY_ENABLED=true
FACTORY_SCHEDULER_ENABLED=false
FACTORY_AUTO_PUBLISH=false
FACTORY_ADMIN_KEY="gere-uma-chave-aleatoria-propria-com-pelo-menos-32-caracteres"
GEMINI_API_KEY="sua-chave-local-nao-envie-em-chat"
FACTORY_DAILY_CALL_LIMIT=3
FACTORY_DAILY_BUDGET_MICROUSD=300000
FACTORY_CALL_RESERVATION_MICROUSD=100000
FACTORY_YOUTUBE_PRIVACY=private
FACTORY_SOURCE_HOSTS=["www.nasa.gov","science.nasa.gov","www.esa.int","arxiv.org"]
```

Gere a chave administrativa localmente com `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Não reutilize o texto de exemplo como chave de produção e não comite `.env`. A chave do módulo não é uma credencial GitHub.

`100000` micro-USD = US$ 0,10 de **reserva estimada por chamada**, não um preço real do Gemini. O limite de chamadas e as reservas são debitados atomicamente antes de chamar a IA e não são devolvidos em falhas, para limitar repetições. O limite financeiro é baseado na reserva configurada: **não garante um teto da fatura do provedor**. Configure a reserva conservadoramente e também limites no provedor. Por padrão, limites e orçamento são zero.

O módulo tem uma chamada Gemini por geração, no máximo 4096 tokens de saída e fontes limitadas. Uma falha transitória pode consumir uma nova reserva na tentativa seguinte. Não é feito fallback pago para outro serviço.

Reinicie o backend, atualize as dependências frontend (`npm ci`) e reinicie o frontend. Abra a nova aba. A chave administrativa é mantida apenas em memória na aba; não vai em URLs nem localStorage. A reprodução autenticada usa um blob no navegador, que é liberado ao trocar a produção ou sair.

No Docker, variáveis do `.env` da raiz **não são automaticamente injetadas no container** pelo Compose atual. Passe as variáveis `FACTORY_*`, Gemini e YouTube em `backend.environment` ou via um arquivo de ambiente explicitamente referenciado no serviço. Não incorpore credenciais na imagem. O `.dockerignore` do backend exclui `.env` e storage.

## 4. Como testar o fluxo sem publicação real

1. Mantenha `AGENT_MODE=SIMULATION` e agendador desligado.
2. Abra a fábrica e informe sua chave administrativa local.
3. Cadastre uma pergunta e pelo menos uma URL HTML válida em host autorizado. O cadastro não chama IA.
4. Clique em **Processar próxima etapa**. Sem chave Gemini, orçamento ou fonte legível, a produção falha explicitamente, sem inventar roteiro.
5. Leia fontes, afirmações e roteiros; confirme as três verificações e o responsável antes de aprovar.
6. Renderize o vídeo e a miniatura. Falta de TTS/FFmpeg/ffprobe bloqueia o envio; não é apresentado sucesso fictício.
7. Carregue e assista à prévia. Selecione um canal e simule o envio. Métricas reais não estarão disponíveis nessa fase.
8. Para passar de uma simulação a envio real, altere o modo do agente, clique em **Preparar esta produção para envio real**, assista à prévia e confirme. O padrão original é privado.

Notícias existentes continuam no fluxo anterior, sem depender de ativar a fábrica. Projetos originais não são criados como falsas notícias. Os endpoints genéricos não podem ser usados para contornar a aprovação da fábrica.

## 5. Automação e falhas

`FACTORY_SCHEDULER_ENABLED=true` ativa um loop independente no startup. A cada tick, ele descobre até cinco candidatos nos feeds existentes e processa uma etapa. Uma atualização SQL condicional toma posse da produção, evitando dois workers na mesma etapa. Ainda não é uma fila distribuída completa nem uma garantia de exactly-once.

A geração avança até **REVIEW_REQUIRED** e para. Aprovação humana é obrigatória nesta versão; não há chave que permita à IA declarar seus próprios fatos verdadeiros. Após a aprovação, render pode ser automático. Para envio automático pós-aprovação, também são obrigatórios:

```dotenv
AGENT_MODE=AUTONOMOUS
FACTORY_AUTO_PUBLISH=true
FACTORY_YOUTUBE_ACCOUNT_ID="id-da-conta-escolhida-no-painel"
FACTORY_YOUTUBE_PRIVACY=private
```

A conta não é escolhida arbitrariamente. `FACTORY_YOUTUBE_PRIVACY=public` deve ser configurado intencionalmente para vídeos públicos. YouTube client ID/secret e OAuth continuam sendo os mesmos do agente atual.

Estados principais:

`QUEUED → GENERATING → REVIEW_REQUIRED → APPROVED → RENDERING → READY → PUBLISHING → PUBLISHED/SIMULATED`

- Evidência/roteiro reprovado: `QUALITY_BLOCKED`. Não há aprovação forçada de um relatório reprovado; revisar e criar uma abordagem diferente é a opção segura desta v1.
- Falhas operacionais: `FAILED` ou `RENDER_FAILED`; repetição manual limitada.
- Timeout, rede, 429 e 5xx de geração têm backoff exponencial e máximo de três tentativas por padrão. Falhas de validação não entram em loop de retry.
- Trabalho local interrompido pode ser recuperado pelo endpoint de retry após 30 minutos. Compare com os processos reais antes de recuperar.
- Upload sem confirmação: `UPLOAD_UNKNOWN`. **Nunca é repetido automaticamente**; primeiro conferir o canal e os registros de jobs. Reconciliação automática/resumable upload retomado não está implementada.
- Falhas conhecidas antes do upload (conta pausada, quota, configuração) deixam a produção pronta para nova tentativa após resolver a causa, reutilizando o mesmo job.
- Mudança de roteiro invalida o fingerprint de aprovação. Esta v1 não oferece editor completo de roteiros/versionamento no painel.

Emergência é verificada antes das etapas e novamente no dispatcher após render. Upload em andamento não é interrompido. Em múltiplos processos, o estado atual do botão de emergência ainda não é compartilhado: manter uma única instância ou implementar controle persistente antes de produção distribuída.

## 6. API

Exceto `/api/v1/factory/status`, todos os endpoints exigem `X-Factory-Key`. Sem módulo/chave segura: 503; chave inválida: 401; transição inválida: 409. Nunca passar chave em query string.

- `GET /api/v1/factory/status`: capacidades e configuração pública, sem credenciais.
- `GET /api/v1/factory/productions`: fila, relatório, consumo reservado e contas YouTube.
- `POST /api/v1/factory/topics`: tema, categoria, natureza, URLs e formato.
- `POST /api/v1/factory/discover`: ideias a partir dos feeds existentes.
- `POST /api/v1/factory/run-next`: próxima etapa elegível.
- `POST /api/v1/factory/productions/{id}/approve`: revisor e três confirmações.
- `POST /api/v1/factory/productions/{id}/render`: render aprovado + thumbnail.
- `POST /api/v1/factory/productions/{id}/publish`: `account_id` de um canal YouTube ativo.
- `POST /api/v1/factory/productions/{id}/retry`: repetição local segura ou preparação de simulado para envio real.
- `POST /api/v1/factory/productions/{id}/metrics`: estatísticas reais.
- `GET /api/v1/factory/productions/{id}/thumbnail`: JPEG autenticado.
- As rotas existentes de preview exigem a mesma chave quando o projeto é da fábrica.

O nome do revisor é uma declaração de quem tem a chave compartilhada, **não autenticação individual/RBAC**. Use TLS, VPN/proxy autenticado, limites de requisição e controle de egress em produção. A allowlist e validação DNS reduzem SSRF, mas não substituem um proxy que fixe o IP de destino contra DNS rebinding. Não permita domínios de terceiros não confiáveis.

## 7. Testes e limitações da validação

```bash
PYTHONPATH=backend .venv/bin/pytest backend/tests -q
cd frontend
npm ci
npm test
npx tsc --noEmit
```

Node 22.12+ compatível com Vitest 5 para testes do frontend. Os testes cobrem o fluxo pesquisa→IA→aprovação→render→envio simulado com provedores mockados, autorização, não contorno pela API antiga, deduplicação, cotas, backoff, fontes, SSRF, prompt injection, hipóteses, falha de render e invalidação da aprovação.

Não houve chamada real ao Gemini, TTS, YouTube ou fontes externas neste ambiente. Não há FFmpeg instalado aqui; qualidade de voz/render real, miniatura elegível no canal e métricas devem ser validadas localmente em simulação/privado. Não foi feito deploy nem teste PostgreSQL/Docker end-to-end. Permanecem os alertas de dependências e segurança listados em `AUDITORIA.md`.
