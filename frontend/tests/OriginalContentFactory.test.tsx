import React from "react";
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import OriginalContentFactory from "../src/components/OriginalContentFactory";

const status = { enabled: true, categories: ["ciencia", "hipoteses"], research_hosts: ["science.nasa.gov"], daily_call_limit: 3, daily_budget_microusd: 300000, capabilities: { gemini_configured: true, ffmpeg: true, ffprobe: true } };
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("shows setup instructions without requesting a paid service when disabled", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ...status, enabled: false }) });
  vi.stubGlobal("fetch", fetch);
  render(<OriginalContentFactory agentMode="SIMULATION" />);
  await screen.findByText("Configuração necessária no backend");
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0][0]).toBe("/api/v1/factory/status");
});

it("keeps administrative credentials out of URLs and submits original topic with disclosure nature", async () => {
  const fetch = vi.fn(async (url: string, options?: RequestInit) => ({ ok: true, json: async () => url.endsWith("/status") ? status : url.endsWith("/productions") ? { items: [], accounts: [], usage: { calls: 0, reserved_microusd: 0 } } : { id: "new", phase: "QUEUED" } }));
  vi.stubGlobal("fetch", fetch);
  render(<OriginalContentFactory agentMode="ASSISTED" />);
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Chave administrativa"), "test-only-key");
  await user.click(screen.getByRole("button", { name: "Acessar" }));
  await user.type(await screen.findByLabelText("Tema do vídeo original"), "E se o Sol desaparecesse amanhã?");
  await user.selectOptions(screen.getByLabelText("Categoria original"), "hipoteses");
  await user.type(screen.getByLabelText("Fontes de pesquisa"), "https://science.nasa.gov/solar-system/");
  await user.click(screen.getByRole("button", { name: "Adicionar à fila" }));
  await waitFor(() => expect(fetch.mock.calls.some(([url]) => url.endsWith("/topics"))).toBe(true));
  const call = fetch.mock.calls.find(([url]) => url.endsWith("/topics"))!;
  expect(JSON.parse(call[1]!.body as string).nature).toBe("HYPOTHESIS");
  expect((call[1]!.headers as Record<string, string>)["X-Factory-Key"]).toBe("test-only-key");
  expect(fetch.mock.calls.every(([url]) => !url.includes("test-only-key"))).toBe(true);
});

it("requires the factual, rights and script attestations before approval", async () => {
  const production = { id: "p", title: "Tema original", category: "ciencia", nature: "FACTUAL", phase: "REVIEW_REQUIRED", score: 80, origin: "manual", source_urls: [], research: [], is_vertical: true, project_id: "project", error: null, attempts: 1, draft: { short_script: "Texto" }, quality_report: { passed: true, issues: [] }, metrics: {} };
  const fetch = vi.fn(async (url: string, options?: RequestInit) => ({ ok: true, json: async () => url.endsWith("/status") ? status : url.endsWith("/productions") ? { items: [production], accounts: [], usage: { calls: 1, reserved_microusd: 100000 } } : { phase: "APPROVED" } }));
  vi.stubGlobal("fetch", fetch);
  render(<OriginalContentFactory agentMode="ASSISTED" />);
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Chave administrativa"), "test-only-key");
  await user.click(screen.getByRole("button", { name: "Acessar" }));
  const approve = await screen.findByRole("button", { name: "Aprovar roteiro" });
  expect((approve as HTMLButtonElement).disabled).toBe(true);
  await user.type(screen.getByLabelText("Nome do revisor"), "Editora");
  for (const box of screen.getAllByRole("checkbox")) await user.click(box);
  expect((approve as HTMLButtonElement).disabled).toBe(false);
  await user.click(approve);
  await waitFor(() => expect(fetch.mock.calls.some(([url]) => url.endsWith("/approve"))).toBe(true));
});
