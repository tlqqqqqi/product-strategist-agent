"""strat media (Task 13a): audio and video into transcript sources that claims cite by timestamp.
No network: `net.post` is replaced by a fake speech-to-text endpoint. The fixtures are a
synthetic Russian clip made with macOS `say` and a test-pattern video built from it."""

import email.parser
import json
import shutil
import sys

import pytest

from conftest import REPO
from strat import media, net
from strat.core import read_jsonl

FIX = REPO / "tests" / "fixtures" / "media"
STT_KEYS = ("STRAT_STT_API_KEY", "STRAT_STT_BASE_URL", "STRAT_STT_MODEL")
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                                  reason="ffmpeg is not installed")

SEG1 = "Отток в октябре вырос до шести процентов."
SEG2 = "Цену проверим в декабре."


def parse_multipart(body: bytes, content_type: str) -> dict:
    """The real contract: a standard MIME parser reads the fields and the file back."""
    msg = email.parser.BytesParser().parsebytes(
        b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body)
    assert msg.is_multipart()
    out = {}
    for part in msg.get_payload():
        name = part.get_param("name", header="content-disposition")
        filename = part.get_param("filename", header="content-disposition")
        payload = part.get_payload(decode=True)
        out[name] = (filename, payload) if filename else payload.decode("utf-8")
    return out


class FakeSTT:
    """Answers each request with segments relative to the uploaded chunk; can fail once."""

    def __init__(self, segments=None, fail_on=None):
        self.calls = []
        self.segments = segments or [{"start": 0.0, "end": 2.1, "text": SEG1},
                                     {"start": 2.1, "end": 4.3, "text": SEG2}]
        self.fail_on = fail_on  # file name that fails the first time it is sent

    def __call__(self, url, body, headers=None, timeout=30, max_bytes=None):
        fields = parse_multipart(body, headers["Content-Type"])
        filename = fields["file"][0]
        self.calls.append({"url": url, "headers": headers, "fields": fields, "file": filename})
        if filename == self.fail_on:
            self.fail_on = None
            raise net.HttpError("HTTP 400 for test: bad chunk", 400)
        return 200, {}, json.dumps({"model": fields["model"], "segments": self.segments,
                                    "usage": {"prompt_audio_seconds": 4}}).encode()


@pytest.fixture
def stt(monkeypatch):
    for k in STT_KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("STRAT_STT_API_KEY", "stt-key")
    monkeypatch.setenv("STRAT_STT_BASE_URL", "https://api.mistral.ai/v1")
    monkeypatch.setattr(media, "RETRY_PAUSE", 0)
    fake = FakeSTT()
    monkeypatch.setattr(net, "post", fake)
    return fake


def put(case, name):
    shutil.copy(FIX / name, case / "materials" / name)
    return f"materials/{name}"


def add_claim(strat, source, where, quote):
    return strat("claim", "add", "--type", "hypothesis", "--kind", "product_metric",
                 "--text", "Отток в октябре вырос до 6% (со слов, не подтверждено документом)",
                 "--source", source, "--where", where, "--quote", quote, "--as-of", "2026-10-31")


@needs_ffmpeg
def test_audio_becomes_a_transcript_source_cited_by_timestamp(strat, case, stt):
    r = strat("media", put(case, "speech_ru.mp3"), "--json")
    assert r.code == 0, r.err
    sid = r.data["transcript"]["id"]
    transcript = (case / "media" / "speech_ru.transcript.md").read_text()
    assert SEG1 in transcript and SEG2 in transcript

    # the request: Mistral's default model, segment timestamps, the key only in the header
    call = stt.calls[0]
    assert call["url"] == "https://api.mistral.ai/v1/audio/transcriptions"
    assert call["fields"]["model"] == "voxtral-mini-transcribe-3-0"
    assert call["fields"]["timestamp_granularities"] == "segment"
    assert call["headers"]["Authorization"] == "Bearer stt-key"

    # a quote from the segment the timestamp falls in passes; from another segment it fails
    assert add_claim(strat, sid, "00:00:01", "вырос до шести процентов").code == 0
    assert add_claim(strat, sid, "00:00:03", "проверим в декабре").code == 0
    bad = add_claim(strat, sid, "00:00:01", "Цену проверим")
    assert bad.code == 1 and "quote not found in 00:00:01" in bad.err
    wrong = add_claim(strat, sid, "00:09:00", "вырос")
    assert wrong.code == 1 and "no segment" in wrong.err

    # the call is logged with its price
    rows = [x for x in read_jsonl(case / "log.jsonl") if x["tool"] == "media stt"]
    assert len(rows) == 1 and rows[0]["usd"] > 0 and rows[0]["status"] == "ok"
    assert "stt-key" not in (case / "log.jsonl").read_text()


