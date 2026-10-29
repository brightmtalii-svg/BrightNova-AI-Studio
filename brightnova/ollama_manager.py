from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .config import config_dir


logger = logging.getLogger(__name__)

ONLINE = "ONLINE"
OFFLINE = "OFFLINE"
CONNECTING = "CONNECTING"


class OllamaError(RuntimeError):
    pass


@dataclass
class OllamaModel:
    name: str
    size: int = 0
    modified_at: str = ""
    parameter_size: str = ""
    quantization: str = ""
    family: str = ""

    @property
    def display_name(self) -> str:
        base = self.name.split(":")[0]
        tag = self.name.split(":", 1)[1] if ":" in self.name else ""
        words = []
        for part in base.replace("_", "-").split("-"):
            if not part:
                continue
            if part.lower() in {"qwen", "coder", "deepseek", "llama", "gemma", "phi"}:
                words.append(part.capitalize())
            elif part.replace(".", "").isdigit():
                words.append(part)
            else:
                words.append(part.capitalize())
        label = " ".join(words)
        if tag:
            label = f"{label} {tag.upper()}"
        return label or self.name

    @property
    def size_label(self) -> str:
        return format_bytes(self.size)


@dataclass
class RunningModel:
    name: str
    size: int = 0
    size_vram: int = 0
    expires_at: str = ""

    @property
    def size_label(self) -> str:
        return format_bytes(self.size)


@dataclass
class HealthResult:
    status: str = OFFLINE
    version: str = ""
    message: str = ""
    managed_by: str = "unknown"

    @property
    def online(self) -> bool:
        return self.status == ONLINE


@dataclass
class ActionResult:
    ok: bool
    message: str
    detail: str = ""


@dataclass
class ProcessInfo:
    pid: int
    name: str
    rss: int = 0
    cmdline: list[str] = field(default_factory=list)


def format_bytes(value: int | float) -> str:
    size = float(max(0, value))
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units[:-1]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} {units[-1]}"


def _clean_error(exc: BaseException) -> str:
    text = str(exc).strip()
    if isinstance(exc, urllib.error.HTTPError):
        try:
            body = exc.read().decode("utf-8", "replace").strip()
            parsed = json.loads(body)
            text = str(parsed.get("error") or body)
        except Exception:
            pass
    return text or exc.__class__.__name__


def _parse_ollama_host(host: str) -> str:
    parsed = urllib.parse.urlparse(host)
    hostname = parsed.hostname or "127.0.0.1"
    port = parsed.port or 11434
    return f"{hostname}:{port}"


