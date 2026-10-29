from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from brightnova.config import ConfigStore, Project, Settings


class ConfigStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_creates_default_settings(self) -> None:
        store = ConfigStore(self.directory)
        self.assertTrue(store.path.exists())
        self.assertEqual(store.settings.selected_model, "qwen2.5-coder:7b")
        self.assertIn("coding mentor", store.settings.system_prompt)
        self.assertEqual(store.last_error, "")

    def test_project_round_trip(self) -> None:
        store = ConfigStore(self.directory)
        project = Project(
            name="BrightLend",
            path="/tmp/brightlend",
            model="qwen2.5-coder:7b",
        )
        saved = store.add_project(project)
        self.assertEqual(store.settings.last_project_id, saved.id)
        reloaded = ConfigStore(self.directory)
        self.assertEqual(len(reloaded.settings.projects), 1)
        self.assertEqual(reloaded.settings.projects[0].name, "BrightLend")
        self.assertEqual(reloaded.last_project().id, saved.id)

        saved.model = "qwen2.5-coder:3b"
        reloaded.update_project(saved)
        self.assertEqual(
            ConfigStore(self.directory).settings.projects[0].model,
            "qwen2.5-coder:3b",
        )

        reloaded.remove_project(saved.id)
        self.assertEqual(ConfigStore(self.directory).settings.projects, [])

    def test_duplicate_project_updates_existing(self) -> None:
        store = ConfigStore(self.directory)
        first = store.add_project(
            Project(name="One", path="/tmp/one", model="qwen2.5-coder:7b")
        )
        second = store.add_project(
            Project(name="One updated", path="/tmp/one", model="qwen2.5-coder:3b")
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(store.settings.projects), 1)
        self.assertEqual(store.settings.projects[0].model, "qwen2.5-coder:3b")

    def test_corrupt_settings_are_preserved(self) -> None:
        directory = self.directory
        path = directory / "settings.json"
        path.write_text("{not valid json", encoding="utf-8")
        store = ConfigStore(directory)
        self.assertTrue(store.last_error)
        self.assertEqual(store.settings, Settings())
        backups = list(directory.glob("settings.corrupt-*.json"))
        self.assertEqual(len(backups), 1)

    def test_interval_is_clamped(self) -> None:
        directory = self.directory
        path = directory / "settings.json"
        path.write_text(
            json.dumps({"refresh_interval_seconds": 0.1}), encoding="utf-8"
        )
        store = ConfigStore(directory)
        self.assertEqual(store.settings.refresh_interval_seconds, 1.0)


if __name__ == "__main__":
    unittest.main()
