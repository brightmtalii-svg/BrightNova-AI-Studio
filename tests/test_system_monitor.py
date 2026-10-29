from __future__ import annotations

import unittest

from brightnova.system_monitor import SystemMonitor, format_bytes


class SystemMonitorTests(unittest.TestCase):
    def test_sample_has_real_resource_values(self) -> None:
        sample = SystemMonitor().sample()
        self.assertGreater(sample.memory_total, 0)
        self.assertGreater(sample.memory_available, 0)
        self.assertGreater(sample.disk_total, 0)
        self.assertGreaterEqual(sample.cpu_percent, 0.0)
        self.assertLessEqual(sample.cpu_percent, 100.0)
        self.assertGreaterEqual(sample.memory_percent, 0.0)
        self.assertLessEqual(sample.memory_percent, 100.0)
        self.assertGreaterEqual(sample.disk_percent, 0.0)
        self.assertLessEqual(sample.disk_percent, 100.0)
        self.assertGreaterEqual(sample.ollama_rss, 0)
        self.assertTrue(sample.disk_path)

    def test_format_bytes(self) -> None:
        self.assertEqual(format_bytes(2048), "2.0 KB")


if __name__ == "__main__":
    unittest.main()
