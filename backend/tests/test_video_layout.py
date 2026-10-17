from pathlib import Path
from types import SimpleNamespace

from app.core.config import settings
from app.modules.video.pipeline import VideoProductionPipeline


def test_fallback_has_no_blue_headline_box(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "VIDEO_DIR", str(tmp_path / "videos"))
    monkeypatch.setattr(settings, "AUDIO_DIR", str(tmp_path / "audio"))
    monkeypatch.setattr(settings, "MEDIA_DIR", str(tmp_path / "media"))
    pipeline = VideoProductionPipeline()
    monkeypatch.setattr(pipeline, "is_ffmpeg_installed", lambda: True)
    monkeypatch.setattr(pipeline, "synthesize_speech", lambda *args: False)
    monkeypatch.setattr(pipeline, "_render_broadcast", lambda *args: False)
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"x" * 60000)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr("app.modules.video.pipeline.subprocess.run", run)
    pipeline.render_mock_or_ffmpeg("layout-test", is_vertical=True, headline="Manchete de teste")
    filters = commands[0][commands[0].index("-vf") + 1]
    assert "color=0x38BDF8:t=4" not in filters
    assert "color=0x1E293B@0.85" not in filters
    assert "textfile=" in filters


def test_broadcast_has_no_headline_panel(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "VIDEO_DIR", str(tmp_path / "videos"))
    monkeypatch.setattr(settings, "AUDIO_DIR", str(tmp_path / "audio"))
    monkeypatch.setattr(settings, "MEDIA_DIR", str(tmp_path / "media"))
    pipeline = VideoProductionPipeline()
    monkeypatch.setattr(pipeline.stock_provider, "get_public_domain_broll", lambda *args, **kwargs: None)
    graphs = []
    def run(command, **kwargs):
        graph = command[command.index("-filter_complex") + 1]
        graphs.append(graph)
        Path(command[-1]).write_bytes(b"x" * 60000)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr("app.modules.video.pipeline.subprocess.run", run)
    assert pipeline._render_broadcast("layout-test", "Manchete", "Texto da notícia", "audio.wav", False, 5.0, True, str(tmp_path / "out.mp4"))
    assert "color=0x0F172A@0.82" not in graphs[0]
    assert ":w=12:" not in graphs[0]
    assert "textfile=" in graphs[0]
