import os
import shutil
import subprocess
import glob
from datetime import datetime
from typing import Dict, Any, Optional

from app.core.config import settings
from app.modules.video.stock_provider import SafeStockVideoProvider
from app.modules.video.speech_text import normalize_speech_text

class VideoProductionPipeline:
    """
    Pipeline completo de geração audiovisual de notícias:
    1. Síntese de Narração (TTS via PowerShell nativo do Windows em áudio WAV).
    2. Geração de Legendas Sincronizadas (.SRT).
    3. Composição Visual no FFmpeg com:
       - Fundo dinâmico em gradiente informativo profissional.
       - Faixa superior/rodapé com branding de jornalismo urgente ("NOTÍCIA URGENTE // AGENTE OFICIAL").
       - Manchete centralizada grande e legível.
       - Legendas dinâmicas em destaque.
       - Áudio de narração e duração sincronizada com a fala.
    """

    def __init__(self):
        self.output_dir = settings.VIDEO_DIR
        self.audio_dir = settings.AUDIO_DIR
        self.stock_provider = SafeStockVideoProvider()
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.audio_dir, exist_ok=True)

    @staticmethod
    def is_ffmpeg_installed() -> bool:
        """Verifica se o FFmpeg está acessível no PATH do sistema."""
        return shutil.which("ffmpeg") is not None

    def synthesize_speech(self, text: str, output_wav_path: str) -> bool:
        """
        Sintetiza a narração em áudio .WAV com alta qualidade de locução jornalística.
        
        1. Se existir um arquivo de voz customizada do usuário em ./storage/audio/custom_voice.wav (ou .mp3),
           permite usar a voz gravada pelo usuário.
        2. Voz neural natural de alta fidelidade em português brasileiro com pitch/equalização
           masculina encorpada de âncora de rádio/TV (sem falhas ou robótica).
        3. Fallback resiliente para a síntese local se estiver offline.
        """
        import urllib.parse
        import urllib.request

        custom_voice_paths = [
            os.path.join(self.audio_dir, "custom_voice.wav"),
            os.path.join(self.audio_dir, "custom_voice.mp3"),
            os.path.join(self.audio_dir, "minha_voz.wav"),
            os.path.join(self.audio_dir, "minha_voz.mp3")
        ]
        for custom_path in custom_voice_paths:
            if os.path.exists(custom_path) and os.path.getsize(custom_path) > 5000:
                print(f"[Video Pipeline] Usando voz customizada do usuário: {custom_path}")
                try:
                    # Normaliza para WAV na taxa correta
                    cmd = ["ffmpeg", "-y", "-i", custom_path, "-ar", "24000", "-ac", "1", output_wav_path]
                    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    return True
                except Exception as ex:
                    print(f"[Video Pipeline] Erro ao carregar voz customizada: {ex}")

        clean_text = normalize_speech_text(text)
        if not clean_text:
            clean_text = "Notícia apurada e verificada pelo agente autônomo de inteligência artificial."

        # 1. MOTOR PRINCIPAL: Microsoft Neural Edge-TTS (pt-BR-AntonioNeural - Repórter Masculino Profissional)
        try:
            import asyncio
            import edge_tts

            temp_mp3 = output_wav_path.replace(".wav", "_edge.mp3")

            async def _synthesize_edge():
                communicate = edge_tts.Communicate(clean_text, "pt-BR-AntonioNeural", rate="+0%", pitch="-3Hz")
                await communicate.save(temp_mp3)

            # Execução segura em qualquer contexto assíncrono ou síncrono
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        pool.submit(asyncio.run, _synthesize_edge()).result()
                else:
                    loop.run_until_complete(_synthesize_edge())
            except Exception:
                asyncio.run(_synthesize_edge())

            if os.path.exists(temp_mp3) and os.path.getsize(temp_mp3) > 1000:
                # Converte com FFmpeg aplicando equalização para estúdio de jornalismo
                af_filter = (
                    "equalizer=f=120:width_type=o:width=1.0:g=3.5,"
                    "equalizer=f=3200:width_type=o:width=1.2:g=2.0,"
                    "volume=1.25"
                )
                cmd = ["ffmpeg", "-y", "-i", temp_mp3, "-af", af_filter, "-ar", "24000", "-ac", "1", output_wav_path]
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    os.remove(temp_mp3)
                except Exception:
                    pass

                if os.path.exists(output_wav_path) and os.path.getsize(output_wav_path) > 1000:
                    print(f"[Video Pipeline] Áudio sintetizado com sucesso com voz masculina de repórter (pt-BR-AntonioNeural)")
                    return True
        except Exception as e_edge:
            print(f"[Video Pipeline] Erro no Edge-TTS neural: {e_edge}")

        # Fallback: voz do Google Tradutor
        try:
            chunks = []
            curr = ""
            for sentence in clean_text.split(". "):
                sentence = sentence.strip()
                if not sentence:
                    continue
                if len(curr) + len(sentence) < 170:
                    curr += (". " if curr else "") + sentence
                else:
                    if curr:
                        chunks.append(curr)
                    curr = sentence
            if curr:
                chunks.append(curr)

            temp_parts = []
            session_id = int(datetime.utcnow().timestamp())
            for idx, chunk in enumerate(chunks):
                encoded_chunk = urllib.parse.quote(chunk)
                url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={encoded_chunk}&tl=pt-BR&client=tw-ob"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                part_path = os.path.join(self.audio_dir, f"tts_part_{session_id}_{idx}.mp3")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    with open(part_path, "wb") as pf:
                        pf.write(resp.read())
                temp_parts.append(part_path)

            concat_file = os.path.abspath(os.path.join(self.audio_dir, f"concat_{session_id}.txt"))
            with open(concat_file, "w", encoding="utf-8") as cf:
                for tp in temp_parts:
                    safe_p = os.path.abspath(tp).replace("\\", "/")
                    cf.write(f"file '{safe_p}'\n")

            # Aplica filtros de áudio para dar timbre masculino grave, firme e encorpado de locutor:
            # - Pitch shift calibrado (asetrate 0.89 + aresample + atempo compensado)
            # - Equalizador nos graves (130Hz) para presença e corpo de voz
            # - Equalizador nos agudos (3200Hz) para clareza e dicção limpa
            # - Volume normalizado para transmissão de notícias
            af_filter = (
                "asetrate=24000*0.89,"
                "aresample=24000,"
                "atempo=1.12,"
                "equalizer=f=130:width_type=o:width=1.2:g=5.5,"
                "equalizer=f=3200:width_type=o:width=1.5:g=2.2,"
                "volume=1.35"
            )
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", concat_file,
                "-af", af_filter,
                output_wav_path
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Limpa temporários
            for tp in temp_parts:
                if os.path.exists(tp):
                    try: os.remove(tp)
                    except Exception: pass
            if os.path.exists(concat_file):
                try: os.remove(concat_file)
                except Exception: pass

            if os.path.exists(output_wav_path) and os.path.getsize(output_wav_path) > 1000:
                return True
        except Exception as e:
            print(f"[Video Pipeline] Erro no TTS Natural Masculino, usando fallback Windows: {e}")

        # Fallback local SAPI Windows caso não haja internet
        safe_sapi_text = clean_text.replace('"', ' ').replace("'", " ")
        ps_script = f"""
Add-Type -AssemblyName System.Speech
$syn = New-Object System.Speech.Synthesis.SpeechSynthesizer
$syn.Rate = 0
$syn.SetOutputToWaveFile('{output_wav_path}')
$syn.Speak('{safe_sapi_text}')
$syn.Dispose()
"""
        temp_ps1 = os.path.join(self.audio_dir, f"tts_{int(datetime.utcnow().timestamp())}.ps1")
        try:
            with open(temp_ps1, "w", encoding="utf-8") as f:
                f.write(ps_script)

            subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", temp_ps1],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30
            )
            return os.path.exists(output_wav_path) and os.path.getsize(output_wav_path) > 1000
        except Exception as e:
            print(f"[Video Pipeline] Erro no fallback TTS Windows: {e}")
            return False
        finally:
            if os.path.exists(temp_ps1):
                try:
                    os.remove(temp_ps1)
                except Exception:
                    pass

    def get_audio_duration(self, audio_path: str) -> float:
        """Obtém a duração exata do áudio usando ffprobe."""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            return float(res.stdout.strip())
        except Exception:
            return 12.0

    def generate_srt_subtitles(self, script_text: str, duration_seconds: int = 15) -> str:
        """Gera arquivo de legenda formatado em padrão SRT sincronizado com a duração."""
        srt_path = os.path.join(self.output_dir, f"subtitles_{int(datetime.utcnow().timestamp())}.srt")
        lines = [line.strip() for line in script_text.split("\n") if line.strip()]
        
        with open(srt_path, "w", encoding="utf-8") as f:
            if not lines:
                lines = ["Notícia apurada e verificada."]
            
            slot_duration = max(1, duration_seconds // len(lines))
            current_time = 0
            
            for idx, text in enumerate(lines, 1):
                start_h, start_m, start_s = current_time // 3600, (current_time % 3600) // 60, current_time % 60
                end_time = current_time + slot_duration
                end_h, end_m, end_s = end_time // 3600, (end_time % 3600) // 60, end_time % 60
                
                f.write(f"{idx}\n")
                f.write(f"{start_h:02d}:{start_m:02d}:{start_s:02d},000 --> {end_h:02d}:{end_m:02d}:{end_s:02d},000\n")
                f.write(f"{text}\n\n")
                current_time = end_time
                
        return srt_path

    @staticmethod
    def _wrap(text: str, width: int, max_lines: int = 99) -> list:
        lines, cur = [], ""
        for w in text.split():
            if cur and len(cur) + 1 + len(w) > width:
                lines.append(cur)
                cur = w
            else:
                cur = f"{cur} {w}".strip()
        if cur:
            lines.append(cur)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = lines[-1].rstrip(" .,") + "..."
        return lines

    def _build_captions(self, speech: str, per_caption_chars: int) -> list:
        """Divide a fala em legendas curtas (frases/trechos) de até 2 linhas."""
        import re
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", " ".join(speech.split())) if s.strip()]
        caps = []
        for s in sentences:
            words, cur = s.split(), ""
            for w in words:
                if cur and len(cur) + 1 + len(w) > per_caption_chars:
                    caps.append(cur)
                    cur = w
                else:
                    cur = f"{cur} {w}".strip()
            if cur:
                caps.append(cur)
        return caps

    def _render_broadcast(self, project_id, title_text, speech_text, wav_path, has_audio,
                          duration, is_vertical, final_video_path) -> bool:
        """Layout de reportagem: fundo animado, tarja AO VIVO, manchete, legendas sincronizadas,
        letreiro rolante, barra de progresso e fades de entrada/saída."""
        W, H = (1080, 1920) if is_vertical else (1920, 1080)
        font_file = "C:/Windows/Fonts/arial.ttf"
        font_opt = f"fontfile='C\\:/Windows/Fonts/arial.ttf':" if os.path.exists(font_file) else ""
        bold_file = "C:/Windows/Fonts/arialbd.ttf"
        bold_opt = f"fontfile='C\\:/Windows/Fonts/arialbd.ttf':" if os.path.exists(bold_file) else font_opt

        tmp_files = []

        def write_txt(name: str, content: str) -> str:
            path = os.path.join(self.output_dir, f"{name}_{project_id}.txt")
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            tmp_files.append(path)
            return path.replace("\\", "/")

        # Dimensões responsivas
        if is_vertical:
            tag_y, tag_h, tag_fs = 90, 70, 30
            head_fs, head_wrap, margin = 54, 26, 60
            cap_fs, cap_wrap, cap_y = 60, 24, "h*0.64"
            tick_h, tick_fs = 120, 34
        else:
            tag_y, tag_h, tag_fs = 40, 60, 28
            head_fs, head_wrap, margin = 56, 52, 80
            cap_fs, cap_wrap, cap_y = 54, 44, "h*0.66"
            tick_h, tick_fs = 90, 30

        head_lines = self._wrap(title_text.upper(), head_wrap, 4)
        card_y = tag_y + tag_h + 40
        head_path = write_txt("head", "\n".join(head_lines))
        tag_path = write_txt("tag", "NOTÍCIAS  |  IMAGENS ILUSTRATIVAS")
        tick_path = write_txt("tick", "AGENTE AUTÔNOMO DE NOTÍCIAS   •   INFORMAÇÃO VERIFICADA EM TEMPO REAL   •   " + title_text + "   •   ")

        # Legendas sincronizadas proporcionalmente ao tamanho do texto
        speech_dur = max(2.0, duration - 1.0)
        captions = self._build_captions(speech_text, cap_wrap * 2)
        total_chars = sum(len(c) for c in captions) or 1
        t0, span = 0.3, max(1.0, speech_dur - 0.5)
        cap_filters = []
        cur_t = t0
        for i, c in enumerate(captions):
            seg = span * len(c) / total_chars
            lines = self._wrap(c, cap_wrap, 2)
            p = write_txt(f"cap{i}", "\n".join(lines))
            cap_filters.append(
                f"drawtext={bold_opt}textfile='{p}':fontcolor=white:fontsize={cap_fs}:line_spacing=12:"
                f"x=(w-text_w)/2:y={cap_y}:box=1:boxcolor=0x0B132B@0.72:boxborderw=26:"
                f"enable='between(t,{cur_t:.2f},{cur_t + seg:.2f})'"
            )
            cur_t += seg

        d = f"{duration:.2f}"
        chain = [
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},format=yuv420p",
            f"drawbox=x=0:y=tag_y:w=iw:h={tag_h}:color=0xDC2626:t=fill".replace("tag_y", str(tag_y)),
            f"drawbox=x={margin}:y={tag_y + tag_h // 2 - 9}:w=18:h=18:color=white:t=fill:enable='lt(mod(t,1.2),0.7)'",
            f"drawtext={bold_opt}textfile='{tag_path}':fontcolor=white:fontsize={tag_fs}:x={margin + 40}:y={tag_y + (tag_h - tag_fs) // 2 - 2}",
            f"drawtext={bold_opt}textfile='{head_path}':fontcolor=white:fontsize={head_fs}:line_spacing=16:"
            f"x={margin + 44}:y={card_y + 30}:alpha='min(1,t/0.7)'",
        ] + cap_filters + [
            f"drawbox=x=0:y=ih-{tick_h}:w=iw:h={tick_h}:color=0x0F172A:t=fill",
            f"drawbox=x=0:y=ih-{tick_h}:w=iw:h=6:color=0xDC2626:t=fill",
            f"drawtext={font_opt}textfile='{tick_path}':fontcolor=0xE2E8F0:fontsize={tick_fs}:"
            f"x='w-mod(t*170,w+text_w)':y=h-{tick_h // 2 + tick_fs // 2}",
            f"fade=t=in:st=0:d=0.5,fade=t=out:st={max(0.1, duration - 0.6):.2f}:d=0.6[bg]",
        ]
        graph = ",\n".join(chain[:-1]) + ",\n" + chain[-1]
        graph += (
            f";\n[bg][2:v]overlay=x='-w+w*t/{d}':y=H-{tick_h}-10:eval=frame[v]"
        )
        script_path = os.path.join(self.output_dir, f"graph_{project_id}.txt")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(graph)
        tmp_files.append(script_path)

        broll_video = self.stock_provider.get_public_domain_broll(title_text, is_vertical=is_vertical, script_or_summary=speech_text)
        if broll_video and os.path.exists(broll_video):
            print(f"[Video Pipeline] Usando vídeo de apoio contextualizado: {broll_video}")
            cmd = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", broll_video]
        else:
            bg = (f"gradients=s=540x960:c0=0x0B132B:c1=0x1E3A8A:c2=0x0B132B:c3=0x172554:nb_colors=4:"
                  f"speed=0.02:r=25:d={d}") if is_vertical else (
                  f"gradients=s=960x540:c0=0x0B132B:c1=0x1E3A8A:c2=0x0B132B:c3=0x172554:nb_colors=4:"
                  f"speed=0.02:r=25:d={d}")
            cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", bg]
        if has_audio:
            cmd += ["-i", wav_path]
        else:
            cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=24000"]
        cmd += ["-f", "lavfi", "-i", f"color=c=0x38BDF8:s={W}x10:r=25:d={d}",
                "-filter_complex", graph,
                "-map", "[v]", "-map", "1:a",
                "-af", "apad", "-t", d,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "25",
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                final_video_path]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
            if res.returncode != 0:
                print(f"[Video Pipeline] Render broadcast falhou: {res.stderr[-600:]}")
                return False
            return os.path.exists(final_video_path) and os.path.getsize(final_video_path) > 20000
        except Exception as e:
            print(f"[Video Pipeline] Erro no render broadcast: {e}")
            return False
        finally:
            for p in tmp_files:
                try:
                    os.remove(p)
                except Exception:
                    pass

    def render_mock_or_ffmpeg(
        self,
        project_id: str,
        is_vertical: bool = False,
        headline: Optional[str] = None,
        script_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Gera um vídeo rico e completo com narração falada, cartela visual e legenda animada.
        - Para Shorts/Reels: 1080x1920 (9:16).
        - Para YouTube padrão: 1920x1080 (16:9).
        """
        width, height = (1080, 1920) if is_vertical else (1920, 1080)
        resolution = f"{width}x{height}"
        aspect_name = "vertical_9_16" if is_vertical else "horizontal_16_9"
        filename = f"video_{project_id}_{aspect_name}.mp4"
        final_video_path = os.path.join(self.output_dir, filename)

        if not self.is_ffmpeg_installed():
            raise RuntimeError("FFmpeg não instalado; vídeo não pode ser gerado.")
        # Remove any previous render before attempting a new one.
        if os.path.exists(final_video_path):
            os.remove(final_video_path)

        # 1. Definir texto de narração e manchete
        title_text = (headline or "NOTÍCIA DE ÚLTIMA HORA").strip()
        speech_text = (script_text or title_text).strip()

        # 2. Sintetizar áudio com a voz
        wav_filename = f"audio_{project_id}_{int(datetime.utcnow().timestamp())}.wav"
        wav_path = os.path.join(self.audio_dir, wav_filename)
        has_audio = self.synthesize_speech(speech_text, wav_path)

        duration = self.get_audio_duration(wav_path) if has_audio else 10.0
        # Margem de segurança de 1 segundo ao final da fala
        duration = max(5.0, duration + 1.0)

        # Render profissional estilo reportagem (fallback abaixo se falhar)
        if self.is_ffmpeg_installed() and self._render_broadcast(
            project_id, title_text, speech_text, wav_path, has_audio,
            duration, is_vertical, final_video_path
        ):
            return {
                "file_path": final_video_path,
                "resolution": resolution,
                "format": aspect_name,
                "duration": duration,
                "has_ffmpeg": True
            }

        # 3. Preparar arquivo de texto da manchete para o FFmpeg
        headline_txt_path = os.path.join(self.output_dir, f"title_{project_id}.txt")
        # Quebra em linhas de até 35 caracteres para caber no vídeo
        words = title_text.split()
        wrapped_lines = []
        cur_line = []
        for w in words:
            if sum(len(x) for x in cur_line) + len(cur_line) + len(w) > 30:
                wrapped_lines.append(" ".join(cur_line))
                cur_line = [w]
            else:
                cur_line.append(w)
        if cur_line:
            wrapped_lines.append(" ".join(cur_line))
        formatted_title = "\n".join(wrapped_lines)

        with open(headline_txt_path, "w", encoding="utf-8") as f:
            f.write(formatted_title)

        # 4. Caminho seguro para o FFmpeg no Windows (escapando barras)
        safe_title_path = headline_txt_path.replace("\\", "/").replace(":", "\\:")
        font_path = "C:/Windows/Fonts/arial.ttf".replace(":", "\\:")

        if self.is_ffmpeg_installed():
            # Filtro de vídeo com gradiente elegante, tarja vermelha e texto centralizado
            font_size = 56 if is_vertical else 48
            banner_size = 28 if is_vertical else 24

            font_opt = f"fontfile='{font_path}':" if os.path.exists("C:/Windows/Fonts/arial.ttf") else ""

            vf_filters = [
                # Tarja superior vermelha de 'URGENTE // NOTÍCIA VERIFICADA'
                f"drawbox=y=80:color=0xDC2626:width=iw:height=70:t=fill",
                f"drawtext={font_opt}text='URGENTE  //  NOTÍCIA VERIFICADA':fontcolor=white:fontsize={banner_size}:x=(w-text_w)/2:y=100",
                # Manchete sem caixa de fundo ou borda azul.
                # Manchete principal
                f"drawtext={font_opt}textfile='{safe_title_path}':fontcolor=0xFFFFFF:fontsize={font_size}:x=(w-text_w)/2:y=(h-text_h)/2-30:line_spacing=18",
                # Rodapé de crédito editorial
                f"drawbox=y=ih-120:color=0x0F172A:width=iw:height=120:t=fill",
                f"drawtext={font_opt}text='AGENTE AUTÔNOMO DE NOTÍCIAS  •  JORNALISMO EM TEMPO REAL':fontcolor=0x94A3B8:fontsize=22:x=(w-text_w)/2:y=h-70"
            ]

            filter_complex = ",".join(vf_filters)

            if has_audio:
                cmd = [
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i", f"color=c=0x0B132B:s={resolution}:r=25:d={duration}",
                    "-i", wav_path,
                    "-vf", filter_complex,
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k",
                    "-shortest",
                    final_video_path
                ]
            else:
                # Fallback sem áudio: gera tom neutro silencioso
                cmd = [
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i", f"color=c=0x0B132B:s={resolution}:r=25:d={duration}",
                    "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
                    "-vf", filter_complex,
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    "-t", str(duration),
                    final_video_path
                ]

            try:
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except Exception as e:
                print(f"[Video Pipeline] Erro ao renderizar vídeo rico: {e}")
                # Fallback simples caso falhe o drawtext com arquivo
                simple_cmd = [
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i", f"color=c=0x1E293B:s={resolution}:r=25:d={duration}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    final_video_path
                ]
                subprocess.run(simple_cmd, check=False)

        # Limpeza de arquivo de texto temporário
        if os.path.exists(headline_txt_path):
            try:
                os.remove(headline_txt_path)
            except Exception:
                pass

        if not os.path.isfile(final_video_path) or os.path.getsize(final_video_path) <= 20000:
            raise RuntimeError("Falha na renderização; vídeo ausente ou inválido.")

        return {
            "file_path": final_video_path,
            "resolution": resolution,
            "format": aspect_name,
            "duration": duration,
            "has_ffmpeg": self.is_ffmpeg_installed()
        }
