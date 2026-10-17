"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Sparkles, LockKeyhole, RefreshCw, Play, Send, CheckCircle2 } from "lucide-react";

type Status = { privacy_status?: string; enabled: boolean; categories: string[]; research_hosts: string[]; daily_call_limit: number; daily_budget_microusd: number; capabilities: { gemini_configured: boolean; ffmpeg: boolean; ffprobe: boolean } };
type Source = { url: string; title: string; excerpt: string; retrieved_at: string };
type Production = { id: string; title: string; category: string; nature: string; phase: string; score: number; origin: string; source_urls: string[]; research: Source[]; is_vertical: boolean; project_id: string | null; error: string | null; attempts: number; draft: { title?: string; short_script?: string; long_script?: string; thumbnail_text?: string; scenes?: { narration: string; visual: string }[] }; quality_report: { passed?: boolean; issues?: string[]; uncertainties?: string[]; claim_checks?: { text: string; status: string }[]; technical?: { passed: boolean; issues: string[] } }; metrics: Record<string, unknown> };
const labels: Record<string, string> = { historia: "Mistérios históricos e arqueologia", ciencia: "Curiosidades científicas", tecnologia: "IA e tecnologia", espaco: "Espaço e universo", hipoteses: "E se…? Cenários hipotéticos", futuro: "Futuro da humanidade", natureza: "Fenômenos naturais", invencoes: "Invenções e descobertas", cerebro: "Psicologia e cérebro", cotidiano: "Perguntas do cotidiano" };
const phases: Record<string, string> = { QUEUED: "Na fila", GENERATING: "Pesquisando / gerando", REVIEW_REQUIRED: "Aguardando revisão", QUALITY_BLOCKED: "Bloqueado pela qualidade", APPROVED: "Aprovado para renderizar", RENDERING: "Renderizando", READY: "Pronto para publicar", PUBLISHING: "Enviando", PUBLISHED: "Publicado", SIMULATED: "Envio simulado", FAILED: "Falha na geração", RENDER_FAILED: "Falha na renderização", UPLOAD_UNKNOWN: "Envio não confirmado — revisar canal" };

