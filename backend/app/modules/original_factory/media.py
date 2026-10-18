"""Technical gates and owned graphical assets, using the existing FFmpeg stack."""
import json
from pathlib import Path
import shutil
import subprocess
import textwrap

from app.modules.video.preview import render_paths


def technical_quality(path: str, vertical: bool):
    if not shutil.which("ffprobe"):
        raise RuntimeError("FFprobe não instalado; checagem técnica indisponível.")
    result = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
                            capture_output=True, text=True, check=True, timeout=30)
    data = json.loads(result.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {})
    width, height = video.get("width", 0), video.get("height", 0)
    duration = float(data.get("format", {}).get("duration", 0))
    issues = []
    if not width or not height or (height > width) != vertical or min(width, height) < 720:
        issues.append("Orientação/resolução inválida")
    if not audio:
        issues.append("Narração ausente")
    if not (15 <= duration <= 65 if vertical else 40 <= duration <= 480):
        issues.append("Duração fora dos limites editoriais")
    # Decode actual audio and frames, not merely a plausible file header.
    subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "null", "-"],
                   capture_output=True, check=True, timeout=600)
    return {"passed": not issues, "issues": issues, "width": width, "height": height,
            "duration": duration, "audio": bool(audio), "decoded": True}


def thumbnail_path(project_id):
    video, _ = render_paths(project_id, True)
    return video.with_name(f"thumbnail_{project_id}.jpg")


CATEGORY_PALETTES = {
    "espaco": "0x0B132B",      # Deep space navy
    "ciencia": "0x0B2545",     # Midnight blue
    "tecnologia": "0x132A13",  # Cyber dark green
    "historia": "0x3D0C11",    # Antique deep crimson
    "natureza": "0x1A281F",    # Deep forest
    "cerebro": "0x2C1138",     # Deep purple / neural
    "hipoteses": "0x261447",   # Deep violet
}


def create_thumbnail(project_id, title, category=None):
    dest = thumbnail_path(project_id)
    text_path = dest.with_suffix(".txt")
    text_path.write_text("\n".join(textwrap.wrap(title, 24)[:3]), encoding="utf-8")
    safe = str(text_path).replace("\\", "/").replace(":", "\\:")
    bg_color = CATEGORY_PALETTES.get(str(category).lower(), "0x0B132B")
    try:
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={bg_color}:s=1280x720:d=1",
            "-vf", f"drawtext=textfile='{safe}':expansion=none:fontcolor=white:fontsize=64:x=(w-text_w)/2:y=(h-text_h)/2",
            "-frames:v", "1", "-update", "1", str(dest)], capture_output=True, check=True, timeout=30)
        if not dest.is_file():
            raise RuntimeError("Miniatura não foi gerada.")
        Path(str(dest) + ".json").write_text(json.dumps({"license": "OWN_PRODUCTION", "kind": "typographic_thumbnail", "category": category}), encoding="utf-8")
        return str(dest)
    finally:
        text_path.unlink(missing_ok=True)
