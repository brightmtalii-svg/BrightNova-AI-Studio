from __future__ import annotations

import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .config import Project


logger = logging.getLogger(__name__)


class ProjectError(RuntimeError):
    pass


@dataclass
class LaunchResult:
    ok: bool
    message: str
    detail: str = ""


def _strip_jsonc(text: str) -> str:
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    length = len(text)
    while index < length:
        char = text[index]
        nxt = text[index + 1] if index + 1 < length else ""
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if char == "/" and nxt == "/":
            index += 2
            while index < length and text[index] not in "\r\n":
                index += 1
            continue
        if char == "/" and nxt == "*":
            index += 2
            while index + 1 < length and text[index : index + 2] != "*/":
                index += 1
            index += 2
            continue
        output.append(char)
        index += 1
    cleaned = "".join(output)
    cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)
    return cleaned


def parse_jsonc(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(_strip_jsonc(text))
    except json.JSONDecodeError as exc:
        raise ProjectError(f"Invalid OpenCode configuration: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProjectError("OpenCode configuration must be a JSON object.")
    return payload


class ProjectManager:
    def __init__(self, opencode_host: str = "http://127.0.0.1:11434"):
        self.opencode_host = opencode_host.rstrip("/")

    def validate_directory(self, path: str) -> Path:
        expanded = Path(path).expanduser()
        try:
            resolved = expanded.resolve(strict=True)
        except OSError as exc:
            raise ProjectError(f"Project directory does not exist: {expanded}") from exc
        if not resolved.is_dir():
            raise ProjectError(f"Not a directory: {resolved}")
        return resolved

    def config_path(self, project_path: str | Path) -> Path:
        directory = Path(project_path)
        jsonc = directory / "opencode.jsonc"
        plain = directory / "opencode.json"
        if jsonc.exists():
            return jsonc
        if plain.exists():
            return plain
        return plain

    def read_config(self, project_path: str | Path) -> dict[str, Any]:
        path = self.config_path(project_path)
        if not path.exists():
            return {}
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ProjectError(f"Unable to read {path}: {exc}") from exc
        return parse_jsonc(text)

    def merge_config(
        self,
        existing: dict[str, Any],
        model: str,
        installed_models: Iterable[str],
    ) -> dict[str, Any]:
        merged = json.loads(json.dumps(existing))
        merged.setdefault("$schema", "https://opencode.ai/config.json")
        provider = merged.get("provider")
        if provider is None:
            provider = {}
            merged["provider"] = provider
        if not isinstance(provider, dict):
            raise ProjectError("The existing 'provider' setting is not an object.")
        ollama = provider.get("ollama")
        if ollama is None:
            ollama = {}
            provider["ollama"] = ollama
        if not isinstance(ollama, dict):
            raise ProjectError("The existing 'ollama' provider is not an object.")
        ollama["npm"] = "@ai-sdk/openai-compatible"
        ollama["name"] = "Ollama (local)"
        options = ollama.get("options")
        if options is None:
            options = {}
            ollama["options"] = options
        if not isinstance(options, dict):
            raise ProjectError("The existing Ollama provider options are not an object.")
        options["baseURL"] = f"{self.opencode_host}/v1"
        models = ollama.get("models")
        if models is None:
            models = {}
            ollama["models"] = models
        if not isinstance(models, dict):
            raise ProjectError("The existing Ollama model map is not an object.")
        model_ids = {str(name) for name in installed_models if name}
        model_ids.add(model)
        for model_id in sorted(model_ids):
            entry = models.get(model_id)
            if not isinstance(entry, dict):
                entry = {}
            entry.setdefault("name", model_id)
            models[model_id] = entry
        merged["model"] = f"ollama/{model}"
        return merged

    def _atomic_write(self, path: Path, text: str) -> None:
        descriptor, temporary = tempfile.mkstemp(
            prefix=".brightnova-opencode-", suffix=path.suffix, dir=path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def configure(
        self,
        project: Project,
        installed_models: Iterable[str],
        allow_existing: bool = False,
    ) -> dict[str, Any]:
        directory = self.validate_directory(project.path)
        path = self.config_path(directory)
        existing = self.read_config(directory) if path.exists() else {}
        if path.exists() and not allow_existing:
            raise ProjectError(
                "This project already has an OpenCode configuration. "
                "Confirmation is required before updating it."
            )
        merged = self.merge_config(existing, project.model, installed_models)
        backup = ""
        if path.exists():
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            backup_path = path.with_name(f"{path.name}.brightnova-{stamp}.bak")
            try:
                backup_path.write_bytes(path.read_bytes())
                backup = str(backup_path)
            except OSError as exc:
                raise ProjectError(f"Unable to back up {path}: {exc}") from exc
        try:
            self._atomic_write(path, json.dumps(merged, indent=2) + "\n")
        except OSError as exc:
            raise ProjectError(f"Unable to write {path}: {exc}") from exc
        return {
            "path": str(path),
            "backup": backup,
            "model": f"ollama/{project.model}",
            "config": merged,
        }

    def open_vscode(self, project: Project) -> LaunchResult:
        directory = self.validate_directory(project.path)
        binary = shutil.which("code")
        if not binary:
            raise ProjectError("VS Code was not found on PATH.")
        try:
            subprocess.Popen(
                [binary, str(directory)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise ProjectError(f"Unable to open VS Code: {exc}") from exc
        return LaunchResult(True, f"Opening {directory.name} in VS Code.")

    def _terminal_command(self, directory: Path) -> list[str] | None:
        shell_command = (
            f"cd {shlex.quote(str(directory))} && exec opencode ."
        )
        if shutil.which("ptyxis"):
            return [
                "ptyxis",
                "--new-window",
                "--working-directory",
                str(directory),
                "--",
                "opencode",
                ".",
            ]
        if shutil.which("gnome-terminal"):
            return [
                "gnome-terminal",
                "--working-directory",
                str(directory),
                "--",
                "opencode",
                ".",
            ]
        if shutil.which("konsole"):
            return ["konsole", "--workdir", str(directory), "-e", "opencode", "."]
        if shutil.which("xfce4-terminal"):
            return [
                "xfce4-terminal",
                "--working-directory",
                str(directory),
                "-x",
                "opencode",
                ".",
            ]
        if shutil.which("kitty"):
            return ["kitty", "--directory", str(directory), "opencode", "."]
        if shutil.which("xterm"):
            return ["xterm", "-e", "bash", "-lc", shell_command]
        if shutil.which("x-terminal-emulator"):
            return ["x-terminal-emulator", "-e", "bash", "-lc", shell_command]
        return None

    def launch_opencode(self, project: Project) -> LaunchResult:
        directory = self.validate_directory(project.path)
        if not shutil.which("opencode"):
            raise ProjectError("OpenCode was not found on PATH.")
        command = self._terminal_command(directory)
        if not command:
            raise ProjectError(
                "No supported terminal emulator was found. "
                "Install ptyxis, GNOME Terminal, Konsole, Xfce Terminal, or xterm."
            )
        try:
            subprocess.Popen(
                command,
                cwd=str(directory),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise ProjectError(f"Unable to launch OpenCode: {exc}") from exc
        return LaunchResult(
            True,
            f"Launching OpenCode in {directory.name}.",
            "The local model must be configured before OpenCode can use it.",
        )

    def opencode_version(self) -> str:
        binary = shutil.which("opencode")
        if not binary:
            return ""
        try:
            completed = subprocess.run(
                [binary, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        output = (completed.stdout or completed.stderr).strip()
        return output.splitlines()[0] if output else ""
