# Auditoria técnica — 15/10/2026

## Escopo

Revisão do fluxo de descoberta → produção → seleção de B-roll → renderização → publicação, configuração e dependências do frontend. Não é certificação de segurança nem validação factual das notícias. Nenhuma publicação real foi realizada.

## Problemas corrigidos

| Achado | Correção |
| --- | --- |
| Primeiro resultado do banco aceito sem verificar relação | Candidatos ordenados por correspondência entre conceito da manchete e tags/slug descritivo; metadados ausentes ou conflitantes são rejeitados. |
| Categorias misturavam assuntos (chuva/incêndio/agro, juros/escritório etc.) | Conceitos visuais específicos, sem alternativas de outro assunto. Manchete desconhecida ou com múltiplos conceitos usa cartela editorial. O roteiro não substitui um tema desconhecido da manchete. |
| Fallback genérico com skyline, estúdio e tecnologia | Removido. Sem correspondência, indisponibilidade ou ausência de chaves: fundo gráfico com manchete/narração, sem B-roll. |
| Consultas geradas por LLM sem validação | Seleção visual determinística, sem custo/latência de chamada Gemini para B-roll. A IA continua disponível na produção editorial. |
| Downloads integrais em RAM e arquivos parciais reutilizáveis | Streaming com teto de 80 MiB, tipo de conteúdo e assinatura MP4, arquivo temporário e substituição atômica. Downloads HTTPS limitados aos domínios dos provedores, sem seguir redirects automaticamente. |
| Formato e resolução ignorados | Exige orientação correspondente e dimensão menor de pelo menos 480 pixels; pode deliberadamente resultar em menos vídeos disponíveis. |
| Cache antigo podia continuar publicando vídeos sem relação | Cache de clipes com namespace novo; publicação só reutiliza render com manifesto da nova política e fingerprint de manchete/roteiro/formato. Renders antigos são regenerados no próximo envio. |
| Vídeo de banco apresentado como “AO VIVO” | Identificação alterada para “IMAGENS ILUSTRATIVAS” no layout broadcast. |
| Adaptador síncrono falhava sem event loop e bloqueava ASGI | Uso de `asyncio.run` em worker; renderização da API e do dispatcher deslocada para `asyncio.to_thread`. Busca tem orçamento global de 45 segundos. |
| Opção FFmpeg incompatível com versões comuns do Docker | Uso de `-filter_complex_script`. Ausência do FFmpeg e render sem arquivo válido geram falha explícita. |
| Outras redes/YouTube sem configuração geravam sucesso e URLs fictícias em produção | Falha explícita; simulação só em SIMULATION. Pipeline/API não reportam sucesso se todos os destinos falharem. |
| Mesmo job publicado poderia ser enviado novamente | Job já PUBLISHED retorna o resultado anterior, sem incrementar contador. Isso não é deduplicação global de novos jobs. |
| Parada acionada durante render ignorada até upload | Rechecagem da parada/pausa após render, antes de iniciar upload. Não interrompe upload já iniciado. |
| Padrão real divergia do README; startup sobrescrevia `.env` | Padrão SIMULATION, enumeração validada e remoção da sobrescrita no startup. |
| `.env.example` continha comando curl no lugar de chave Pixabay | Exemplo corrigido. |
| Instalação local sem dependência do SQLAlchemy assíncrono | `sqlalchemy[asyncio]` em requirements. |
| Next.js fixado em 14.2.15 | Atualização compatível para 14.2.35 e lockfile atualizado. Não elimina todos os alertas atuais. |

## Validação executada

- `PYTHONPATH=backend .venv/bin/pytest backend/tests -q`: **48 testes passaram**, incluindo os existentes e as regressões novas.
- `cd frontend && npx tsc --noEmit`: passou.
- `git diff --check`: passou.
- `npm audit` e `npm audit fix` executados; permanecem **9 alertas** no conjunto completo (2 moderados, 6 altos, 1 crítico). A auditoria de produção aponta Next.js e PostCSS transitivo. As correções sugeridas exigem migração de versões maiores de Next/Tailwind e precisam de trabalho dedicado e testes de compatibilidade; não foi aplicado `--force`.
- Integrações externas de vídeos, Gemini e YouTube **não testadas ao vivo**: ambiente sem acesso a esses hosts e sem credenciais fornecidas. Testes HTTP usam respostas simuladas.
- FFmpeg não está instalado neste sandbox: composição audiovisual real e qualidade da narração não foram validadas. O caminho de falha por ausência do executável está coberto.

## Limitações e pendências importantes

1. **Relevância não é prova visual:** tags e slug podem ser incorretos. O filtro não analisa os frames, não identifica pessoas/localizações e não comprova que a cena mostra o fato noticiado. Para material específico de um acontecimento, usar fonte/licença comprovada e revisão humana. A política atual prefere omitir imagens a adivinhar.
2. **Licenças:** Pixabay/Pexels não significam automaticamente domínio público/CC0. Revisar condições, atribuições e direitos de imagem de cada material. Sidecar JSON do clipe registra provedor, consulta e URL de origem do download, mas não substitui auditoria jurídica.
3. **API administrativa sem autenticação aplicada às rotas operacionais:** manter restrita à rede local/VPN ou proxy autenticado. Não expor diretamente na internet antes de implementar autenticação/autorização e proteção do OAuth.
4. **Criptografia legada:** chaves de desenvolvimento e fallback que aceita credenciais não cifradas continuam exigindo endurecimento e plano de migração antes de produção.
5. **Concorrência e publicação:** múltiplos workers podem criar jobs diferentes para o mesmo conteúdo. Ainda é necessário lock transacional/fila e idempotência estável projeto/conta. A checagem adicionada evita repetição do mesmo job concluído, não garante exactly-once.
6. **Limite diário e emergência:** revisão do reset do contador diário, persistência compartilhada da parada entre workers e cancelamento de upload em andamento continua necessária. O botão não oferece a garantia absoluta descrita anteriormente no README.
7. **Produção editorial/verificação:** revisão humana continua importante; o fallback editorial contém afirmações genéricas de apuração e urgência que não equivalem a checagem independente. Não usar a pontuação heurística como garantia factual.
8. **Dependências frontend:** não considerar o sistema pronto para exposição pública enquanto os alertas críticos/altos e controles de acesso não forem resolvidos.

## Operação recomendada

- Começar em `AGENT_MODE=SIMULATION`; usar ASSISTED com revisão editorial para notícias sensíveis.
- Configurar `PEXELS_API_KEY` e/ou `PIXABAY_API_KEY` no ambiente do backend. Sem chave válida, o resultado esperado é cartela, não vídeo aleatório.
- Instalar FFmpeg/ffprobe (o Dockerfile já inclui FFmpeg).
- Consultar `backend/tests/test_video_relevance.py` para ampliar os conceitos com exemplos positivos, negativos e ambíguos. Não adicionar fallback genérico para aumentar artificialmente a taxa de vídeos encontrados.
- A política aceita menos imagens intencionalmente: educação não deve receber bolsa financeira, juros não devem receber escritório genérico, futebol não deve receber corrida, chuva não deve receber incêndio.