class OllamaManager:
    def __init__(self, host: str = "http://127.0.0.1:11434"):
        self.host = host.rstrip("/")
        self._owned_process: subprocess.Popen[bytes] | None = None
        self._owned_log_handle = None
        self._active_response = None
        self._response_lock = threading.Lock()
        self._systemd_cache: bool | None = None

    def _url(self, path: str) -> str:
        return f"{self.host}{path}"

    def _request(
        self,
        path: str,
        payload: dict[str, Any] | None = None,
        method: str = "GET",
        timeout: float = 5.0,
    ) -> Any:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self._url(path), data=data, method=method, headers=headers
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise OllamaError(_clean_error(exc)) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise OllamaError(
                f"Cannot reach Ollama at {self.host}: {_clean_error(exc)}"
            ) from exc
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OllamaError("Ollama returned an invalid JSON response") from exc

    def process_info(self) -> list[ProcessInfo]:
        found: list[ProcessInfo] = []
        try:
            import psutil
        except ImportError:
            try:
                completed = subprocess.run(
                    ["pgrep", "-a", "ollama"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
            except (OSError, subprocess.SubprocessError):
                return found
            for line in completed.stdout.splitlines():
                pieces = line.split(None, 1)
                if pieces and pieces[0].isdigit():
                    found.append(
                        ProcessInfo(
                            pid=int(pieces[0]),
                            name="ollama",
                            cmdline=pieces[1].split() if len(pieces) > 1 else [],
                        )
                    )
            return found
        for process in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                name = (process.info.get("name") or "").lower()
                cmdline = process.info.get("cmdline") or []
                joined = " ".join(cmdline).lower()
                if name.startswith("ollama") or "ollama serve" in joined:
                    found.append(
                        ProcessInfo(
                            pid=process.pid,
                            name=process.info.get("name") or "ollama",
                            rss=process.memory_info().rss,
                            cmdline=list(cmdline),
                        )
                    )
            except (psutil.Error, OSError):
                continue
        return found

    def systemd_installed(self) -> bool:
        if self._systemd_cache is not None:
            return self._systemd_cache
        if not shutil.which("systemctl"):
            self._systemd_cache = False
            return False
        try:
            completed = subprocess.run(
                ["systemctl", "list-unit-files", "ollama.service", "--no-legend"],
                capture_output=True,
                text=True,
                timeout=4,
            )
            self._systemd_cache = "ollama.service" in completed.stdout
        except (OSError, subprocess.SubprocessError):
            self._systemd_cache = False
        return self._systemd_cache

    def systemd_active(self) -> bool:
        if not shutil.which("systemctl"):
            return False
        try:
            completed = subprocess.run(
                ["systemctl", "is-active", "--quiet", "ollama.service"],
                capture_output=True,
                timeout=3,
            )
            return completed.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def health(self, timeout: float = 2.0) -> HealthResult:
        managed_by = "offline"
        if self._owned_process is not None and self._owned_process.poll() is None:
            managed_by = "brightnova"
        elif self.systemd_active():
            managed_by = "systemd"
        else:
            processes = self.process_info()
            if processes:
                managed_by = "external"
        try:
            payload = self._request("/api/version", timeout=timeout)
            version = str(payload.get("version") or "")
            return HealthResult(
                status=ONLINE,
                version=version,
                message=f"Connected to Ollama {version}".strip(),
                managed_by=managed_by,
            )
        except OllamaError as exc:
            return HealthResult(
                status=OFFLINE,
                message=str(exc),
                managed_by=managed_by,
            )

    def list_models(self, timeout: float = 5.0) -> list[OllamaModel]:
        payload = self._request("/api/tags", timeout=timeout)
        models = []
        for item in payload.get("models") or []:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            details = item.get("details") or {}
            models.append(
                OllamaModel(
                    name=str(item.get("name")),
                    size=int(item.get("size") or 0),
                    modified_at=str(item.get("modified_at") or ""),
                    parameter_size=str(details.get("parameter_size") or ""),
                    quantization=str(details.get("quantization_level") or ""),
                    family=str(details.get("family") or ""),
                )
            )
        return sorted(models, key=lambda model: model.name)

    def running_models(self, timeout: float = 3.0) -> list[RunningModel]:
        payload = self._request("/api/ps", timeout=timeout)
        models = []
        for item in payload.get("models") or []:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            models.append(
                RunningModel(
                    name=str(item.get("name")),
                    size=int(item.get("size") or 0),
                    size_vram=int(item.get("size_vram") or 0),
                    expires_at=str(item.get("expires_at") or ""),
                )
            )
        return models

    def _wait_for_health(self, timeout: float = 30.0) -> HealthResult:
        deadline = time.monotonic() + timeout
        result = HealthResult()
        while time.monotonic() < deadline:
            result = self.health(timeout=1.0)
            if result.online:
                return result
            time.sleep(0.5)
        return result

    def _control_service(self, action: str) -> ActionResult:
        command = ["systemctl", action, "ollama.service"]
        if os.geteuid() != 0:
            if not shutil.which("pkexec"):
                return ActionResult(
                    False,
                    "Administrator access is required to control the Ollama service.",
                    "Install policykit-1 or run the command manually.",
                )
            command = ["pkexec"] + command
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=90,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return ActionResult(False, f"Could not {action} Ollama service.", str(exc))
        output = (completed.stderr or completed.stdout).strip()
        if completed.returncode != 0:
            return ActionResult(
                False,
                f"Systemd could not {action} the Ollama service.",
                output or f"Exit code {completed.returncode}",
            )
        return ActionResult(True, f"Ollama service {action} request completed.")

    def start_server(self, timeout: float = 35.0) -> ActionResult:
        current = self.health(timeout=1.5)
        if current.online:
            return ActionResult(
                True,
                "Ollama is already online.",
                f"Connected to an externally managed instance ({current.managed_by}).",
            )
        if self.systemd_installed():
            result = self._control_service("start")
            if not result.ok:
                return result
            health = self._wait_for_health(timeout)
            if health.online:
                return ActionResult(True, "Ollama started through systemd.", health.message)
            return ActionResult(
                False,
                "The Ollama service was started but did not become healthy.",
                health.message,
            )
        binary = shutil.which("ollama")
        if not binary:
            return ActionResult(
                False,
                "Ollama is not installed or is not on PATH.",
                "Install Ollama from https://ollama.com/download and try again.",
            )
        if self.process_info():
            health = self._wait_for_health(timeout)
            if health.online:
                return ActionResult(
                    True,
                    "Connected to the existing Ollama process.",
                    health.message,
                )
            return ActionResult(
                False,
                "An Ollama process exists but its API is not reachable.",
                health.message,
            )
        log_directory = config_dir() / "logs"
        log_directory.mkdir(parents=True, exist_ok=True)
        log_path = log_directory / "ollama.log"
        try:
            self._owned_log_handle = log_path.open("ab", buffering=0)
            environment = os.environ.copy()
            environment["OLLAMA_HOST"] = _parse_ollama_host(self.host)
            self._owned_process = subprocess.Popen(
                [binary, "serve"],
                stdout=self._owned_log_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=environment,
                start_new_session=True,
            )
        except OSError as exc:
            return ActionResult(False, "Unable to start Ollama.", str(exc))
        health = self._wait_for_health(timeout)
        if health.online:
            return ActionResult(
                True,
                "Ollama started by BrightNova.",
                f"Log file: {log_path}",
            )
        self.stop_server(allow_service_stop=False)
        return ActionResult(
            False,
            "Ollama did not become healthy after starting.",
            f"{health.message}\nSee {log_path} for details.",
        )

    def stop_server(self, allow_service_stop: bool = False) -> ActionResult:
        current = self.health(timeout=1.5)
        if not current.online:
            return ActionResult(True, "Ollama is already offline.")
        if self._owned_process is not None and self._owned_process.poll() is None:
            self._owned_process.terminate()
            try:
                self._owned_process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                self._owned_process.kill()
                try:
                    self._owned_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    return ActionResult(
                        False,
                        "The BrightNova-managed Ollama process did not stop.",
                    )
            self._close_owned_log()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if not self.health(timeout=0.8).online:
                    return ActionResult(True, "BrightNova's Ollama process stopped.")
                time.sleep(0.4)
            return ActionResult(False, "Ollama stopped but the API is still responding.")
        if current.managed_by == "systemd":
            if not allow_service_stop:
                return ActionResult(
                    False,
                    "Ollama is managed by systemd.",
                    "BrightNova will not stop an external service without confirmation.",
                )
            result = self._control_service("stop")
            if not result.ok:
                return result
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                if not self.health(timeout=0.8).online:
                    return ActionResult(True, "Ollama service stopped through systemd.")
                time.sleep(0.4)
            return ActionResult(False, "Systemd stopped the service but the API still responds.")
        return ActionResult(
            False,
            "Ollama is managed outside BrightNova.",
            "BrightNova did not terminate it. Stop it from its owning terminal or service manager.",
        )

    def restart_server(self, allow_service_stop: bool = True) -> ActionResult:
        current = self.health(timeout=1.5)
        if current.managed_by == "systemd":
            if not allow_service_stop:
                return ActionResult(False, "Restart cancelled.")
            result = self._control_service("restart")
            if not result.ok:
                return result
            health = self._wait_for_health(35)
            if health.online:
                return ActionResult(True, "Ollama service restarted.", health.message)
            return ActionResult(False, "Ollama did not become healthy after restart.", health.message)
        if self._owned_process is not None and self._owned_process.poll() is None:
            stopped = self.stop_server(allow_service_stop=False)
            if not stopped.ok:
                return stopped
            started = self.start_server()
            if started.ok:
                return ActionResult(True, "BrightNova's Ollama process restarted.", started.detail)
            return started
        if current.online:
            return ActionResult(
                False,
                "Ollama is managed outside BrightNova.",
                "Restart it from its owning terminal or service manager.",
            )
        return self.start_server()

    def load_model(self, model: str, timeout: float = 600.0) -> ActionResult:
        payload = self._request(
            "/api/generate",
            {"model": model, "keep_alive": "30m"},
            method="POST",
            timeout=timeout,
        )
        if payload.get("error"):
            raise OllamaError(str(payload["error"]))
        return ActionResult(True, f"{model} is loaded.")

    def unload_model(self, model: str) -> ActionResult:
        payload = self._request(
            "/api/generate",
            {"model": model, "keep_alive": 0},
            method="POST",
            timeout=30.0,
        )
        if payload.get("error"):
            raise OllamaError(str(payload["error"]))
        return ActionResult(True, f"{model} was unloaded.")

    def cancel_generation(self) -> None:
        with self._response_lock:
            response = self._active_response
        if response is not None:
            try:
                response.close()
            except Exception:
                logger.debug("Unable to close Ollama response cleanly", exc_info=True)

    def chat_stream(
        self,
        model: str,
        messages: Iterable[dict[str, str]],
        on_chunk: Callable[[str], None],
        cancel_event: threading.Event | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "messages": list(messages),
            "stream": True,
        }
        if options:
            payload["options"] = options
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self._url("/api/chat"),
            data=data,
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/x-ndjson"},
        )
        output: list[str] = []
        response = None
        try:
            response = urllib.request.urlopen(request, timeout=300)
            with self._response_lock:
                self._active_response = response
            for raw_line in response:
                if cancel_event is not None and cancel_event.is_set():
                    break
                line = raw_line.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if item.get("error"):
                    raise OllamaError(str(item["error"]))
                content = (item.get("message") or {}).get("content") or ""
                if content:
                    output.append(content)
                    on_chunk(content)
                if item.get("done"):
                    break
        except urllib.error.HTTPError as exc:
            raise OllamaError(_clean_error(exc)) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if cancel_event is not None and cancel_event.is_set():
                return "".join(output)
            raise OllamaError(
                f"Ollama chat request failed: {_clean_error(exc)}"
            ) from exc
        finally:
            with self._response_lock:
                self._active_response = None
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass
        return "".join(output)

    def _close_owned_log(self) -> None:
        if self._owned_log_handle is not None:
            try:
                self._owned_log_handle.close()
            except OSError:
                pass
            self._owned_log_handle = None

    def shutdown(self) -> None:
        self.cancel_generation()
        self._close_owned_log()