export default function OriginalContentFactory({ agentMode }: { agentMode: string }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [keyInput, setKeyInput] = useState("");
  const [key, setKey] = useState("");
  const [items, setItems] = useState<Production[]>([]);
  const [accounts, setAccounts] = useState<{ id: string; name: string }[]>([]);
  const [account, setAccount] = useState("");
  const [usage, setUsage] = useState({ calls: 0, reserved_microusd: 0 });
  const [selectedId, setSelectedId] = useState("");
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("ciencia");
  const [nature, setNature] = useState("FACTUAL");
  const [urls, setUrls] = useState("");
  const [vertical, setVertical] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [checks, setChecks] = useState([false, false, false]);
  const [video, setVideo] = useState("");
  const [thumbnail, setThumbnail] = useState("");
  const [watched, setWatched] = useState(false);
  const mediaRequest = useRef<AbortController | null>(null);
  const selected = items.find((p) => p.id === selectedId);

  useEffect(() => {
    fetch("/api/v1/factory/status").then(async (r) => { if (!r.ok) throw new Error(); setStatus(await r.json()); })
      .catch(() => setMessage("Não foi possível consultar a fábrica. Atualize o backend e verifique a conexão."));
  }, []);

  const request = useCallback(async (path: string, body?: unknown, token = key) => {
    const response = await fetch(`/api/v1/factory${path}`, { method: body === undefined ? "GET" : "POST", headers: { "X-Factory-Key": token, "Content-Type": "application/json" }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Solicitação inválida. Confira os campos e a configuração.");
    return data;
  }, [key]);

  const refresh = useCallback(async (token = key) => {
    const data = await request("/productions", undefined, token);
    setItems(data.items); setAccounts(data.accounts); setUsage(data.usage);
    setSelectedId((current) => current || data.items[0]?.id || "");
  }, [key, request]);

  useEffect(() => {
    if (!key) return;
    const timer = setInterval(() => { refresh().catch(() => {}); }, 15000);
    return () => clearInterval(timer);
  }, [key, refresh]);

  useEffect(() => {
    mediaRequest.current?.abort(); setVideo(""); setThumbnail(""); setWatched(false); setChecks([false, false, false]);
  }, [selectedId, key]);
  useEffect(() => () => { if (video) URL.revokeObjectURL(video); }, [video]);
  useEffect(() => () => { if (thumbnail) URL.revokeObjectURL(thumbnail); }, [thumbnail]);
  useEffect(() => () => mediaRequest.current?.abort(), []);

  const action = async (path: string, body: unknown = {}) => {
    setBusy(true); setMessage("");
    try {
      const data = await request(path, body);
      setMessage(data.error || data.result?.error || `Operação concluída${data.phase ? `: ${phases[data.phase] || data.phase}` : "."}`);
      await refresh();
      return data;
    } catch (err) { setMessage(err instanceof Error ? err.message : "Falha na operação."); }
    finally { setBusy(false); }
  };

  const loadMedia = async () => {
    if (!selected?.project_id) return;
    mediaRequest.current?.abort();
    const controller = new AbortController(); mediaRequest.current = controller;
    setBusy(true); setMessage(""); setWatched(false);
    try {
      const headers = { "X-Factory-Key": key };
      const response = await fetch(`/api/v1/content-projects/${selected.project_id}/preview?is_vertical=${selected.is_vertical}`, { headers, signal: controller.signal });
      const data = await response.json();
      if (!response.ok || !data.video_url) throw new Error(data.detail || "Renderize o vídeo aprovado para liberar a prévia.");
      // Auth headers cannot be set on a <video src>. Use an authenticated blob,
      // never put the administrative credential in a URL or localStorage.
      const media = await fetch(data.video_url, { headers, signal: controller.signal });
      if (!media.ok) throw new Error("Não foi possível abrir o vídeo.");
      const blob = await media.blob();
      if (!controller.signal.aborted) setVideo(URL.createObjectURL(blob));
      const image = await fetch(`/api/v1/factory/productions/${selected.id}/thumbnail`, { headers, signal: controller.signal });
      if (image.ok) {
        const imageBlob = await image.blob();
        if (!controller.signal.aborted) setThumbnail(URL.createObjectURL(imageBlob));
      }
    } catch (err) { if (!controller.signal.aborted) setMessage(err instanceof Error ? err.message : "Falha na prévia."); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  };

  return <div className="space-y-6">
    <div className="rounded-2xl border border-violet-800/50 bg-gradient-to-br from-violet-950/60 to-slate-900 p-6">
      <div className="flex items-center gap-3"><Sparkles className="text-violet-300" /><div><h2 className="text-xl font-bold">Fábrica de Conteúdo Original</h2><p className="text-xs text-slate-400 mt-1">Módulo 2 · Pesquisa, roteiro original, revisão e produção para YouTube</p></div></div>
      <p className="text-xs text-slate-300 mt-4">Vídeos explicativos sem apresentador, em português brasileiro. Hipóteses são identificadas; evidências e direitos exigem revisão humana. A pontuação não é promessa de viralização.</p>
      <div className="mt-4 flex flex-wrap gap-2 text-xs">{[status?.enabled ? "Módulo habilitado" : "Desativado por padrão", `Modo: ${agentMode}`, `Privacidade do envio: ${status?.privacy_status || "private"}`, "Gráficos próprios · sem trilha não licenciada"].map((text) => <span key={text} className="rounded-full bg-slate-800 px-3 py-1">{text}</span>)}</div>
    </div>
    {message && <p role="status" className="rounded-xl border border-sky-900 bg-sky-950/40 p-3 text-sm text-sky-200">{message}</p>}
    {!status?.enabled ? <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900 space-y-3"><h3 className="font-bold">Configuração necessária no backend</h3><p className="text-sm text-slate-400">Defina FACTORY_ENABLED=true, uma FACTORY_ADMIN_KEY própria (mínimo de 32 caracteres), GEMINI_API_KEY e os limites diários de chamadas/orçamento. Instale FFmpeg e ffprobe. Reinicie o backend.</p><p className="text-xs text-amber-300">Nenhum serviço pago é chamado apenas por abrir este painel. Consulte docs/ORIGINAL_CONTENT_FACTORY.md.</p></div> : !key ? (
      <form className="p-6 rounded-2xl border border-slate-800 bg-slate-900 space-y-3 max-w-xl" onSubmit={async (e) => { e.preventDefault(); setBusy(true); try { await refresh(keyInput); setKey(keyInput); setKeyInput(""); setMessage(""); } catch (err) { setMessage(err instanceof Error ? err.message : "Acesso negado."); } finally { setBusy(false); } }}>
        <h3 className="font-bold flex items-center gap-2"><LockKeyhole className="w-4 h-4" /> Acesso à fábrica</h3><label className="block text-xs text-slate-400">Chave administrativa<input required type="password" autoComplete="off" value={keyInput} onChange={(e) => setKeyInput(e.target.value)} className="mt-2 block w-full p-3 bg-slate-950 border border-slate-700 rounded-lg" /></label><p className="text-xs text-slate-500">A chave fica apenas na memória desta página. Não é salva no navegador nem colocada nos links.</p><button disabled={busy} className="rounded-lg bg-violet-600 px-4 py-2 text-sm disabled:opacity-50">{busy ? "Verificando…" : "Acessar"}</button>
      </form>
    ) : <>
      <div className="flex flex-wrap items-center gap-3 text-xs"><span>Chamadas hoje: {usage.calls}/{status.daily_call_limit}</span><span>Reserva estimada: US$ {(usage.reserved_microusd / 1e6).toFixed(2)} / {(status.daily_budget_microusd / 1e6).toFixed(2)}</span><button disabled={busy} onClick={() => refresh().catch((e) => setMessage(e.message))} className="p-2 rounded-lg bg-slate-800 flex gap-2"><RefreshCw className="w-3 h-3" /> Atualizar</button><button disabled={busy} onClick={() => { mediaRequest.current?.abort(); setKey(""); setItems([]); }} className="p-2 text-slate-400">Sair da fábrica</button></div>
      {(!status.capabilities.gemini_configured || !status.capabilities.ffmpeg || !status.capabilities.ffprobe) && <p className="text-xs text-amber-300">Há pré-requisitos indisponíveis: Gemini configurado {status.capabilities.gemini_configured ? "✓" : "✕"}, FFmpeg {status.capabilities.ffmpeg ? "✓" : "✕"}, ffprobe {status.capabilities.ffprobe ? "✓" : "✕"}.</p>}
      <form className="rounded-2xl bg-slate-900 border border-slate-800 p-5 space-y-3" onSubmit={async (e) => { e.preventDefault(); const data = await action("/topics", { title, category, nature, source_urls: urls.split("\n").map((s) => s.trim()).filter(Boolean), is_vertical: vertical }); if (data?.id) { setSelectedId(data.id); setTitle(""); setUrls(""); } }}>
        <h3 className="font-bold">Nova ideia de conteúdo</h3><input aria-label="Tema do vídeo original" required minLength={10} maxLength={300} value={title} disabled={busy} onChange={(e) => setTitle(e.target.value)} placeholder="Por que os planetas têm cores diferentes?" className="w-full bg-slate-950 border border-slate-700 rounded-lg p-3 text-sm" />
        <div className="grid sm:grid-cols-3 gap-3"><select aria-label="Categoria original" value={category} disabled={busy} onChange={(e) => { setCategory(e.target.value); if (e.target.value === "hipoteses") setNature("HYPOTHESIS"); }} className="bg-slate-950 border border-slate-700 rounded-lg p-2 text-xs">{status.categories.map((c) => <option key={c} value={c}>{labels[c] || c}</option>)}</select><select aria-label="Natureza do conteúdo" value={nature} disabled={busy} onChange={(e) => setNature(e.target.value)} className="bg-slate-950 border border-slate-700 rounded-lg p-2 text-xs"><option value="FACTUAL">Explicação factual</option><option value="HYPOTHESIS">Hipótese / simulação</option><option value="FICTION">Ficção identificada</option></select><select aria-label="Formato original" value={String(vertical)} disabled={busy} onChange={(e) => setVertical(e.target.value === "true")} className="bg-slate-950 border border-slate-700 rounded-lg p-2 text-xs"><option value="true">9:16 · Shorts</option><option value="false">16:9 · YouTube</option></select></div>
        <textarea aria-label="Fontes de pesquisa" disabled={busy} value={urls} onChange={(e) => setUrls(e.target.value)} rows={3} placeholder="URLs HTTPS de pesquisa, uma por linha (até 5)" className="w-full bg-slate-950 border border-slate-700 rounded-lg p-3 text-xs" /><p className="text-[11px] text-slate-500">Domínios permitidos: {status.research_hosts.join(", ")}. Uma fonte não concede licença para copiar suas imagens ou textos.</p>
        <div className="flex flex-wrap gap-2"><button disabled={busy} className="rounded-lg bg-violet-600 px-3 py-2 text-xs font-bold disabled:opacity-50">Adicionar à fila</button><button type="button" disabled={busy} onClick={() => action("/discover")} className="rounded-lg bg-slate-800 px-3 py-2 text-xs disabled:opacity-50">Encontrar temas nos feeds existentes</button><button type="button" disabled={busy} onClick={() => action("/run-next")} className="rounded-lg bg-sky-600 px-3 py-2 text-xs font-bold disabled:opacity-50">{busy ? "Processando…" : "Processar próxima etapa"}</button></div>
      </form>
      <div className="grid lg:grid-cols-[280px_1fr] gap-5">
        <div className="space-y-2"><h3 className="font-bold text-sm">Produções ({items.length})</h3>{!items.length && <p className="text-xs text-slate-500">Adicione um tema ou descubra ideias nos feeds de fontes permitidas.</p>}{items.map((p) => <button key={p.id} disabled={busy} onClick={() => setSelectedId(p.id)} className={`w-full text-left rounded-xl border p-3 space-y-2 ${p.id === selectedId ? "border-violet-500 bg-violet-950/30" : "border-slate-800 bg-slate-900"}`}><p className="text-sm font-semibold">{p.title}</p><p className="text-[11px] text-slate-400">{phases[p.phase] || p.phase} · {p.is_vertical ? "9:16" : "16:9"} · Score {p.score}</p></button>)}</div>
        {selected && <div className="rounded-2xl bg-slate-900 border border-slate-800 p-5 space-y-4 min-w-0"><h3 className="font-bold">{selected.draft.title || selected.title}</h3><p className="text-xs text-violet-300">{phases[selected.phase] || selected.phase} · {selected.nature} · {labels[selected.category]}</p>{selected.error && <p role="alert" className="text-xs text-red-300">{selected.error}</p>}
          {(selected.quality_report.issues || []).map((issue) => <p key={issue} className="text-xs text-amber-300">• {issue}</p>)}
          <details><summary className="text-sm cursor-pointer">Pesquisa, evidências e roteiro</summary><div className="mt-3 space-y-3 text-xs text-slate-400">{selected.research.map((s) => <div key={s.url}><a href={s.url} target="_blank" rel="noopener noreferrer" className="text-sky-400 break-all">{s.title}</a><p>Consulta: {s.retrieved_at}</p><p className="line-clamp-3">{s.excerpt}</p></div>)}<h4>Roteiro {selected.is_vertical ? "curto" : "longo"}</h4><p className="whitespace-pre-wrap">{selected.is_vertical ? selected.draft.short_script : selected.draft.long_script}</p>{selected.quality_report.claim_checks?.map((c, i) => <p key={i}>{c.status}: {c.text}</p>)}{selected.quality_report.uncertainties?.map((s) => <p key={s}>Incerteza: {s}</p>)}</div></details>
          {selected.phase === "REVIEW_REQUIRED" && <div className="border border-amber-900/50 rounded-xl p-4 space-y-3"><h4 className="text-sm font-bold">Revisão editorial obrigatória</h4><p className="text-xs text-amber-300">Correspondência com uma citação não prova que a afirmação é verdadeira. Confira as fontes, os dois roteiros e as hipóteses antes de aprovar.</p><input aria-label="Nome do revisor" value={reviewer} onChange={(e) => setReviewer(e.target.value)} placeholder="Nome do responsável pela revisão" className="w-full p-2 rounded-lg bg-slate-950 text-sm" />{["Conferi os fatos e separei hipóteses de evidências", "Conferi os direitos de uso dos materiais", "Revisei os roteiros e as divulgações de IA"].map((label, i) => <label key={label} className="flex items-center gap-2 text-xs"><input type="checkbox" checked={checks[i]} onChange={(e) => setChecks(checks.map((v, j) => j === i ? e.target.checked : v))} />{label}</label>)}<button disabled={busy || reviewer.trim().length < 3 || !checks.every(Boolean)} onClick={() => action(`/productions/${selected.id}/approve`, { reviewer, facts_checked: checks[0], rights_checked: checks[1], script_reviewed: checks[2] })} className="flex items-center gap-2 rounded-lg bg-emerald-700 px-3 py-2 text-xs disabled:opacity-40"><CheckCircle2 className="w-4 h-4" /> Aprovar roteiro</button></div>}
          <div className="flex flex-wrap gap-3">{selected.phase === "APPROVED" && <button disabled={busy} onClick={() => action(`/productions/${selected.id}/render`)} className="bg-sky-600 rounded-lg px-3 py-2 text-xs disabled:opacity-40">Renderizar vídeo e miniatura</button>}{["READY", "PUBLISHED", "SIMULATED"].includes(selected.phase) && <button disabled={busy} onClick={loadMedia} className="bg-slate-800 rounded-lg px-3 py-2 text-xs flex gap-2 disabled:opacity-40"><Play className="w-4 h-4" /> Carregar prévia</button>}{["FAILED", "RENDER_FAILED"].includes(selected.phase) && <button disabled={busy} onClick={() => action(`/productions/${selected.id}/retry`)} className="bg-slate-800 rounded-lg px-3 py-2 text-xs">Recolocar na fila</button>}</div>
          {video && <div className="grid md:grid-cols-2 gap-3"><video src={video} controls playsInline className="w-full max-h-80 bg-black rounded-xl" onPlaying={() => setWatched(true)} onError={() => { setWatched(false); setMessage("Falha na reprodução. Não publique antes de conferir o vídeo."); }} aria-label="Prévia do conteúdo original" />{thumbnail && <img src={thumbnail} alt="Miniatura original gerada" className="rounded-xl w-full object-contain max-h-60" />}</div>}
          {selected.phase === "READY" && <div className="flex flex-wrap gap-3 items-center"><select aria-label="Canal de destino da fábrica" value={account} onChange={(e) => setAccount(e.target.value)} className="bg-slate-950 border border-slate-700 p-2 rounded-lg text-xs"><option value="">Selecione o canal YouTube</option>{accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select><button disabled={busy || !account || !watched} onClick={() => action(`/productions/${selected.id}/publish`, { account_id: account })} className="bg-emerald-700 px-3 py-2 rounded-lg text-xs flex gap-2 disabled:opacity-40"><Send className="w-4 h-4" />{agentMode === "SIMULATION" ? "Simular envio" : "Publicar versão aprovada"}</button><p className="text-[11px] text-slate-500">Assista à prévia para habilitar o envio manual. A rotina automática só envia após aprovação editorial e configuração explícita.</p></div>}
          {selected.phase === "SIMULATED" && agentMode !== "SIMULATION" && <button disabled={busy} onClick={() => action(`/productions/${selected.id}/retry`)} className="text-xs bg-amber-800 rounded-lg p-2">Preparar esta produção para envio real</button>}
          {selected.phase === "PUBLISHED" && <button disabled={busy} onClick={() => action(`/productions/${selected.id}/metrics`)} className="text-xs bg-slate-800 rounded-lg p-2">Atualizar métricas reais do YouTube</button>}{Object.keys(selected.metrics || {}).length > 0 && <pre className="overflow-auto text-xs text-slate-400">{JSON.stringify(selected.metrics, null, 2)}</pre>}
        </div>}
      </div>
    </>}
  </div>;
}