@needs_ffmpeg
def test_media_step_replays_without_a_second_call(strat, case, stt):
    path = put(case, "speech_ru.mp3")
    assert strat("media", path, "--step", "media.call").code == 0
    again = strat("media", path, "--step", "media.call", "--json")
    assert again.code == 0 and again.data["replayed"] is True
    assert len(stt.calls) == 1


@needs_ffmpeg
def test_video_yields_frames_with_timestamps_and_a_transcript(strat, case, stt):
    r = strat("media", put(case, "clip.mp4"), "--every", "2", "--json")
    assert r.code == 0, r.err
    frames = sorted((case / "media" / "clip").glob("frame_*.jpg"))
    assert [f.name for f in frames] == ["frame_0001.jpg", "frame_0002.jpg", "frame_0003.jpg"]
    index = (case / "media" / "clip" / "frames.md").read_text()
    assert "frame_0002.jpg" in index and "00:00:02" in index
    assert (case / "media" / "clip.transcript.md").is_file()
    assert r.data["frames"]["count"] == 3
    assert add_claim(strat, r.data["transcript"]["id"], "00:00:01", "шести процентов").code == 0


def test_video_without_ffmpeg_is_refused(strat, case, stt, monkeypatch, tmp_path):
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    r = strat("media", put(case, "clip.mp4"))
    assert r.code == 2
    assert "ffmpeg" in r.err and "video" in r.err
    assert stt.calls == [] and not (case / "media" / "clip.transcript.md").exists()


def test_no_endpoint_and_no_local_whisper_exits_2(strat, case, monkeypatch):
    for k in STT_KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setitem(sys.modules, "faster_whisper", None)  # import raises ImportError
    monkeypatch.setitem(sys.modules, "whisper", None)
    r = strat("media", put(case, "speech_ru.mp3"))
    assert r.code == 2
    assert "STRAT_STT_API_KEY" in r.err and "whisper" in r.err


@needs_ffmpeg
def test_chunked_transcription_resumes_without_redoing_finished_chunks(strat, case, stt,
                                                                       monkeypatch):
    conf = dict(media._conf(), chunk_sec=2)
    monkeypatch.setattr(media, "_conf", lambda: conf)
    stt.segments = [{"start": 0.0, "end": 1.5, "text": "кусок"}]
    stt.fail_on = "chunk_002.mp3"
    path = put(case, "speech_ru.mp3")

    first = strat("media", path)
    assert first.code == 2 and "chunk 2" in first.err
    assert [c["file"] for c in stt.calls] == ["chunk_001.mp3", "chunk_002.mp3"]

    second = strat("media", path, "--json")
    assert second.code == 0, second.err
    assert [c["file"] for c in stt.calls[2:]] == ["chunk_002.mp3", "chunk_003.mp3"]

    # offsets: each chunk's segments are shifted by the chunk start
    transcript = (case / "media" / "speech_ru.transcript.md").read_text()
    assert "## [00:00:00 - 00:00:02]" in transcript
    assert "## [00:00:02 - 00:00:04]" in transcript
    assert "## [00:00:04 - 00:00:05]" in transcript  # clipped to the file end
    ok_chunks = [x["step"] for x in read_jsonl(case / "log.jsonl")
                 if x["tool"] == "media stt" and x["status"] == "ok"]
    assert ok_chunks == ["media.speech_ru.chunk.001", "media.speech_ru.chunk.002",
                         "media.speech_ru.chunk.003"]


def test_audio_without_ffmpeg_goes_up_whole(strat, case, stt, monkeypatch, tmp_path):
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    r = strat("media", put(case, "speech_ru.mp3"), "--json")
    assert r.code == 0, r.err
    assert [c["file"] for c in stt.calls] == ["speech_ru.mp3"]
    assert "ffmpeg not found" in r.data["note"]
    assert add_claim(strat, r.data["transcript"]["id"], "00:00:03", "Цену проверим").code == 0
