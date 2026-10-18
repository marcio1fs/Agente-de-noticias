import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import NewsPreview from "../src/components/NewsPreview";

const readyPreview = {
  headline: "Manchete", summary: "Resumo", ready: true,
  video_url: "/api/v1/content-projects/project/preview/video?is_vertical=false",
  source_url: "https://example.com/news", publication_description: "Fonte da notícia original: https://example.com/news",
};

function props() {
  return {
    items: [{ project_id: "project", title: "Manchete" }], selectedId: "project",
    onSelect: vi.fn(), refreshKey: 0, mode: "ASSISTED", stopped: false, busy: false,
    onRender: vi.fn().mockResolvedValue(undefined), onPublish: vi.fn().mockResolvedValue(undefined),
  };
}

function mockPreview(data = readyPreview) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => data }));
}

async function makePlayable() {
  const player = await screen.findByLabelText("Vídeo da notícia: Manchete");
  fireEvent.canPlay(player);
  return player;
}

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("NewsPreview publication controls", () => {
  it("explains missing video, keeps review blocked and generates the selected horizontal version", async () => {
    mockPreview({ ...readyPreview, ready: false, video_url: null as unknown as string });
    const callbacks = props();
    render(<NewsPreview {...callbacks} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "16:9 YouTube" }));
    await screen.findByText(/1\. Clique em/);
    expect((screen.getByRole("checkbox") as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Confirmar publicação" }) as HTMLButtonElement).disabled).toBe(true);
    await user.click(screen.getByRole("button", { name: "Gerar prévia do vídeo" }));
    expect(callbacks.onRender).toHaveBeenCalledWith("project", false);
  });

  it("enables review and publishes the horizontal version only after confirmation", async () => {
    mockPreview();
    const callbacks = props();
    render(<NewsPreview {...callbacks} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "16:9 YouTube" }));
    await makePlayable();
    const review = screen.getByRole("checkbox") as HTMLInputElement;
    expect(review.disabled).toBe(false);
    const publish = screen.getByRole("button", { name: "Confirmar publicação" }) as HTMLButtonElement;
    expect(publish.disabled).toBe(true);
    await user.click(review);
    expect(publish.disabled).toBe(false);
    await user.click(publish);
    expect(callbacks.onPublish).toHaveBeenCalledWith("project", false);
  });

  it("clicking the already active format does not clear the loaded video", async () => {
    mockPreview();
    render(<NewsPreview {...props()} />);
    const player = await makePlayable();
    await userEvent.click(screen.getByRole("button", { name: "16:9 YouTube" }));
    expect(screen.getByLabelText("Vídeo da notícia: Manchete")).toEqual(player);
    expect((screen.getByRole("checkbox") as HTMLInputElement).disabled).toBe(false);
  });

  it("clears review after a format change and keeps emergency stop effective", async () => {
    mockPreview();
    const callbacks = props();
    const { rerender } = render(<NewsPreview {...callbacks} />);
    const user = userEvent.setup();
    await makePlayable();
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "9:16 Shorts" }));
    await user.click(screen.getByRole("checkbox"));
    rerender(<NewsPreview {...callbacks} stopped />);
    expect((screen.getByRole("button", { name: "Confirmar publicação" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("disables review again when video playback fails", async () => {
    mockPreview();
    render(<NewsPreview {...props()} />);
    const player = await makePlayable();
    await userEvent.click(screen.getByRole("checkbox"));
    fireEvent.error(player);
    await waitFor(() => expect((screen.getByRole("checkbox") as HTMLInputElement).disabled).toBe(true));
    expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(false);
  });
});
