from __future__ import annotations

import json
import threading
import unittest
from unittest.mock import Mock, patch

from brightnova.ollama_manager import (
    OFFLINE,
    ONLINE,
    HealthResult,
    OllamaError,
    OllamaManager,
    OllamaModel,
    format_bytes,
)


class FakeResponse:
    def __init__(self, lines: list[bytes]):
        self.lines = lines
        self.closed = False

    def __iter__(self):
        return iter(self.lines)

    def close(self) -> None:
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


class FormattingTests(unittest.TestCase):
    def test_format_bytes(self) -> None:
        self.assertEqual(format_bytes(0), "0.0 B")
        self.assertEqual(format_bytes(1024), "1.0 KB")
        self.assertEqual(format_bytes(1024 ** 3), "1.0 GB")

    def test_model_display_name(self) -> None:
        model = OllamaModel(name="qwen2.5-coder:7b", size=100)
        self.assertEqual(model.display_name, "Qwen2.5 Coder 7B")
        self.assertEqual(model.size_label, "100.0 B")


class OllamaManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = OllamaManager("http://127.0.0.1:11434")

    def test_list_models_reads_api_metadata(self) -> None:
        self.manager._request = Mock(
            return_value={
                "models": [
                    {
                        "name": "qwen2.5-coder:7b",
                        "size": 4683087561,
                        "modified_at": "2026-01-01",
                        "details": {
                            "parameter_size": "7.6B",
                            "quantization_level": "Q4_K_M",
                            "family": "qwen2",
                        },
                    }
                ]
            }
        )
        models = self.manager.list_models()
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0].name, "qwen2.5-coder:7b")
        self.assertEqual(models[0].parameter_size, "7.6B")

    def test_running_models(self) -> None:
        self.manager._request = Mock(
            return_value={
                "models": [
                    {
                        "name": "qwen2.5-coder:3b",
                        "size": 1000,
                        "size_vram": 0,
                        "expires_at": "soon",
                    }
                ]
            }
        )
        models = self.manager.running_models()
        self.assertEqual(models[0].name, "qwen2.5-coder:3b")
        self.assertEqual(models[0].size_label, "1000.0 B")

    def test_health_reports_online_after_version_response(self) -> None:
        self.manager._request = Mock(return_value={"version": "0.40.11"})
        self.manager.systemd_active = Mock(return_value=False)
        self.manager.process_info = Mock(return_value=[])
        health = self.manager.health()
        self.assertEqual(health.status, ONLINE)
        self.assertEqual(health.version, "0.40.11")

    def test_health_reports_offline_on_api_error(self) -> None:
        self.manager._request = Mock(side_effect=OllamaError("refused"))
        self.manager.systemd_active = Mock(return_value=False)
        self.manager.process_info = Mock(return_value=[])
        health = self.manager.health()
        self.assertEqual(health.status, OFFLINE)
        self.assertIn("refused", health.message)

    def test_external_service_is_not_stopped_without_permission(self) -> None:
        self.manager.health = Mock(
            return_value=HealthResult(status=ONLINE, managed_by="external")
        )
        result = self.manager.stop_server(allow_service_stop=False)
        self.assertFalse(result.ok)
        self.assertIn("outside BrightNova", result.message)

    def test_load_and_unload_model_use_api(self) -> None:
        self.manager._request = Mock(return_value={})
        loaded = self.manager.load_model("qwen2.5-coder:7b")
        unloaded = self.manager.unload_model("qwen2.5-coder:3b")
        self.assertTrue(loaded.ok)
        self.assertTrue(unloaded.ok)
        self.assertEqual(self.manager._request.call_count, 2)
        unload_payload = self.manager._request.call_args_list[1].args[1]
        self.assertEqual(unload_payload["keep_alive"], 0)

    def test_chat_stream_aggregates_chunks(self) -> None:
        response = FakeResponse(
            [
                json.dumps({"message": {"content": "Hello "}}).encode() + b"\n",
                json.dumps({"message": {"content": "world"}}).encode() + b"\n",
                json.dumps({"done": True}).encode() + b"\n",
            ]
        )
        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            return response

        chunks = []
        with patch(
            "brightnova.ollama_manager.urllib.request.urlopen",
            side_effect=fake_urlopen,
        ):
            text = self.manager.chat_stream(
                "qwen2.5-coder:7b",
                [{"role": "user", "content": "Hi"}],
                chunks.append,
            )
        self.assertEqual(text, "Hello world")
        self.assertEqual("".join(chunks), "Hello world")
        payload = json.loads(captured["request"].data.decode())
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["model"], "qwen2.5-coder:7b")
        self.assertTrue(response.closed)

    def test_chat_stream_honours_cancellation(self) -> None:
        response = FakeResponse(
            [
                json.dumps({"message": {"content": "first"}}).encode() + b"\n",
                json.dumps({"message": {"content": "second"}}).encode() + b"\n",
            ]
        )
        cancel = threading.Event()
        chunks = []

        def on_chunk(chunk: str) -> None:
            chunks.append(chunk)
            cancel.set()

        with patch(
            "brightnova.ollama_manager.urllib.request.urlopen",
            return_value=response,
        ):
            text = self.manager.chat_stream(
                "qwen2.5-coder:7b",
                [{"role": "user", "content": "Hi"}],
                on_chunk,
                cancel_event=cancel,
            )
        self.assertEqual(text, "first")
        self.assertEqual(chunks, ["first"])

    def test_chat_stream_reports_ollama_error(self) -> None:
        response = FakeResponse(
            [json.dumps({"error": "model not found"}).encode() + b"\n"]
        )
        with patch(
            "brightnova.ollama_manager.urllib.request.urlopen",
            return_value=response,
        ):
            with self.assertRaises(OllamaError):
                self.manager.chat_stream(
                    "missing", [{"role": "user", "content": "Hi"}], lambda _chunk: None
                )


if __name__ == "__main__":
    unittest.main()
