#!/usr/bin/env python3
"""Independent stdlib tests for the narrative-video audio tools."""

from __future__ import annotations

import base64
from contextlib import contextmanager
import importlib.util
import io
import json
from pathlib import Path
import os
import tempfile
import threading
import unittest
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SYNTH = load_module("narrative_synthesize_full", ROOT / "scripts/synthesize_full.py")
ALIGN = load_module("narrative_align_narration", ROOT / "scripts/align_narration.py")


def wav_bytes(duration_ms: int, sample_rate: int = 1000) -> bytes:
    frame_count = round(duration_ms * sample_rate / 1000)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * frame_count)
    return buffer.getvalue()


class MockTTSHandler(BaseHTTPRequestHandler):
    response_body = wav_bytes(2200)
    response_status = 200
    response_content_type = "audio/wav"
    redirect_location = None
    received = []

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        type(self).received.append({"headers": dict(self.headers), "body": body})
        if type(self).redirect_location:
            self.send_response(302)
            self.send_header("Location", type(self).redirect_location)
            self.end_headers()
            return
        self.send_response(type(self).response_status)
        self.send_header("Content-Type", type(self).response_content_type)
        self.send_header("Content-Length", str(len(type(self).response_body)))
        self.end_headers()
        self.wfile.write(type(self).response_body)

    def log_message(self, format, *args):  # noqa: A002 - stdlib hook
        return


@contextmanager
def mock_server():
    MockTTSHandler.received = []
    MockTTSHandler.response_status = 200
    MockTTSHandler.response_body = wav_bytes(2200)
    MockTTSHandler.response_content_type = "audio/wav"
    MockTTSHandler.redirect_location = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockTTSHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def write_tts_config(root: Path, endpoint: str, *, max_text_bytes: int = 1024) -> Path:
    path = root / "tts.json"
    path.write_text(
        json.dumps(
            {
                "provider": "doubao",
                "endpoint": endpoint,
                "resource_id": "test-resource",
                "auth_mode": "bearer_semicolon",
                "access_token_env": "NARRATIVE_TEST_TOKEN",
                "speaker": "test-speaker",
                "uid": "test-project",
                "model": "test-model",
                "audio_format": "wav",
                "sample_rate": 1000,
                "max_text_bytes": max_text_bytes,
                "timeout_seconds": 5,
                "allow_insecure_localhost": True,
            }
        ),
        encoding="utf-8",
    )
    return path


