import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.modules.video.speech_text import normalize_speech_text
from app.modules.video.pipeline import VideoProductionPipeline


@pytest.mark.parametrize("text,expected", [
    ("Fim da escala 6x1.", "Fim da escala seis por um."),
    ("Escala 6 x 1, em debate.", "Escala seis por um, em debate."),
    ("Jornada 5 X 2", "Jornada cinco por dois"),
    ("Turnos 12×36 e 24x48", "Turnos doze por trinta e seis e vinte e quatro por quarenta e oito"),
    ("Tela 1920x1080", "Tela 1920 por 1080"),
    ("Medidas 2,5 x 3,5", "Medidas 2,5 por 3,5"),
    ("A rede X e o exame de raio-X.", "A rede X e o exame de raio-X."),
    ("Modelo AX6X1 e arquivo6x1.mp4", "Modelo AX6X1 e arquivo6x1.mp4"),
    ("Escala seis por um", "Escala seis por um"),
])
def test_numeric_x_pronunciation(text, expected):
    assert normalize_speech_text(text) == expected
    assert normalize_speech_text(expected) == expected


def test_edge_receives_normalized_speech(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "VIDEO_DIR", str(tmp_path / "videos"))
    monkeypatch.setattr(settings, "AUDIO_DIR", str(tmp_path / "audio"))
    monkeypatch.setattr(settings, "MEDIA_DIR", str(tmp_path / "media"))
    spoken = []
    class Communicate:
        def __init__(self, text, *args, **kwargs):
            spoken.append(text)
        async def save(self, path):
            Path(path).write_bytes(b"audio" * 1000)
    monkeypatch.setitem(sys.modules, "edge_tts", SimpleNamespace(Communicate=Communicate))
    def run(command, **kwargs):
        Path(command[-1]).write_bytes(b"audio" * 1000)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr("app.modules.video.pipeline.subprocess.run", run)
    original = "Notícia sobre a escala 6x1."
    output = str(tmp_path / "narration.wav")
    assert VideoProductionPipeline().synthesize_speech(original, output)
    assert spoken == ["Notícia sobre a escala seis por um."]
    assert original == "Notícia sobre a escala 6x1."
