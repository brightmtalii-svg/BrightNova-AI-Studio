from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from brightnova.config import Project
from brightnova.project_manager import ProjectError, ProjectManager, parse_jsonc


class JsoncTests(unittest.TestCase):
    def test_comments_and_trailing_commas(self) -> None:
        text = """
        {
          // line comment
          "model": "anthropic/example",
          "provider": {
            /* block comment */
            "anthropic": {"options": {"baseURL": "https://example.test"}},
          },
        }
        """
        payload = parse_jsonc(text)
        self.assertEqual(payload["model"], "anthropic/example")
        self.assertIn("anthropic", payload["provider"])

    def test_strings_with_comment_markers(self) -> None:
        payload = parse_jsonc('{"value": "https://example.test/a//b", "x": 1}')
        self.assertEqual(payload["value"], "https://example.test/a//b")


class ProjectManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.project_dir = self.root / "BrightLend"
        self.project_dir.mkdir()
        self.manager = ProjectManager("http://127.0.0.1:11434")
        self.project = Project(
            name="BrightLend",
            path=str(self.project_dir),
            model="qwen2.5-coder:7b",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_configure_creates_local_provider(self) -> None:
        result = self.manager.configure(
            self.project,
            ["qwen2.5-coder:7b", "qwen2.5-coder:3b"],
        )
        path = Path(result["path"])
        self.assertTrue(path.exists())
        payload = json.loads(path.read_text(encoding="utf-8"))
        ollama = payload["provider"]["ollama"]
        self.assertEqual(ollama["npm"], "@ai-sdk/openai-compatible")
        self.assertEqual(ollama["options"]["baseURL"], "http://127.0.0.1:11434/v1")
        self.assertIn("qwen2.5-coder:7b", ollama["models"])
        self.assertIn("qwen2.5-coder:3b", ollama["models"])
        self.assertEqual(payload["model"], "ollama/qwen2.5-coder:7b")
        self.assertEqual(result["backup"], "")

    def test_existing_configuration_requires_permission(self) -> None:
        path = self.project_dir / "opencode.json"
        path.write_text('{"provider": {"anthropic": {}}}', encoding="utf-8")
        with self.assertRaises(ProjectError):
            self.manager.configure(self.project, ["qwen2.5-coder:7b"])
        self.assertEqual(
            json.loads(path.read_text(encoding="utf-8")),
            {"provider": {"anthropic": {}}},
        )

    def test_existing_providers_are_preserved_and_backup_created(self) -> None:
        path = self.project_dir / "opencode.jsonc"
        path.write_text(
            """
            {
              "model": "anthropic/claude",
              "provider": {
                "anthropic": {"options": {"baseURL": "https://example.test"}}
              },
            }
            """,
            encoding="utf-8",
        )
        result = self.manager.configure(
            self.project,
            ["qwen2.5-coder:7b"],
            allow_existing=True,
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            payload["provider"]["anthropic"]["options"]["baseURL"],
            "https://example.test",
        )
        self.assertIn("ollama", payload["provider"])
        self.assertEqual(payload["model"], "ollama/qwen2.5-coder:7b")
        self.assertTrue(Path(result["backup"]).exists())

    def test_invalid_existing_provider_is_not_overwritten(self) -> None:
        path = self.project_dir / "opencode.json"
        path.write_text('{"provider": "invalid"}', encoding="utf-8")
        with self.assertRaises(ProjectError):
            self.manager.configure(
                self.project, ["qwen2.5-coder:7b"], allow_existing=True
            )
        self.assertEqual(
            json.loads(path.read_text(encoding="utf-8")), {"provider": "invalid"}
        )

    def test_missing_directory_is_rejected(self) -> None:
        project = Project(name="Missing", path=str(self.root / "nope"), model="x")
        with self.assertRaises(ProjectError):
            self.manager.configure(project, ["x"])

    def test_open_vscode_spawns_detached_process(self) -> None:
        with patch("brightnova.project_manager.shutil.which", return_value="/usr/bin/code"), patch(
            "brightnova.project_manager.subprocess.Popen"
        ) as popen:
            result = self.manager.open_vscode(self.project)
        self.assertTrue(result.ok)
        popen.assert_called_once()
        self.assertEqual(popen.call_args.args[0][0], "/usr/bin/code")


if __name__ == "__main__":
    unittest.main()