class AudioToolsTests(unittest.TestCase):
    def test_tts_dry_run_single_request_and_validated_cache(self):
        with tempfile.TemporaryDirectory() as directory, mock_server() as server:
            root = Path(directory)
            text = "第一段，Codex 在 2026 年继续工作。\n第二段保留停顿。"
            (root / "script").mkdir()
            (root / "script/narration.txt").write_text(text, encoding="utf-8")
            endpoint = f"http://127.0.0.1:{server.server_port}/tts"
            config = write_tts_config(root, endpoint)
            old_token = os.environ.get("NARRATIVE_TEST_TOKEN")
            os.environ["NARRATIVE_TEST_TOKEN"] = "unit-test-token"
            try:
                dry = SYNTH.run_tts(
                    project_root=root,
                    text_path="script/narration.txt",
                    config_path=str(config),
                    output_path="audio/vo-full.wav",
                    dry_run=True,
                )
                self.assertTrue(dry["dry_run"])
                self.assertEqual(dry["request_count"], 1)
                self.assertEqual(len(MockTTSHandler.received), 0)
                self.assertFalse((root / "audio/vo-full.wav").exists())

                generated = SYNTH.run_tts(
                    project_root=root,
                    text_path="script/narration.txt",
                    config_path=str(config),
                    output_path="audio/vo-full.wav",
                )
                self.assertFalse(generated["cache_hit"])
                self.assertEqual(len(MockTTSHandler.received), 1)
                payload = json.loads(MockTTSHandler.received[0]["body"])
                self.assertEqual(payload["req_params"]["text"], text)
                self.assertEqual(payload["req_params"]["speaker"], "test-speaker")
                self.assertNotIn("unit-test-token", MockTTSHandler.received[0]["body"].decode("utf-8"))
                self.assertEqual(generated["duration_ms"], 2200)
                self.assertTrue((root / "audio/vo-full.wav.meta.json").is_file())

                cached = SYNTH.run_tts(
                    project_root=root,
                    text_path="script/narration.txt",
                    config_path=str(config),
                    output_path="audio/vo-full.wav",
                )
                self.assertTrue(cached["cache_hit"])
                self.assertEqual(len(MockTTSHandler.received), 1)
            finally:
                if old_token is None:
                    os.environ.pop("NARRATIVE_TEST_TOKEN", None)
                else:
                    os.environ["NARRATIVE_TEST_TOKEN"] = old_token

    def test_tts_limit_fails_without_splitting_or_network(self):
        with tempfile.TemporaryDirectory() as directory, mock_server() as server:
            root = Path(directory)
            (root / "script").mkdir()
            (root / "script/narration.txt").write_text("中文文本超出限制", encoding="utf-8")
            config = write_tts_config(root, f"http://127.0.0.1:{server.server_port}/tts", max_text_bytes=4)
            with self.assertRaises(SYNTH.TTSUserError) as caught:
                SYNTH.run_tts(
                    project_root=root,
                    text_path="script/narration.txt",
                    config_path=str(config),
                    output_path="audio/vo-full.wav",
                )
            self.assertIn("will not split", str(caught.exception))
            self.assertEqual(len(MockTTSHandler.received), 0)

    def test_tts_provider_failure_and_redirect_do_not_leak_secret(self):
        with tempfile.TemporaryDirectory() as directory, mock_server() as server:
            root = Path(directory)
            (root / "script").mkdir()
            (root / "script/narration.txt").write_text("失败测试", encoding="utf-8")
            config = write_tts_config(root, f"http://127.0.0.1:{server.server_port}/tts")
            old_token = os.environ.get("NARRATIVE_TEST_TOKEN")
            secret = "secret-token-that-must-not-appear"
            os.environ["NARRATIVE_TEST_TOKEN"] = secret
            try:
                MockTTSHandler.response_status = 500
                MockTTSHandler.response_body = ("provider body " + secret).encode("utf-8")
                with self.assertRaises(SYNTH.TTSRequestError) as caught:
                    SYNTH.run_tts(
                        project_root=root,
                        text_path="script/narration.txt",
                        config_path=str(config),
                        output_path="audio/vo-full.wav",
                    )
                self.assertNotIn(secret, str(caught.exception))

                MockTTSHandler.response_status = 200
                MockTTSHandler.redirect_location = f"http://127.0.0.1:{server.server_port}/other"
                with self.assertRaises(SYNTH.NoRedirectError):
                    SYNTH.run_tts(
                        project_root=root,
                        text_path="script/narration.txt",
                        config_path=str(config),
                        output_path="audio/vo-full.wav",
                    )
                self.assertFalse((root / "audio/vo-full.wav").exists())
            finally:
                if old_token is None:
                    os.environ.pop("NARRATIVE_TEST_TOKEN", None)
                else:
                    os.environ["NARRATIVE_TEST_TOKEN"] = old_token

    def test_alignment_manual_timestamps_preserve_source_and_silence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "script").mkdir()
            (root / "audio").mkdir()
            source = "你好，Codex 在 2026 年工作。\n"
            (root / "script/narration.txt").write_text(source, encoding="utf-8")
            (root / "audio/vo-full.wav").write_bytes(wav_bytes(2200))
            timestamps = [
                {"text": "你好", "start_ms": 100, "end_ms": 400},
                {"text": "Codex", "start_ms": 800, "end_ms": 1200},
                {"text": "在 2026 年工作", "start_ms": 1500, "end_ms": 2000},
            ]
            (root / "timestamps.json").write_text(json.dumps(timestamps), encoding="utf-8")
            result = ALIGN.run_alignment(
                project_root=root,
                text_path="script/narration.txt",
                audio_path="audio/vo-full.wav",
                output_path="audio/alignment.json",
                backend="python",
                timestamps_path="timestamps.json",
            )
            self.assertEqual(result["method"], "known-text-manual")
            artifact = json.loads((root / "audio/alignment.json").read_text(encoding="utf-8"))
            self.assertEqual("".join(segment["text"] for segment in artifact["segments"]), source)
            measured = [segment for segment in artifact["segments"] if segment["start_ms"] is not None]
            self.assertEqual([(item["start_ms"], item["end_ms"]) for item in measured], [(100, 400), (800, 1200), (1500, 2000)])
            self.assertFalse(any(item["code"] == "UNALIGNED_SOURCE_GAP" for item in artifact["issues"]))
            self.assertIn("，", measured[0]["text"])
            self.assertFalse(artifact["reviewed"])
            self.assertEqual(artifact["audio_path"], "audio/vo-full.wav")

    def test_alignment_asr_backend_is_distinct_and_reports_difference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "script").mkdir()
            (root / "audio").mkdir()
            source = "你好，Codex。"
            (root / "script/narration.txt").write_text(source, encoding="utf-8")
            (root / "audio/vo-full.wav").write_bytes(wav_bytes(1200))
            asr = {"result": {"utterances": [{"text": "你好", "start_time": 100, "end_time": 400}, {"text": "CODEX", "start_time": 700, "end_time": 1000}]}}
            (root / "asr.json").write_text(json.dumps(asr), encoding="utf-8")
            result = ALIGN.run_alignment(
                project_root=root,
                text_path="script/narration.txt",
                audio_path="audio/vo-full.wav",
                output_path="audio/alignment.json",
                backend="asr",
                asr_json_path="asr.json",
            )
            artifact = json.loads((root / "audio/alignment.json").read_text(encoding="utf-8"))
            self.assertEqual(result["method"], "asr-transcript-mapped")
            self.assertEqual(artifact["method"], "asr-transcript-mapped")
            self.assertTrue(any(item["code"] == "TEXT_FORMAT_DIFFERENCE" for item in artifact["issues"]))

    def test_alignment_import_rejects_overlap_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "script").mkdir()
            (root / "audio").mkdir()
            (root / "script/narration.txt").write_text("甲乙", encoding="utf-8")
            (root / "audio/vo-full.wav").write_bytes(wav_bytes(1000))
            timestamps = [{"text": "甲", "start_ms": 100, "end_ms": 700}, {"text": "乙", "start_ms": 600, "end_ms": 900}]
            (root / "bad.json").write_text(json.dumps(timestamps), encoding="utf-8")
            with self.assertRaises(ALIGN.AlignmentError):
                ALIGN.run_alignment(
                    project_root=root,
                    text_path="script/narration.txt",
                    audio_path="audio/vo-full.wav",
                    output_path="audio/alignment.json",
                    backend="python",
                    timestamps_path="bad.json",
                )
            self.assertFalse((root / "audio/alignment.json").exists())

    def test_python_backend_marks_unmeasured_coarse_span(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "script").mkdir()
            (root / "audio").mkdir()
            (root / "script/narration.txt").write_text("整篇原稿", encoding="utf-8")
            (root / "audio/vo-full.wav").write_bytes(wav_bytes(900))
            ALIGN.run_alignment(
                project_root=root,
                text_path="script/narration.txt",
                audio_path="audio/vo-full.wav",
                output_path="audio/alignment.json",
                backend="python",
            )
            artifact = json.loads((root / "audio/alignment.json").read_text(encoding="utf-8"))
            self.assertEqual(artifact["method"], "python-coarse")
            self.assertEqual(artifact["segments"], [{"id": "seg-001", "text": "整篇原稿", "start_ms": 0, "end_ms": 900}])
            self.assertEqual(artifact["issues"][0]["code"], "NO_INTERNAL_BOUNDARIES")


if __name__ == "__main__":
    unittest.main()
