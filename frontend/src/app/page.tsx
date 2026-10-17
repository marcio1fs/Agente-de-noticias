"use client";

import React, { useState, useEffect } from "react";
import NewsPreview from "../components/NewsPreview";
import OriginalContentFactory from "../components/OriginalContentFactory";
import {
  AlertTriangle,
  Radio,
  FileCheck2,
  Video,
  Send,
  ShieldAlert,
  BarChart3,
  Layers,
  Settings,
  Flame,
  CheckCircle2,
  RefreshCw,
  ExternalLink,
  Sliders,
  DollarSign,
  Play,
  Check,
  XCircle,
  FileText,
  Clock,
  Sparkles,
  Search
} from "lucide-react";

const API_BASE = "/api/v1";

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState("overview");
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<{ text: string; type: "success" | "error" } | null>(null);

  // Estados Globais da Aplicação
  const [stats, setStats] = useState({
    total_news_collected: 0,
    total_news_verified: 0,
    total_content_produced: 0,
    total_published: 0,
    total_quarantined: 0,
    total_blocked: 0,
    total_pending: 0,
    emergency_stop_active: false,
    agent_mode: "SIMULATION",
    total_cost_usd: 0.42
  });

  const [newsList, setNewsList] = useState<any[]>([]);
  const [sourcesList, setSourcesList] = useState<any[]>([]);
  const [categoriesList, setCategoriesList] = useState<any[]>([]);
  const [publishingAccounts, setPublishingAccounts] = useState<any[]>([]);
  const [previewProjectId, setPreviewProjectId] = useState("");
  const [previewRefresh, setPreviewRefresh] = useState(0);
  const openPreview = (projectId: string) => {
    setPreviewProjectId(projectId);
    document.getElementById("news-preview")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const [selectedNews, setSelectedNews] = useState<any | null>(null);
  const [selectedCategoryFilter, setSelectedCategoryFilter] = useState("ALL");
  const [selectedStatusFilter, setSelectedStatusFilter] = useState("ALL");

  // Carregar dados da API
  const fetchData = async () => {
    try {
      const statsRes = await fetch(`${API_BASE}/dashboard/stats`);
      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStats(statsData);
      }

      const newsRes = await fetch(`${API_BASE}/news?limit=50`);
      if (newsRes.ok) {
        const newsData = await newsRes.json();
        setNewsList(newsData);
      }

      const sourcesRes = await fetch(`${API_BASE}/sources`);
      if (sourcesRes.ok) {
        const sourcesData = await sourcesRes.json();
        setSourcesList(sourcesData);
      }

      const categoriesRes = await fetch(`${API_BASE}/categories`);
      if (categoriesRes.ok) {
        const catData = await categoriesRes.json();
        setCategoriesList(catData);
      }

      const accountsRes = await fetch(`${API_BASE}/publishing-accounts`);
      if (accountsRes.ok) {
        const accData = await accountsRes.json();
        setPublishingAccounts(accData);
      }
    } catch (err) {
      console.error("Erro ao conectar à API:", err);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 8000);

    // Verificar se retornou da autorização do YouTube
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const ytAuth = params.get("youtube_auth");
      if (ytAuth === "success") {
        const channel = params.get("channel") || "YouTube";
        showNotification(`Canal "${decodeURIComponent(channel)}" conectado com sucesso!`, "success");
        window.history.replaceState({}, document.title, window.location.pathname);
      } else if (ytAuth === "error") {
        const reason = params.get("reason") || "Falha na autorização";
        showNotification(`Erro ao conectar canal: ${decodeURIComponent(reason)}`, "error");
        window.history.replaceState({}, document.title, window.location.pathname);
      }
    }

    return () => clearInterval(interval);
  }, []);

  const showNotification = (text: string, type: "success" | "error" = "success") => {
    setActionMessage({ text, type });
    setTimeout(() => setActionMessage(null), 5000);
  };

  // 1. AÇÃO: Coletar Notícias Agora
  const handleTriggerDiscovery = async () => {
    setLoadingAction("discovery");
    try {
      const res = await fetch(`${API_BASE}/actions/trigger-discovery`, { method: "POST" });
      const data = await res.json();
      if (res.ok) {
        showNotification(data.message, "success");
        await fetchData();
      } else {
        showNotification(data.detail || "Erro ao coletar notícias", "error");
      }
    } catch (err: any) {
      showNotification("Falha na requisição ao backend. Verifique se o servidor está ativo na porta 8000.", "error");
    } finally {
      setLoadingAction(null);
    }
  };

  // 1.1 AÇÃO: Verificar Todas as Notícias Pendentes
  const handleVerifyAllPending = async () => {
    setLoadingAction("verify-all");
    try {
      const res = await fetch(`${API_BASE}/actions/verify-all-pending`, { method: "POST" });
      const data = await res.json();
      if (res.ok) {
        showNotification(data.message, "success");
        await fetchData();
      } else {
        showNotification(data.detail || "Erro ao verificar notícias", "error");
      }
    } catch (err: any) {
      showNotification("Falha ao comunicar com o servidor para verificação.", "error");
    } finally {
      setLoadingAction(null);
    }
  };

  // 1.2 AÇÃO: Disparar Pipeline Autônomo Completo (Breaking News / Automação)
  const handleRunAutonomousPipeline = async () => {
    setLoadingAction("autonomous-pipeline");
    try {
      const res = await fetch(`${API_BASE}/actions/run-autonomous-pipeline?limit=30`, { method: "POST" });
      const data = await res.json();
      if (res.ok) {
        showNotification(`Pipeline concluído: ${data.processed_count} notícias processadas e direcionadas.`, "success");
        await fetchData();
      } else {
        showNotification(data.detail || "Erro ao rodar pipeline autônomo", "error");
      }
    } catch (err: any) {
      showNotification("Falha na comunicação com o backend.", "error");
    } finally {
      setLoadingAction(null);
    }
  };

  // 2. AÇÃO: Alternar Parada de Emergência
  const handleToggleEmergency = async () => {
    setLoadingAction("emergency");
    const nextState = !stats.emergency_stop_active;
    try {
      const res = await fetch(`${API_BASE}/system/emergency-stop?active=${nextState}`, { method: "POST" });
      const data = await res.json();
      if (res.ok) {
        setStats((prev) => ({ ...prev, emergency_stop_active: nextState }));
        showNotification(data.message, nextState ? "error" : "success");
      }
    } catch (err) {
      showNotification("Erro ao acionar parada de emergência", "error");
    } finally {
      setLoadingAction(null);
    }
  };

  // 3. AÇÃO: Alternar Modo do Agente (Simulação, Assistido, Autônomo)
  const handleChangeMode = async (mode: string) => {
    setLoadingAction("mode");
    try {
      const res = await fetch(`${API_BASE}/system/agent-mode`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode })
      });
      const data = await res.json();
      if (res.ok) {
        setStats((prev) => ({ ...prev, agent_mode: mode }));
        showNotification(data.message, "success");
      }
    } catch (err) {
      showNotification("Erro ao alterar modo", "error");
    } finally {
      setLoadingAction(null);
    }
  };

  // 4. AÇÃO: Verificar Notícia Específica
  const handleVerifyNews = async (item: any) => {
    setLoadingAction(`verify_${item.id}`);
    try {
      const res = await fetch(`${API_BASE}/actions/verify/${item.id}`, { method: "POST" });
      const data = await res.json();
      if (res.ok) {
        showNotification(`Verificação concluída: ${data.verdict} (${data.score}% de confiança)`, "success");
        await fetchData();
      } else {
        showNotification(data.detail || "Erro na checagem", "error");
      }
    } catch (err) {
      showNotification("Erro ao checar notícia", "error");
    } finally {
      setLoadingAction(null);
    }
  };

  // 5. AÇÃO: Produzir Conteúdo & Roteiro
  const handleProduceContent = async (item: any) => {
    setLoadingAction(`produce_${item.id}`);
    try {
      const res = await fetch(`${API_BASE}/actions/produce-content/${item.id}`, { method: "POST" });
      const data = await res.json();
      if (res.ok) {
        showNotification(`Conteúdo e Roteiros 16:9 / 9:16 gerados com sucesso!`, "success");
        await fetchData();
      } else {
        showNotification(data.detail || "Erro ao produzir", "error");
      }
    } catch (err) {
      showNotification("Erro ao produzir conteúdo", "error");
    } finally {
      setLoadingAction(null);
    }
  };

  // 6. AÇÃO: Renderizar Vídeo
  const handleRenderVideo = async (projectId: string, isVertical: boolean = false) => {
    setLoadingAction(`render_${projectId}`);
    try {
      const res = await fetch(`${API_BASE}/actions/render-video/${projectId}?is_vertical=${isVertical}`, { method: "POST" });
      const data = await res.json();
      if (res.ok) {
        showNotification(`Vídeo ${data.format} e narração gerados com sucesso!`, "success");
        openPreview(projectId);
        setPreviewRefresh((n) => n + 1);
        await fetchData();
      } else {
        showNotification(data.detail || "Erro ao renderizar vídeo", "error");
      }
    } catch (err) {
      showNotification("Erro na renderização", "error");
    } finally {
      setLoadingAction(null);
    }
  };

  // 6.1. AÇÃO: Renderizar Todos os Roteiros Pendentes
  const handleRenderAllPending = async () => {
    const projectsToRender = newsList.filter((n) => n.has_content && n.project_id);
    if (projectsToRender.length === 0) {
      showNotification("Nenhum roteiro produzido disponível para renderizar. Clique em 'Produzir Conteúdo' primeiro em uma notícia.", "error");
      return;
    }

    setLoadingAction("render_all");
    showNotification(`Iniciando renderização de ${projectsToRender.length} vídeos com narração...`, "success");

    let successCount = 0;
    for (const item of projectsToRender) {
      try {
        const res = await fetch(`${API_BASE}/actions/render-video/${item.project_id}?is_vertical=true`, { method: "POST" });
        if (res.ok) successCount++;
      } catch (e) {
        console.error(e);
      }
    }

    setLoadingAction(null);
    showNotification(`Concluído! ${successCount} de ${projectsToRender.length} vídeos renderizados com áudio e cartela!`, "success");
    await fetchData();
  };

  // 7. AÇÃO: Publicar nas Redes Sociais
  const handlePublish = async (projectId: string, isVertical: boolean = true) => {
    setLoadingAction(`publish_${projectId}`);
    try {
      const res = await fetch(`${API_BASE}/actions/publish/${projectId}?is_vertical=${isVertical}`, { method: "POST" });
      const data = await res.json();
      if (res.ok && data.success) {
        showNotification(`Publicado com sucesso em ${data.published_destinations?.filter((r: any) => r.details?.success).length || 0} canais!`, "success");
        await fetchData();
      } else {
        showNotification(data.detail || data.published_destinations?.find((r: any) => !r.details?.success)?.details?.error || "Nenhuma publicação foi concluída.", "error");
      }
    } catch (err) {
      showNotification("Erro ao publicar", "error");
    } finally {
      setLoadingAction(null);
    }
  };

  // 8. AÇÃO: Conectar Canal do YouTube
  const handleConnectYouTube = async () => {
    setLoadingAction("connect_youtube");
    try {
      const res = await fetch(`${API_BASE}/auth/youtube/login`);
      const data = await res.json();
      if (res.ok && data.auth_url) {
        window.location.href = data.auth_url;
      } else {
        showNotification(data.detail || "Erro ao iniciar autenticação do YouTube", "error");
      }
    } catch (err) {
      showNotification("Erro ao conectar com a API", "error");
    } finally {
      setLoadingAction(null);
    }
  };


  // Filtro de Notícias
  const filteredNews = newsList.filter((item) => {
    if (selectedStatusFilter !== "ALL" && item.status !== selectedStatusFilter) return false;
    return true;
  });

  return (
    <div className="flex h-screen overflow-hidden bg-slate-950 text-slate-100 font-sans">
      {/* Toast de Notificação */}
      {actionMessage && (
        <div
          className={`fixed top-5 right-5 z-50 px-5 py-3 rounded-xl shadow-2xl border text-sm font-semibold flex items-center gap-3 transition-all animate-bounce ${
            actionMessage.type === "success"
              ? "bg-emerald-950/90 text-emerald-200 border-emerald-600/50"
              : "bg-red-950/90 text-red-200 border-red-600/50"
          }`}
        >
          {actionMessage.type === "success" ? <CheckCircle2 className="w-5 h-5 text-emerald-400" /> : <AlertTriangle className="w-5 h-5 text-red-400" />}
          {actionMessage.text}
        </div>
      )}

      {/* Modal de Detalhes da Notícia */}
      {selectedNews && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-40 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-6 space-y-4 shadow-2xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-start justify-between">
              <div>
                <span className="text-xs uppercase font-bold px-2 py-0.5 rounded bg-slate-800 text-slate-400">
                  Status: {selectedNews.status}
                </span>
                <h3 className="text-lg font-bold text-white mt-2 leading-snug">{selectedNews.title}</h3>
              </div>
              <button onClick={() => setSelectedNews(null)} className="text-slate-400 hover:text-white p-1">
                ✕
              </button>
            </div>

            <div className="bg-slate-950 p-4 rounded-xl border border-slate-800/80 text-sm text-slate-300">
              <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Resumo / Conteúdo Extraído:</h4>
              <p className="leading-relaxed">{selectedNews.summary || "Sem resumo disponível."}</p>
            </div>

            <div className="grid grid-cols-2 gap-4 text-xs">
              <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                <span className="text-slate-400 block font-semibold">Nível de Risco:</span>
                <span className="font-bold text-sm text-amber-400">{selectedNews.risk_level}</span>
              </div>
              <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                <span className="text-slate-400 block font-semibold">Confiança da IA:</span>
                <span className="font-bold text-sm text-emerald-400">{selectedNews.confidence_score ? `${selectedNews.confidence_score}%` : "Pendente"}</span>
              </div>
            </div>

            <div className="flex items-center justify-between pt-4 border-t border-slate-800">
              <a
                href={selectedNews.url}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-indigo-400 hover:underline flex items-center gap-1.5"
              >
                Abrir Fonte Original <ExternalLink className="w-3.5 h-3.5" />
              </a>

              <div className="flex gap-2">
                <button
                  onClick={() => {
                    handleVerifyNews(selectedNews);
                    setSelectedNews(null);
                  }}
                  className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold"
                >
                  Verificar Agora
                </button>
                <button
                  onClick={() => {
                    handleProduceContent(selectedNews);
                    setSelectedNews(null);
                  }}
                  className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold"
                >
                  Produzir Conteúdo
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Barra Lateral / Sidebar */}
      <aside className="w-72 bg-slate-900 border-r border-slate-800 flex flex-col">
        <div className="p-6 border-b border-slate-800 flex items-center gap-3">
          <div className="h-10 w-10 bg-indigo-600 rounded-xl flex items-center justify-center font-extrabold text-white shadow-lg shadow-indigo-500/30">
            IA
          </div>
          <div>
            <h1 className="font-bold text-base leading-tight">Redação Digital</h1>
            <p className="text-xs text-slate-400">Jornalismo Autônomo</p>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto p-4 space-y-1 text-sm font-medium">
          <button
            onClick={() => setActiveTab("overview")}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all ${
              activeTab === "overview" ? "bg-indigo-600 text-white shadow-lg shadow-indigo-600/20" : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            }`}
          >
            <Radio className="w-4 h-4" />
            Visão Geral da Operação
          </button>

          <button
            onClick={() => setActiveTab("news")}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all ${
              activeTab === "news" ? "bg-indigo-600 text-white shadow-lg shadow-indigo-600/20" : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            }`}
          >
            <Layers className="w-4 h-4" />
            Notícias Coletadas ({stats.total_news_collected})
          </button>

          <button
            onClick={() => setActiveTab("verification")}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all ${
              activeTab === "verification" ? "bg-indigo-600 text-white shadow-lg shadow-indigo-600/20" : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            }`}
          >
            <FileCheck2 className="w-4 h-4" />
            Checagem & Fatos ({stats.total_news_verified})
          </button>

          <button
            onClick={() => setActiveTab("videos")}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all ${
              activeTab === "videos" ? "bg-indigo-600 text-white shadow-lg shadow-indigo-600/20" : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            }`}
          >
            <Video className="w-4 h-4" />
            Gerenciador de Vídeos
          </button>

          <button
            onClick={() => setActiveTab("factory")}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all ${activeTab === "factory" ? "bg-violet-600 text-white shadow-lg" : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"}`}
          >
            <Sparkles className="w-4 h-4" />
            Fábrica de Conteúdo Original
          </button>

          <button
            onClick={() => setActiveTab("publishing")}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all ${
              activeTab === "publishing" ? "bg-indigo-600 text-white shadow-lg shadow-indigo-600/20" : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            }`}
          >
            <Send className="w-4 h-4" />
            Fila de Publicação ({stats.total_published})
          </button>

          <button
            onClick={() => setActiveTab("sources")}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all ${
              activeTab === "sources" ? "bg-indigo-600 text-white shadow-lg shadow-indigo-600/20" : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            }`}
          >
            <Search className="w-4 h-4" />
            Fontes & Categorias
          </button>

          <button
            onClick={() => setActiveTab("settings")}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all ${
              activeTab === "settings" ? "bg-indigo-600 text-white shadow-lg shadow-indigo-600/20" : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            }`}
          >
            <Sliders className="w-4 h-4" />
            Autonomia & Segurança
          </button>
        </nav>

        {/* Botão de Pânico / Parada de Emergência */}
        <div className="p-4 border-t border-slate-800 bg-slate-900/50">
          <button
            onClick={handleToggleEmergency}
            disabled={loadingAction === "emergency"}
            className={`w-full py-3 px-4 rounded-xl flex items-center justify-center gap-2 font-bold text-sm shadow-xl transition-all cursor-pointer ${
              stats.emergency_stop_active
                ? "bg-amber-600 hover:bg-amber-500 text-white animate-pulse"
                : "bg-red-600 hover:bg-red-500 text-white"
            }`}
          >
            <AlertTriangle className="w-5 h-5" />
            {stats.emergency_stop_active ? "EMERGÊNCIA ATIVA (PAUSADO)" : "PARADA DE EMERGÊNCIA"}
          </button>
        </div>
      </aside>

      {/* Conteúdo Principal */}
      <main className="flex-1 flex flex-col overflow-y-auto">
        {/* Header Superior com Controles Ativos */}
        <header className="h-16 border-b border-slate-800 px-8 flex items-center justify-between bg-slate-900/60 backdrop-blur-md sticky top-0 z-10">
          <div className="flex items-center gap-3">
            <span className="text-xs uppercase tracking-wider font-semibold text-slate-400">Modo Atual:</span>
            <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800">
              {["SIMULATION", "ASSISTED", "AUTONOMOUS"].map((m) => (
                <button
                  key={m}
                  onClick={() => handleChangeMode(m)}
                  className={`text-xs px-3 py-1 rounded-md font-bold transition-all ${
                    stats.agent_mode === m ? "bg-indigo-600 text-white shadow" : "text-slate-400 hover:text-white"
                  }`}
                >
                  {m === "SIMULATION" ? "Simulação" : m === "ASSISTED" ? "Assistido" : "Autônomo"}
                </button>
              ))}
            </div>

            {stats.emergency_stop_active && (
              <span className="text-xs uppercase tracking-wider font-bold px-2.5 py-1 rounded bg-red-500/20 text-red-400 border border-red-500/40 flex items-center gap-1.5 animate-pulse">
                <ShieldAlert className="w-3.5 h-3.5" /> Disparos Travados
              </span>
            )}
          </div>

          <div className="flex items-center gap-3">
            {/* BOTÃO PIPELINE AUTÔNOMO / MODO FURO */}
            <button
              onClick={handleRunAutonomousPipeline}
              disabled={loadingAction === "autonomous-pipeline"}
              className="flex items-center gap-2 text-xs bg-amber-600 hover:bg-amber-500 text-white font-bold px-4 py-2 rounded-xl shadow-lg shadow-amber-600/20 transition cursor-pointer"
            >
              <Sparkles className={`w-3.5 h-3.5 ${loadingAction === "autonomous-pipeline" ? "animate-spin" : ""}`} />
              {loadingAction === "autonomous-pipeline" ? "Executando Pipeline..." : "Disparar Pipeline Autônomo"}
            </button>

            {/* BOTÃO VERIFICAR PENDENTES */}
            <button
              onClick={handleVerifyAllPending}
              disabled={loadingAction === "verify-all"}
              className="flex items-center gap-2 text-xs bg-indigo-600 hover:bg-indigo-500 text-white font-bold px-4 py-2 rounded-xl shadow-lg shadow-indigo-600/20 transition cursor-pointer"
            >
              <CheckCircle2 className={`w-3.5 h-3.5 ${loadingAction === "verify-all" ? "animate-spin" : ""}`} />
              {loadingAction === "verify-all" ? "Verificando..." : "Verificar Pendentes"}
            </button>

            {/* BOTÃO COLETAR AGORA REAL */}
            <button
              onClick={handleTriggerDiscovery}
              disabled={loadingAction === "discovery"}
              className="flex items-center gap-2 text-xs bg-emerald-600 hover:bg-emerald-500 text-white font-bold px-4 py-2 rounded-xl shadow-lg shadow-emerald-600/20 transition cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingAction === "discovery" ? "animate-spin" : ""}`} />
              {loadingAction === "discovery" ? "Coletando Fontes..." : "Coletar Notícias Agora"}
            </button>
          </div>
        </header>

        {/* Container das Páginas */}
        <div className="p-8 space-y-8">
          {activeTab !== "factory" && <NewsPreview
            items={newsList.filter((n) => n.has_content && n.project_id)}
            selectedId={previewProjectId}
            onSelect={setPreviewProjectId}
            refreshKey={previewRefresh}
            mode={stats.agent_mode}
            stopped={stats.emergency_stop_active}
            busy={loadingAction !== null}
            onRender={handleRenderVideo}
            onPublish={handlePublish}
          />}
          {activeTab === "factory" && <OriginalContentFactory agentMode={stats.agent_mode} />}
          {/* ABA 1: VISÃO GERAL */}
          {activeTab === "overview" && (
            <>
              {/* Métricas Principais Conectadas à API */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
                <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl">
                  <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Notícias Coletadas</span>
                  <div className="text-3xl font-extrabold mt-2 text-white">{stats.total_news_collected}</div>
                  <p className="text-xs text-slate-400 mt-2">
                    {stats.total_pending} aguardando análise
                  </p>
                </div>

                <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl">
                  <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Verificadas & Fatos</span>
                  <div className="text-3xl font-extrabold mt-2 text-indigo-400">{stats.total_news_verified}</div>
                  <p className="text-xs text-slate-400 mt-2">
                    {stats.total_quarantined} em quarentena editorial
                  </p>
                </div>

                <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl">
                  <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Conteúdos & Roteiros</span>
                  <div className="text-3xl font-extrabold mt-2 text-sky-400">{stats.total_content_produced}</div>
                  <p className="text-xs text-slate-400 mt-2">16:9 (YouTube) e 9:16 (Shorts/Reels)</p>
                </div>

                <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl">
                  <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Publicações Realizadas</span>
                  <div className="text-3xl font-extrabold mt-2 text-emerald-400">{stats.total_published}</div>
                  <p className="text-xs text-slate-400 mt-2">Custo de IA: ${stats.total_cost_usd}</p>
                </div>
              </div>

              {/* Tabela Interativa de Notícias */}
              <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
                <div className="p-6 border-b border-slate-800 flex items-center justify-between">
                  <div>
                    <h2 className="text-lg font-bold">Fluxo Operacional em Tempo Real</h2>
                    <p className="text-xs text-slate-400 mt-1">
                      Execute ações diretamente nos cards: Checagem, Produção Editorial, Renderização e Publicação.
                    </p>
                  </div>

                  {/* Filtro por Status */}
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-slate-400">Filtrar:</span>
                    <select
                      value={selectedStatusFilter}
                      onChange={(e) => setSelectedStatusFilter(e.target.value)}
                      className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-slate-200"
                    >
                      <option value="ALL">Todos os Status</option>
                      <option value="PENDING">Pendentes</option>
                      <option value="READY_TO_PUBLISH">Prontos</option>
                      <option value="QUARANTINED">Quarentena</option>
                      <option value="BLOCKED">Bloqueados</option>
                    </select>
                  </div>
                </div>

                {filteredNews.length === 0 ? (
                  <div className="p-12 text-center text-slate-400 space-y-3">
                    <p>Nenhuma notícia encontrada com o filtro selecionado.</p>
                    <button
                      onClick={handleTriggerDiscovery}
                      className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-bold"
                    >
                      Coletar Notícias das Fontes Agora
                    </button>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <thead className="bg-slate-950/60 text-slate-400 uppercase text-xs font-semibold border-b border-slate-800">
                        <tr>
                          <th className="py-3 px-6">Notícia / Fato</th>
                          <th className="py-3 px-6">Confiança IA</th>
                          <th className="py-3 px-6">Risco</th>
                          <th className="py-3 px-6">Status</th>
                          <th className="py-3 px-6 text-right">Ações Rápidas</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800">
                        {filteredNews.map((item) => (
                          <tr key={item.id} className="hover:bg-slate-800/40 transition">
                            <td className="py-4 px-6 max-w-md">
                              <div
                                onClick={() => setSelectedNews(item)}
                                className="font-semibold text-slate-200 leading-snug cursor-pointer hover:text-indigo-400 transition"
                              >
                                {item.title}
                              </div>
                              <div className="text-xs text-slate-400 mt-1 flex items-center gap-2">
                                <a href={item.url} target="_blank" rel="noreferrer" className="hover:underline flex items-center gap-1">
                                  Fonte Original <ExternalLink className="w-2.5 h-2.5" />
                                </a>
                              </div>
                            </td>
                            <td className="py-4 px-6">
                              {item.confidence_score !== null ? (
                                <span className={`font-bold ${item.confidence_score >= 80 ? "text-emerald-400" : item.confidence_score >= 50 ? "text-amber-400" : "text-red-400"}`}>
                                  {item.confidence_score}%
                                </span>
                              ) : (
                                <span className="text-xs text-slate-500 italic">Não checado</span>
                              )}
                            </td>
                            <td className="py-4 px-6">
                              <span className={`text-xs px-2.5 py-1 rounded font-bold ${
                                item.risk_level === "LOW"
                                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                                  : item.risk_level === "MEDIUM"
                                  ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                                  : "bg-red-500/10 text-red-400 border border-red-500/20"
                              }`}>
                                {item.risk_level}
                              </span>
                            </td>
                            <td className="py-4 px-6">
                              <span className="text-xs font-semibold text-slate-300 bg-slate-800 px-2.5 py-1 rounded-md">
                                {item.status}
                              </span>
                            </td>
                            <td className="py-4 px-6 text-right">
                              <div className="flex items-center justify-end gap-2">
                                {/* Botão Verificar */}
                                <button
                                  onClick={() => handleVerifyNews(item)}
                                  disabled={loadingAction === `verify_${item.id}`}
                                  className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-indigo-300 rounded text-xs font-semibold border border-slate-700 transition"
                                >
                                  {loadingAction === `verify_${item.id}` ? "Checando..." : "Verificar"}
                                </button>

                                {/* Botão Produzir Roteiro */}
                                <button
                                  onClick={() => handleProduceContent(item)}
                                  disabled={loadingAction === `produce_${item.id}`}
                                  className="px-2.5 py-1 bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-300 rounded text-xs font-semibold border border-indigo-500/30 transition"
                                >
                                  {loadingAction === `produce_${item.id}` ? "Gerando..." : "Gerar Roteiro"}
                                </button>

                                {/* Botão Renderizar se tiver projeto */}
                                {item.has_content && item.project_id && (
                                  <button
                                    onClick={() => handleRenderVideo(item.project_id, true)}
                                    disabled={loadingAction === `render_${item.project_id}`}
                                    className="px-2.5 py-1 bg-sky-600/20 hover:bg-sky-600/40 text-sky-300 rounded text-xs font-semibold border border-sky-500/30 transition"
                                  >
                                    Renderizar
                                  </button>
                                )}

                                {/* Botão Publicar se tiver projeto */}
                                {item.has_content && item.project_id && (
                                  <button
                                    onClick={() => openPreview(item.project_id)}
                                    disabled={loadingAction === `publish_${item.project_id}`}
                                    className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-xs font-bold transition"
                                  >
                                    Prévia
                                  </button>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          )}

          {/* ABA 2: NOTÍCIAS COLETADAS */}
          {activeTab === "news" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-bold">Catálogo de Notícias Coletadas</h2>
                  <p className="text-xs text-slate-400 mt-1">Todas as matérias e despachos captados pelas fontes RSS/APIs.</p>
                </div>
                <button
                  onClick={handleTriggerDiscovery}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs rounded-xl flex items-center gap-2"
                >
                  <RefreshCw className="w-3.5 h-3.5" /> Nova Varredura
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {newsList.map((n) => (
                  <div key={n.id} className="bg-slate-900 border border-slate-800 p-5 rounded-xl space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-indigo-400 font-bold">{n.risk_level} RISCO</span>
                      <span className="text-xs bg-slate-800 px-2 py-0.5 rounded text-slate-400">{n.status}</span>
                    </div>
                    <h3 className="font-bold text-white text-base leading-snug">{n.title}</h3>
                    <p className="text-xs text-slate-400 line-clamp-2">{n.summary || "Sem texto complementar."}</p>
                    <div className="flex gap-2 pt-2 border-t border-slate-800">
                      <button
                        onClick={() => handleVerifyNews(n)}
                        className="px-3 py-1 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-xs font-semibold"
                      >
                        Verificar
                      </button>
                      <button
                        onClick={() => handleProduceContent(n)}
                        className="px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-xs font-semibold"
                      >
                        Produzir Conteúdo
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ABA 2.5: CHECAGEM & FATOS */}
          {activeTab === "verification" && (
            <div className="space-y-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <h2 className="text-xl font-bold flex items-center gap-2">
                    <FileCheck2 className="w-5 h-5 text-indigo-400" />
                    Central de Checagem & Fatos
                  </h2>
                  <p className="text-xs text-slate-400 mt-1">
                    Auditoria anti-fake news, análise de credibilidade, cálculo de risco e vereditos editoriais emitidos pela IA.
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={handleVerifyAllPending}
                    disabled={loadingAction === "verify-all"}
                    className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-bold text-xs rounded-xl flex items-center gap-2 shadow-lg shadow-indigo-600/20"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${loadingAction === "verify-all" ? "animate-spin" : ""}`} />
                    Verificar Todas as Pendentes
                  </button>
                  <button
                    onClick={handleTriggerDiscovery}
                    disabled={loadingAction === "discovery"}
                    className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-xs rounded-xl flex items-center gap-2"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${loadingAction === "discovery" ? "animate-spin" : ""}`} />
                    Buscar Fontes
                  </button>
                </div>
              </div>

              {/* Métricas Rápidas de Verificação */}
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
                  <span className="text-xs text-slate-400 uppercase font-semibold">Total Verificadas</span>
                  <div className="text-2xl font-bold text-emerald-400 mt-1">{stats.total_news_verified}</div>
                </div>
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
                  <span className="text-xs text-slate-400 uppercase font-semibold">Pendentes de Checagem</span>
                  <div className="text-2xl font-bold text-amber-400 mt-1">
                    {newsList.filter(n => !n.confidence_score).length}
                  </div>
                </div>
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
                  <span className="text-xs text-slate-400 uppercase font-semibold">Em Quarentena</span>
                  <div className="text-2xl font-bold text-orange-400 mt-1">{stats.total_quarantined}</div>
                </div>
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
                  <span className="text-xs text-slate-400 uppercase font-semibold">Bloqueadas (Alto Risco)</span>
                  <div className="text-2xl font-bold text-red-400 mt-1">{stats.total_blocked}</div>
                </div>
              </div>

              {/* Lista Detalhada de Checagem */}
              <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
                <div className="p-5 border-b border-slate-800 flex items-center justify-between">
                  <h3 className="font-bold text-base text-white">Relatórios de Verificação dos Fatos</h3>
                  <span className="text-xs text-slate-400">
                    {newsList.length} notícias no pipeline
                  </span>
                </div>

                <div className="divide-y divide-slate-800">
                  {newsList.map((item) => {
                    const isVerified = item.confidence_score !== null && item.confidence_score !== undefined;
                    const score = item.confidence_score || 0;
                    const verdictColor = 
                      score >= 80 ? "text-emerald-400 bg-emerald-950/60 border-emerald-800/60" :
                      score >= 50 ? "text-amber-400 bg-amber-950/60 border-amber-800/60" :
                      isVerified ? "text-red-400 bg-red-950/60 border-red-800/60" :
                      "text-slate-400 bg-slate-800/60 border-slate-700/60";

                    return (
                      <div key={item.id} className="p-5 hover:bg-slate-800/30 transition flex flex-col md:flex-row md:items-center justify-between gap-4">
                        <div className="space-y-2 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className={`text-[11px] font-bold px-2.5 py-0.5 rounded-full border ${verdictColor}`}>
                              {isVerified ? `${score}% CONFIANÇA • ${item.verdict || "VERIFICADA"}` : "AGUARDANDO CHECAGEM"}
                            </span>
                            <span className="text-[11px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded">
                              RISCO: {item.risk_level}
                            </span>
                            <span className="text-[11px] text-slate-500">
                              Status: {item.status}
                            </span>
                          </div>

                          <h4 
                            onClick={() => setSelectedNews(item)}
                            className="font-bold text-slate-100 hover:text-indigo-400 cursor-pointer transition text-base"
                          >
                            {item.title}
                          </h4>

                          <p className="text-xs text-slate-400 line-clamp-2">
                            {item.summary || "Sem resumo disponível."}
                          </p>

                          <a
                            href={item.url}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1 text-[11px] text-indigo-400 hover:underline"
                          >
                            Ver link da fonte apurada <ExternalLink className="w-3 h-3" />
                          </a>
                        </div>

                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => handleVerifyNews(item)}
                            disabled={loadingAction === `verify_${item.id}`}
                            className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 shadow"
                          >
                            <FileCheck2 className="w-3.5 h-3.5" />
                            {isVerified ? "Rechecar" : "Checar Fatos"}
                          </button>

                          {item.has_content ? (
                            <span className="text-xs text-emerald-400 font-semibold px-2 py-1 bg-emerald-950/40 rounded border border-emerald-900">
                              Conteúdo Produzido
                            </span>
                          ) : (
                            <button
                              onClick={() => handleProduceContent(item)}
                              disabled={loadingAction === `produce_${item.id}`}
                              className="px-3.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-semibold flex items-center gap-1.5"
                            >
                              <Sparkles className="w-3.5 h-3.5 text-amber-400" />
                              Produzir
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* ABA 3: FONTES & CATEGORIAS */}
          {activeTab === "sources" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-bold">Fontes Oficiais e Feeds Conectados</h2>
                <p className="text-xs text-slate-400 mt-1">Fontes monitoradas continuamente pelo motor autônomo.</p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {sourcesList.map((s) => (
                  <div key={s.id} className="bg-slate-900 border border-slate-800 p-5 rounded-xl space-y-2">
                    <span className="text-xs font-bold text-emerald-400 uppercase">{s.source_type}</span>
                    <h3 className="font-bold text-white text-base">{s.name}</h3>
                    <p className="text-xs text-slate-400 break-all">{s.feed_url}</p>
                    <div className="text-xs text-slate-400 pt-2 border-t border-slate-800">
                      Peso de Confiança: <span className="text-indigo-400 font-bold">{s.trust_weight * 100}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ABA 4: GERENCIADOR DE VÍDEOS */}
          {activeTab === "videos" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-bold">Gerenciador de Vídeos & Renderização</h2>
                <p className="text-xs text-slate-400 mt-1">Controle de legendas SRT, cartela informativa, proporção (16:9 e 9:16) e narração por IA.</p>
              </div>

              <div className="bg-slate-900 border border-slate-800 p-6 rounded-2xl space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-bold text-white text-base">Pipeline de Renderização de Vídeo Ativo</h3>
                    <p className="text-xs text-slate-300 mt-1">
                      O pipeline processa automaticamente: Roteiro ➔ Síntese de Narração (TTS) ➔ Cartela Jornalística FFmpeg com Tarja Vermelha Urgente ➔ Arquivo MP4 pronto para o YouTube.
                    </p>
                  </div>
                  <button
                    onClick={handleRenderAllPending}
                    disabled={loadingAction === "render_all"}
                    className="px-4 py-2.5 bg-sky-600 hover:bg-sky-500 text-white rounded-xl text-xs font-bold flex items-center gap-2 shadow-lg shadow-sky-600/20 transition disabled:opacity-50 cursor-pointer"
                  >
                    <Video className={`w-4 h-4 ${loadingAction === "render_all" ? "animate-spin" : ""}`} />
                    {loadingAction === "render_all" ? "Renderizando Lote..." : "Renderizar Todos os Roteiros"}
                  </button>
                </div>
              </div>

              {/* Lista de Notícias Prontas para Renderizar ou já Produzidas */}
              <div className="space-y-3">
                <h3 className="text-sm font-bold text-slate-300">Roteiros Prontos para Renderização:</h3>
                {newsList.filter((n) => n.has_content && n.project_id).length === 0 ? (
                  <div className="bg-slate-900/60 border border-slate-800 p-8 rounded-2xl text-center text-slate-400 text-xs">
                    Nenhum roteiro produzido ainda. Vá na aba <strong>Visão Geral</strong> ou <strong>Notícias</strong> e clique em <strong>Produzir Conteúdo</strong> em qualquer matéria.
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {newsList
                      .filter((n) => n.has_content && n.project_id)
                      .map((item) => (
                        <div key={item.id} className="bg-slate-900 border border-slate-800 p-5 rounded-2xl space-y-3 flex flex-col justify-between">
                          <div>
                            <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300">
                              Roteiro Criado
                            </span>
                            <h4 className="font-bold text-white text-sm mt-2 leading-snug">{item.title}</h4>
                            <p className="text-xs text-slate-400 mt-1 line-clamp-2">{item.summary}</p>
                          </div>

                          <div className="flex gap-2 pt-3 border-t border-slate-800">
                            <button
                              onClick={() => handleRenderVideo(item.project_id, true)}
                              disabled={loadingAction === `render_${item.project_id}`}
                              className="flex-1 py-2 px-3 bg-sky-600 hover:bg-sky-500 text-white rounded-xl text-xs font-bold flex items-center justify-center gap-1.5 transition disabled:opacity-50 cursor-pointer"
                            >
                              <Video className="w-3.5 h-3.5" />
                              {loadingAction === `render_${item.project_id}` ? "Renderizando..." : "Renderizar 9:16 Shorts"}
                            </button>
                            <button
                              onClick={() => handleRenderVideo(item.project_id, false)}
                              disabled={loadingAction === `render_${item.project_id}`}
                              className="flex-1 py-2 px-3 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs font-bold flex items-center justify-center gap-1.5 transition disabled:opacity-50 cursor-pointer"
                            >
                              <Play className="w-3.5 h-3.5" />
                              {loadingAction === `render_${item.project_id}` ? "..." : "16:9 YouTube"}
                            </button>
                            <button
                              onClick={() => openPreview(item.project_id)}
                              disabled={loadingAction === `publish_${item.project_id}`}
                              className="py-2 px-3 bg-red-600 hover:bg-red-500 text-white rounded-xl text-xs font-bold flex items-center justify-center gap-1.5 transition disabled:opacity-50 cursor-pointer"
                            >
                              <Send className="w-3.5 h-3.5" />
                              Prévia
                            </button>
                          </div>
                        </div>
                      ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ABA 5: FILA DE PUBLICAÇÃO */}
          {activeTab === "publishing" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-bold">Fila de Publicação Multiplataforma</h2>
                <p className="text-xs text-slate-400 mt-1">Destinos autorizados: YouTube, Instagram, TikTok e Telegram.</p>
              </div>

              <div className="bg-slate-900 border border-slate-800 p-6 rounded-2xl space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs uppercase font-bold text-slate-400">Status dos Canais Conectados:</span>
                  <span className="text-xs px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-bold">
                    {publishingAccounts.length > 0 ? `${publishingAccounts.length} Contas Conectadas` : "3 Contas Padrão"}
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {/* Card YouTube com Botão de Conexão */}
                  {(() => {
                    const ytAccount = publishingAccounts.find((a) => a.platform === "YOUTUBE");
                    return (
                      <div className="bg-slate-950 p-4 rounded-xl border border-red-900/40 relative flex flex-col justify-between">
                        <div>
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold text-red-400 flex items-center gap-1.5">
                              <Video className="w-3.5 h-3.5" /> YouTube
                            </span>
                            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                              ytAccount && ytAccount.channel_id !== "UC123456"
                                ? "bg-emerald-500/20 text-emerald-300"
                                : "bg-amber-500/20 text-amber-300"
                            }`}>
                              {ytAccount && ytAccount.channel_id !== "UC123456" ? "CONECTADO" : "NÃO CONECTADO"}
                            </span>
                          </div>
                          <p className="text-sm font-semibold text-white mt-2 truncate">
                            {ytAccount?.account_name || "Canal Não Conectado"}
                          </p>
                          <span className="text-xs text-slate-400 block mt-0.5">
                            ID: {ytAccount?.channel_id || "Nenhum"}
                          </span>
                          <span className="text-xs text-slate-400 block mt-0.5">
                            Limite: {ytAccount?.daily_post_limit || 10} vídeos/dia ({ytAccount?.posts_today || 0} hoje)
                          </span>
                        </div>

                        <div className="mt-4 pt-3 border-t border-slate-800">
                          <button
                            onClick={handleConnectYouTube}
                            disabled={loadingAction === "connect_youtube"}
                            className="w-full py-2 px-3 bg-red-600 hover:bg-red-500 text-white rounded-lg text-xs font-bold flex items-center justify-center gap-2 shadow-lg shadow-red-600/20 transition-all cursor-pointer disabled:opacity-50"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                            {loadingAction === "connect_youtube"
                              ? "Redirecionando..."
                              : ytAccount && ytAccount.channel_id !== "UC123456"
                              ? "Reconectar Canal"
                              : "Conectar Canal no YouTube"}
                          </button>
                        </div>
                      </div>
                    );
                  })()}

                  <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 flex flex-col justify-between">
                    <div>
                      <span className="text-xs font-bold text-pink-400">Instagram</span>
                      <p className="text-sm font-semibold text-white mt-1">@noticias_hoje</p>
                      <span className="text-xs text-slate-400 block mt-0.5">Limite: 15 reels/dia</span>
                    </div>
                    <span className="text-[10px] text-slate-500 mt-4 block">Modo Simulação</span>
                  </div>

                  <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 flex flex-col justify-between">
                    <div>
                      <span className="text-xs font-bold text-sky-400">TikTok</span>
                      <p className="text-sm font-semibold text-white mt-1">@noticias_curtas</p>
                      <span className="text-xs text-slate-400 block mt-0.5">Limite: 20 shorts/dia</span>
                    </div>
                    <span className="text-[10px] text-slate-500 mt-4 block">Modo Simulação</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ABA 6: AUTONOMIA & CONFIGURAÇÕES */}
          {activeTab === "settings" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-bold">Configurações de Autonomia & Segurança</h2>
                <p className="text-xs text-slate-400 mt-1">Definições de risco, moderação humana e políticas editoriais.</p>
              </div>

              <div className="bg-slate-900 border border-slate-800 p-6 rounded-2xl space-y-4">
                <h3 className="font-bold text-white text-base">Políticas Editoriais e Bloqueio Automático</h3>
                <ul className="text-xs text-slate-300 space-y-2 list-disc pl-4">
                  <li>Notícias com suspeita de Prompt Injection são retidas com veredito <code>SECURITY_BLOCKED</code>.</li>
                  <li>Notícias com classificação de risco <code>HIGH</code> (crimes, investigações judiciais) exigem aprovação humana.</li>
                  <li>Parada de emergência cancela instantaneamente publicações pendentes e em execução.</li>
                </ul>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
