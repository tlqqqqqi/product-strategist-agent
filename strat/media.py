"""Audio and video into sources a claim cites by timestamp.

Audio: speech to text, chunk by chunk, into media/<name>.transcript.md with one "## [HH:MM:SS -
HH:MM:SS]" block per segment; the transcript is registered as a source (format "transcript").
Video: ffmpeg takes out the audio track (then the same transcript) and a frame every N seconds
into media/<name>/frame_NNNN.jpg, listed with timestamps in media/<name>/frames.md (registered as
a source of format "frames").

Speech to text: the endpoint in .env (STRAT_STT_BASE_URL, _API_KEY, _MODEL; an
OpenAI-compatible /audio/transcriptions, Mistral's by default), else local Whisper
(faster-whisper or openai-whisper), else exit 2. Each chunk is its own logged step with its
price, so a restart continues after the last finished chunk. ffmpeg is optional for audio (the
file goes up in one piece) and required for video.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import time
import uuid
import wave
from pathlib import Path

from strat import net
from strat.core import FAILED, UNAVAILABLE, StratError, case_path, emit, env, load_config

AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".flac", ".aiff",
                  ".aif", ".wma"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mpeg", ".mpg", ".wmv"}
MISTRAL_HOST = "api.mistral.ai"
RETRY_PAUSE = 2.0  # seconds before the one retry; tests set it to 0
FFMPEG_HINT = ("install ffmpeg (macOS: `brew install ffmpeg`; Debian/Ubuntu: `sudo apt install "
               "ffmpeg`; Windows: `winget install ffmpeg`) and run the command again")
NO_STT = ("no speech-to-text: set STRAT_STT_API_KEY (and STRAT_STT_BASE_URL, e.g. "
          "https://api.mistral.ai/v1) in .env, or install local Whisper into the venv "
          "(`.venv/bin/pip install faster-whisper` or `openai-whisper`)")
LIMITS = ("Limits: speakers are not identified; terms and figures may be misheard, so a number "
          "taken from speech is a hypothesis until a document confirms it.")


def _conf() -> dict:
    return load_config("routes").get("media", {})


# --- multipart (urllib has none; sent through net.post so tests replace the network) ----------

def multipart(fields: dict[str, str], files: dict[str, tuple[str, bytes, str]]) -> tuple[bytes, str]:
    """Encode form fields and files as multipart/form-data. Returns (body, content type)."""
    boundary = "strat-" + uuid.uuid4().hex
    out = bytearray()
    for name, value in fields.items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n"
                f"{value}\r\n").encode("utf-8")
    for name, (filename, data, ctype) in files.items():
        safe = filename.replace('"', "_").replace("\r", "_").replace("\n", "_")
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; "
                f"filename=\"{safe}\"\r\nContent-Type: {ctype}\r\n\r\n").encode("utf-8")
        out += data + b"\r\n"
    out += f"--{boundary}--\r\n".encode("utf-8")
    return bytes(out), f"multipart/form-data; boundary={boundary}"


# --- timestamps ---------------------------------------------------------------------------------

def hms(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def parse_hms(text: str) -> int | None:
    """'00:12:40', '12:40' or '1:02:03' -> seconds; None when it is not a timestamp."""
    m = re.match(r"^(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:\.\d+)?$", text.strip())
    if not m or int(m.group(3)) > 59 or (m.group(1) and int(m.group(2)) > 59):
        return None
    return int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3))


SEGMENT_HEADER = re.compile(r"^## \[(\d{2}:\d{2}:\d{2}) - (\d{2}:\d{2}:\d{2})\]$")


def segments_of(text: str) -> list[tuple[int, int, str]]:
    """(start, end, text) per "## [HH:MM:SS - HH:MM:SS]" block of a transcript snapshot."""
    out, cur, buf = [], None, []
    for line in text.splitlines():
        m = SEGMENT_HEADER.match(line)
        if m:
            if cur:
                out.append((*cur, "\n".join(buf).strip()))
            cur, buf = (parse_hms(m.group(1)), parse_hms(m.group(2))), []
        elif cur:
            buf.append(line)
    if cur:
        out.append((*cur, "\n".join(buf).strip()))
    return out


def locate_transcript(text: str, where: str) -> str | None:
    """The text of the segments `where` points to: a timestamp inside a segment (or its start),
    or a range 'HH:MM:SS-HH:MM:SS' (every segment it overlaps). None when nothing matches;
    raises ValueError when `where` is not a timestamp."""
    parts = [p.strip() for p in re.split(r"\s*[-–—]\s*", where.strip(), maxsplit=1)]
    times = [parse_hms(p) for p in parts]
    if not parts or any(t is None for t in times):
        raise ValueError("not a timestamp")
    lo, hi = times[0], times[-1]
    if hi < lo:
        raise ValueError("the range ends before it starts")
    hits = [seg for seg in segments_of(text)
            if seg[0] <= hi and (lo < max(seg[1], seg[0] + 1) if len(times) == 1
                                 else lo <= seg[1])]
    return "\n".join(s[2] for s in hits) if hits else None


# --- tools ----------------------------------------------------------------------------------------

def _run(cmd: list[str], what: str) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = " ".join(proc.stderr.strip().splitlines()[-3:])
        raise StratError(f"ffmpeg could not {what}: {tail}", FAILED)
    return proc.stdout


def _ffmpeg() -> tuple[str, str] | None:
    ff, probe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    return (ff, probe) if ff and probe else None


def _duration(path: Path, tools: tuple[str, str] | None) -> float | None:
    if tools:
        out = _run([tools[1], "-v", "error", "-show_entries", "format=duration", "-of",
                    "csv=p=0", str(path)], f"read the length of {path.name}")
        try:
            return float(out.strip())
        except ValueError:
            return None
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path)) as w:
                return w.getnframes() / float(w.getframerate())
        except (wave.Error, EOFError):
            return None
    return None


def _has_audio(path: Path, probe: str) -> bool:
    out = _run([probe, "-v", "error", "-select_streams", "a", "-show_entries",
                "stream=index", "-of", "csv=p=0", str(path)], f"read the streams of {path.name}")
    return bool(out.strip())


# --- speech to text -------------------------------------------------------------------------------

class STT:
    """The configured engine: a remote endpoint, or local Whisper."""

    def __init__(self):
        conf = _conf()
        key = env("STRAT_STT_API_KEY")
        self.local = None
        if key:
            self.base = (env("STRAT_STT_BASE_URL") or "https://api.mistral.ai/v1").rstrip("/")
            self.key = key
            self.mistral = MISTRAL_HOST in self.base
            self.model = env("STRAT_STT_MODEL") or (conf.get("mistral_model", "")
                                                    if self.mistral else "")
            if not self.model:
                raise StratError("set STRAT_STT_MODEL in .env: the speech-to-text model of "
                                 f"{self.base}", UNAVAILABLE)
            return
        size = conf.get("whisper_model", "small")
        try:
            from faster_whisper import WhisperModel  # noqa: F401
            self.local, self.model = "faster-whisper", size
        except ImportError:
            try:
                import whisper  # noqa: F401
                self.local, self.model = "openai-whisper", size
            except ImportError:
                raise StratError(NO_STT, UNAVAILABLE) from None

    @property
    def label(self) -> str:
        return f"local {self.local} {self.model}" if self.local else self.model

    def transcribe(self, path: Path) -> tuple[list[dict], float | None]:
        """Segments (start, end, text, relative to the file) and billed audio seconds."""
        if self.local:
            return self._local(path), None
        fields = {"model": self.model}
        if self.mistral:
            fields["timestamp_granularities"] = "segment"
        else:  # OpenAI-style endpoints give segments only in verbose_json
            fields["response_format"] = "verbose_json"
            fields["timestamp_granularities[]"] = "segment"
        body, ctype = multipart(fields, {"file": (path.name, path.read_bytes(),
                                                  "application/octet-stream")})
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": ctype,
                   "Accept": "application/json"}
        timeout = int(_conf().get("timeout_sec", 300))
        for attempt in (1, 2):
            try:
                _, _, raw = net.post(self.base + "/audio/transcriptions", body, headers=headers,
                                     timeout=timeout)
                break
            except net.HttpError as exc:
                retry = exc.status is None or exc.status == 429 or exc.status >= 500
                if attempt == 1 and retry:
                    time.sleep(RETRY_PAUSE)
                    continue
                raise
        try:
            data = json.loads(raw)
        except ValueError:
            raise net.HttpError("the speech-to-text answer is not JSON") from None
        segs = [{"start": float(s.get("start") or 0), "end": float(s.get("end") or 0),
                 "text": str(s.get("text") or "").strip()}
                for s in data.get("segments") or [] if isinstance(s, dict)]
        if not segs and str(data.get("text") or "").strip():
            segs = [{"start": 0.0, "end": 0.0, "text": data["text"].strip()}]
        if not segs and "segments" not in data and "text" not in data:
            raise net.HttpError("the speech-to-text answer has no text or segments")
        usage = data.get("usage") or {}
        billed = usage.get("prompt_audio_seconds") or usage.get("seconds")
        return segs, (float(billed) if billed else None)

    def _local(self, path: Path) -> list[dict]:
        if self.local == "faster-whisper":
            from faster_whisper import WhisperModel

            segments, _ = WhisperModel(self.model, device="cpu",
                                       compute_type="int8").transcribe(str(path))
            return [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments]
        import whisper

        result = whisper.load_model(self.model).transcribe(str(path))
        return [{"start": s["start"], "end": s["end"], "text": s["text"].strip()}
                for s in result["segments"]]

    def usd(self, seconds: float) -> tuple[float, bool]:
        if self.local:
            return 0.0, False
        conf = _conf()
        rates = conf.get("usd_per_min") or {}
        estimated = self.model not in rates
        rate = float(conf.get("default_usd_per_min", 0.006) if estimated else rates[self.model])
        return seconds / 60 * rate, estimated


# --- the command ----------------------------------------------------------------------------------

def _chunks(cdir: Path, base: str, name: str, audio: Path, total: float | None,
            tools: tuple[str, str] | None, digest: str) -> tuple[list[dict], float, str, int]:
    """Transcribe chunk by chunk, reusing finished chunks. Returns (segments, usd, model,
    number of chunks)."""
    from strat.state import find_ok, log_action

    work = cdir / "media" / name
    work.mkdir(parents=True, exist_ok=True)
    size = float(_conf().get("chunk_sec", 600))
    if tools and total:
        n = max(1, math.ceil(total / size - 1e-6))
        spans = [(i * size, min(size, total - i * size)) for i in range(n)]
    else:  # no ffmpeg: the file goes up whole
        spans = [(0.0, total or 0.0)]
    stt, segments, spent, model = None, [], 0.0, ""
    for i, (start, length) in enumerate(spans, 1):
        step = f"{base}.chunk.{i:03d}"
        saved = work / f"chunk_{i:03d}.json"
        if find_ok(cdir, step) and saved.is_file():
            done = json.loads(saved.read_text(encoding="utf-8"))
            if done.get("sha256") == digest:
                segments += done["segments"]
                model = model or done.get("model", "")
                continue
        stt = stt or STT()
        if tools:
            piece = work / f"chunk_{i:03d}.mp3"
            _run([tools[0], "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{length:.3f}",
                  "-i", str(audio), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k",
                  str(piece)], f"cut chunk {i}")
        else:
            piece = audio
        started = time.monotonic()
        try:
            segs, billed = stt.transcribe(piece)
        except net.HttpError as exc:
            log_action(cdir, step=step, tool="media stt", in_=str(piece.relative_to(cdir)),
                       status="error", note=f"{stt.label}: {exc}",
                       sec=time.monotonic() - started)
            done_n = i - 1
            raise StratError(f"speech to text failed on chunk {i} of {len(spans)}: {exc}. "
                             f"{done_n} finished chunk{'s are' if done_n != 1 else ' is'} kept; "
                             "run the same command again to continue", UNAVAILABLE) from None
        end_cap = start + length if length else None
        shifted = []
        for s in segs:
            if not s["text"]:
                continue
            a = start + s["start"]
            b = start + max(s["end"], s["start"])
            if end_cap is not None:
                a, b = min(a, end_cap), min(b, end_cap)
            if b <= a:
                b = end_cap if end_cap is not None and end_cap > a else a + 1
            shifted.append({"start": round(a, 2), "end": round(b, 2), "text": s["text"]})
        seconds = billed or length or (shifted[-1]["end"] - start if shifted else 0.0)
        usd, estimated = stt.usd(seconds)
        saved.write_text(json.dumps({"sha256": digest, "model": stt.label, "start": start,
                                     "segments": shifted}, ensure_ascii=False, indent=1),
                         encoding="utf-8")
        note = (f"{stt.label}, {seconds:.1f} s of audio" + (", price estimated" if estimated
                                                            else ""))
        log_action(cdir, step=step, tool="media stt", in_=str(piece.relative_to(cdir)),
                   out=str(saved.relative_to(cdir)), usd=usd, note=note,
                   sec=time.monotonic() - started)
        segments += shifted
        spent += usd
        model = stt.label
    return segments, spent, model, len(spans)


def _transcript_text(origin: str, model: str, segments: list[dict]) -> str:
    lines = [f"# Расшифровка: {Path(origin).name}", "",
             f"> Файл: {origin}. Распознавание речи: {model}. Говорящие не определены; термины и "
             "цифры могли быть расслышаны неверно: число со слов остаётся гипотезой, пока его не "
             "подтвердит документ.", ""]
    for s in segments:
        lines += [f"## [{hms(math.floor(s['start']))} - {hms(math.ceil(s['end']))}]",
                  s["text"], ""]
    return "\n".join(lines)


def _frames(cdir: Path, name: str, video: Path, every: int, ffmpeg: str,
            origin: str) -> tuple[Path, int]:
    work = cdir / "media" / name
    work.mkdir(parents=True, exist_ok=True)
    for old in work.glob("frame_*.jpg"):
        old.unlink()
    # the first frame, then the first frame at least `every` seconds after the last one taken;
    # showinfo prints each written frame's real time, so the index never guesses
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostats", "-y", "-i", str(video), "-vf",
         f"select='isnan(prev_selected_t)+gte(t-prev_selected_t\\,{every})',showinfo",
         "-fps_mode", "vfr", "-q:v", "4", str(work / "frame_%04d.jpg")],
        capture_output=True, text=True)
    if proc.returncode != 0:
        tail = " ".join(proc.stderr.strip().splitlines()[-3:])
        raise StratError(f"ffmpeg could not take frames: {tail}", FAILED)
    times = [float(t) for t in re.findall(r"pts_time:\s*([0-9.]+)", proc.stderr)]
    frames = sorted(work.glob("frame_*.jpg"))
    lines = [f"# Кадры: {Path(origin).name}", "",
             f"> Файл: {origin}. Кадр примерно каждые {every} с; время - от начала видео.", ""]
    lines += [f"- {f.name} - {hms(times[k] if k < len(times) else k * every)}"
              for k, f in enumerate(frames)]
    index = work / "frames.md"
    index.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return index, len(frames)


def media(path: str, case: str | None = None, every: int = 10, step: str | None = None,
          as_json: bool = False) -> int:
    """Transcribe audio; split video into audio and frames. Registers the sources."""
    from strat import sources
    from strat.state import log_action, replay

    cdir = case_path(case)
    if replay(cdir, step, as_json, "media"):
        return 0
    if every < 1:
        raise StratError("--every must be at least 1 second")
    src = Path(path)
    if not src.is_absolute():
        src = cdir / path if (cdir / path).exists() else Path.cwd() / path
    if not src.is_file():
        raise StratError(f"{path}: file not found")
    suffix = src.suffix.lower()
    is_video = suffix in VIDEO_SUFFIXES
    if not is_video and suffix not in AUDIO_SUFFIXES:
        raise StratError(f"{src.name}: not an audio or video file; audio: "
                         f"{', '.join(sorted(AUDIO_SUFFIXES))}; video: "
                         f"{', '.join(sorted(VIDEO_SUFFIXES))}")
    tools = _ffmpeg()
    if is_video and not tools:
        raise StratError(f"{src.name}: video needs ffmpeg and ffprobe, which are not installed; "
                         f"{FFMPEG_HINT}. Audio files work without ffmpeg.", UNAVAILABLE)
    src = sources.into_materials(cdir, src)
    origin = str(src.relative_to(cdir.resolve()))
    name = re.sub(r"[^\w.-]+", "_", src.stem).strip("._") or "media"
    base = step or f"media.{name}"
    digest = sources.sha256(src.read_bytes())
    (cdir / "media").mkdir(exist_ok=True)
    started = time.monotonic()

    frames = None
    if is_video:
        index, count = _frames(cdir, name, src, every, tools[0], origin)
        entry = sources.register(cdir, kind="file", origin=str(index.relative_to(cdir)),
                                 title=f"Кадры: {src.name}", text=index.read_text("utf-8"),
                                 digest=sources.sha256(index.read_bytes()), fmt="frames",
                                 media=origin)
        frames = {"id": entry["id"], "path": str(index.relative_to(cdir)), "count": count,
                  "every": every, "dir": f"media/{name}"}
        has_audio = _has_audio(src, tools[1])
        audio = cdir / "media" / name / "audio.mp3"
        if has_audio:
            _run([tools[0], "-v", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar",
                  "16000", "-b:a", "32k", str(audio)], "take the audio track")
    else:
        has_audio, audio = True, src

    transcript, usd, chunks, warn_note = None, 0.0, 0, ""
    if has_audio:
        total = _duration(audio, tools)
        segments, usd, model, chunks = _chunks(cdir, base, name, audio, total, tools, digest)
        tpath = cdir / "media" / f"{name}.transcript.md"
        text = _transcript_text(origin, model, segments)
        tpath.write_text(text, encoding="utf-8")
        entry = sources.register(cdir, kind="file", origin=str(tpath.relative_to(cdir)),
                                 title=f"Расшифровка: {src.name}", text=text,
                                 digest=sources.sha256(text.encode("utf-8")), fmt="transcript",
                                 media=origin)
        transcript = {"id": entry["id"], "path": str(tpath.relative_to(cdir)),
                      "segments": len(segments), "model": model,
                      "flags": entry.get("flags", [])}
        if not tools:
            warn_note = ("ffmpeg not found: the file was sent whole; a long recording needs "
                         "ffmpeg to be cut into chunks")

    ref = transcript["id"] if transcript else frames["id"]
    out = transcript["path"] if transcript else frames["path"]
    log_action(cdir, step=base, tool="media", in_=origin, out=out, ref=ref,
               note=(f"{chunks} chunk(s), ${usd:.4f}" if transcript else "no audio track"),
               sec=time.monotonic() - started)

    lines = []
    if transcript:
        lines.append(f"transcript: {transcript['path']} registered as {transcript['id']} "
                     f"({transcript['segments']} segments, {chunks} chunk(s), "
                     f"{transcript['model']}, ${usd:.4f})")
        lines.append(f"cite: --source {transcript['id']} --where HH:MM:SS (a moment inside a "
                     "segment) --quote '<words from that segment>'")
    else:
        lines.append("transcript: none, the video has no audio track")
    if frames:
        lines.append(f"frames: {frames['count']} in {frames['dir']}/ every {every} s, index "
                     f"{frames['path']} registered as {frames['id']}; read only the frames near "
                     "the moment you need")
    if transcript and transcript["flags"]:
        lines.append(sources.FLAG_NOTE.format(sid=transcript["id"]))
    if warn_note:
        lines.append(warn_note)
    lines.append(LIMITS)
    emit("\n".join(lines), {"replayed": False, "origin": origin, "transcript": transcript,
                            "frames": frames, "chunks": chunks, "usd": round(usd, 6),
                            "note": warn_note}, as_json)
    return 0
