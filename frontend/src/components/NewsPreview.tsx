"use client";

import { useEffect, useState } from "react";
import { Video, RefreshCw, Send, Eye } from "lucide-react";

type News = { project_id: string; title: string; summary?: string };
type Preview = { headline: string; summary: string; ready: boolean; video_url: string | null };
type Props = {
  items: News[];
  selectedId: string;
  onSelect: (id: string) => void;
  refreshKey: number;
  mode: string;
  stopped: boolean;
  busy: boolean;
  onRender: (id: string, vertical: boolean) => Promise<void>;
  onPublish: (id: string) => Promise<void>;
};

export default function NewsPreview({ items, selectedId, onSelect, refreshKey, mode, stopped, busy, onRender, onPublish }: Props) {
  const [vertical, setVertical] = useState(true);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [playable, setPlayable] = useState(false);
  const [reload, setReload] = useState(0);
  const item = items.find((entry) => entry.project_id === selectedId);

  useEffect(() => {
    const controller = new AbortController();
    setPreview(null);
    setReviewed(false);
    setPlayable(false);
    setError("");
    if (!selectedId) { setLoading(false); return; }
    setLoading(true);
    fetch(`/api/v1/content-projects/${encodeURIComponent(selectedId)}/preview?is_vertical=${vertical}`, { signal: controller.signal })
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Não foi possível carregar a prévia.");
        if (!controller.signal.aborted) setPreview(data);
      })
      .catch((err) => { if (!controller.signal.aborted) setError(err.message || "Falha de conexão."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [selectedId, vertical, refreshKey, reload]);

  return (
    <section id="news-preview" aria-labelledby="preview-title" className="rounded-2xl border border-sky-900/60 bg-slate-900 p-5 space-y-4 scroll-mt-24">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="preview-title" className="font-bold flex items-center gap-2"><Eye className="h-4 w-4 text-sky-400" /> Prévia antes de publicar</h2>
          <p className="text-xs text-slate-400 mt-1">Confira a notícia, as imagens e a narração sem sair do painel.</p>
        </div>
        <select aria-label="Notícia para pré-visualizar" value={selectedId} onChange={(e) => onSelect(e.target.value)} disabled={busy} className="max-w-full w-full sm:w-80 bg-slate-950 border border-slate-700 rounded-lg p-2 text-xs disabled:opacity-50">
          <option value="">Selecione uma notícia com roteiro</option>
          {items.map((entry) => <option key={entry.project_id} value={entry.project_id}>{entry.title}</option>)}
        </select>
      </div>
      {!selectedId ? (
        <div className="rounded-xl border border-dashed border-slate-700 p-6 text-center text-sm text-slate-400">{items.length ? "Selecione uma notícia acima ou clique em ‘Prévia’ na lista." : "Produza o conteúdo de uma notícia para visualizar o vídeo aqui."}</div>
      ) : (
        <div className="grid md:grid-cols-[240px_1fr] gap-5">
          <div className="rounded-xl bg-black border border-slate-800 h-64 flex items-center justify-center overflow-hidden">
            {preview?.video_url ? (
              <video key={preview.video_url} src={preview.video_url} controls playsInline preload="metadata" aria-label={`Vídeo da notícia: ${preview.headline}`} className="w-full h-full object-contain" onLoadedData={() => setPlayable(true)} onError={() => { setPlayable(false); setReviewed(false); setError("O vídeo não pôde ser reproduzido. Tente atualizar ou gerar novamente."); }}>
                Seu navegador não suporta reprodução de vídeo.
              </video>
            ) : (
              <div className="text-center p-4 text-xs text-slate-400"><Video className="w-8 h-8 mx-auto mb-3 text-slate-600" />{loading ? "Carregando prévia…" : "Vídeo ainda não gerado para este formato."}</div>
            )}
          </div>
          <div className="space-y-3 min-w-0">
            <div className="flex gap-2">
              {[true, false].map((value) => <button key={String(value)} type="button" disabled={busy} onClick={() => { setVertical(value); setPreview(null); setReviewed(false); setPlayable(false); }} aria-pressed={vertical === value} className={`px-3 py-1.5 rounded-lg text-xs font-bold disabled:opacity-50 ${vertical === value ? "bg-sky-600 text-white" : "bg-slate-800 text-slate-300"}`}>{value ? "9:16 Shorts" : "16:9 YouTube"}</button>)}
              <button type="button" disabled={loading || busy} onClick={() => setReload((n) => n + 1)} title="Atualizar prévia" aria-label="Atualizar prévia" className="p-2 rounded-lg bg-slate-800 disabled:opacity-50"><RefreshCw className="w-3.5 h-3.5" /></button>
            </div>
            <h3 className="text-sm font-bold text-white leading-snug">{preview?.headline || item?.title}</h3>
            <p className="text-xs text-slate-400 whitespace-pre-line max-h-24 overflow-y-auto">{preview?.summary || item?.summary}</p>
            <p className="text-[11px] text-slate-500">Imagens de banco são ilustrativas, não uma comprovação visual do acontecimento.</p>
            {mode === "AUTONOMOUS" && <p className="text-xs text-amber-300">O modo Autônomo pode publicar sem aguardar sua revisão. Use o modo Assistido para revisar antes do envio.</p>}
            {!vertical && <p className="text-xs text-amber-300">O envio atual utiliza 9:16. Selecione e revise essa versão para publicar.</p>}
            {error && <p role="alert" className="text-xs text-red-300">{error}</p>}
            <div className="flex flex-wrap gap-3 items-center">
              <button type="button" disabled={busy || loading} onClick={() => onRender(selectedId, vertical)} className="px-3 py-2 bg-sky-600 hover:bg-sky-500 rounded-lg text-xs font-bold disabled:opacity-50">{busy ? "Processando…" : preview?.ready ? "Abrir vídeo gerado" : "Gerar prévia do vídeo"}</button>
              <label className="text-xs text-slate-300 flex items-center gap-2"><input type="checkbox" checked={reviewed} disabled={!playable || !vertical || busy || loading} onChange={(e) => setReviewed(e.target.checked)} /> Revisei esta notícia e este vídeo</label>
              <button type="button" disabled={!reviewed || !playable || !vertical || busy || loading || stopped} onClick={() => { setReviewed(false); onPublish(selectedId); }} className="flex items-center gap-2 px-3 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-lg text-xs font-bold disabled:opacity-40 disabled:cursor-not-allowed"><Send className="w-3.5 h-3.5" />{mode === "SIMULATION" ? "Simular publicação" : "Confirmar publicação"}</button>
            </div>
            {stopped && <p className="text-xs text-red-300">Publicação bloqueada pela parada de emergência.</p>}
          </div>
        </div>
      )}
    </section>
  );
}
