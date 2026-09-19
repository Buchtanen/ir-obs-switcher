"""Unit tests for headroom.py (stdlib unittest)."""

from __future__ import annotations

import unittest

from headroom import classify_sample, percentile, summarize_samples


class TestPercentile(unittest.TestCase):
    def test_empty_returns_none(self) -> None:
        self.assertIsNone(percentile([], 50))

    def test_single_value(self) -> None:
        self.assertEqual(percentile([42.0], 0), 42.0)
        self.assertEqual(percentile([42.0], 50), 42.0)
        self.assertEqual(percentile([42.0], 100), 42.0)

    def test_unsorted_median(self) -> None:
        self.assertEqual(percentile([30.0, 10.0, 20.0], 50), 20.0)

    def test_endpoints(self) -> None:
        xs = [1.0, 2.0, 3.0, 4.0]
        self.assertEqual(percentile(xs, 0), 1.0)
        self.assertEqual(percentile(xs, 100), 4.0)

    def test_p95_interpolation(self) -> None:
        xs = [float(i) for i in range(1, 101)]  # 1..100
        # rank = 99 * 0.95 = 94.05 → between index 94 (95) and 95 (96)
        self.assertAlmostEqual(percentile(xs, 95), 95.05, places=6)

    def test_p_out_of_range_raises(self) -> None:
        with self.assertRaises(ValueError):
            percentile([1.0], -1)
        with self.assertRaises(ValueError):
            percentile([1.0], 101)


class TestClassifySample(unittest.TestCase):
    def test_unknown_when_both_none(self) -> None:
        self.assertEqual(classify_sample(None, None), "unknown")

    def test_fps_low_below_92pct_target(self) -> None:
        # 90 * 0.92 = 82.8
        self.assertEqual(classify_sample(82.0, 50.0), "fps_low")
        self.assertEqual(classify_sample(82.0, 99.0), "fps_low")  # fps_low wins

    def test_fps_not_low_at_boundary(self) -> None:
        self.assertNotEqual(classify_sample(82.8, 50.0), "fps_low")

    def test_gpu_bound_high_load_soft_fps(self) -> None:
        self.assertEqual(classify_sample(85.0, 95.0), "gpu_bound")
        self.assertEqual(classify_sample(89.9, 99.0), "gpu_bound")

    def test_gpu_bound_when_fps_missing(self) -> None:
        self.assertEqual(classify_sample(None, 97.0), "gpu_bound")

    def test_not_gpu_bound_at_exact_target_fps(self) -> None:
        # fps == target → not (fps < target), so not gpu_bound
        self.assertEqual(classify_sample(90.0, 97.0), "ok")

    def test_headroom(self) -> None:
        # 90 * 0.98 = 88.2
        self.assertEqual(classify_sample(90.0, 70.0), "headroom")
        self.assertEqual(classify_sample(88.2, 79.9), "headroom")

    def test_ok_when_gpu_high_but_fps_on_target(self) -> None:
        self.assertEqual(classify_sample(90.0, 90.0), "ok")

    def test_ok_when_fps_ok_gpu_missing(self) -> None:
        self.assertEqual(classify_sample(90.0, None), "ok")

    def test_custom_target_hz(self) -> None:
        self.assertEqual(
            classify_sample(100.0, 50.0, target_hz=120.0),
            "fps_low",
        )  # 120 * 0.92 = 110.4
        self.assertEqual(
            classify_sample(120.0, 50.0, target_hz=120.0),
            "headroom",
        )


class TestSummarizeSamples(unittest.TestCase):
    def test_empty(self) -> None:
        out = summarize_samples([])
        self.assertEqual(out["n"], 0)
        self.assertEqual(out["class_counts"], {})
        self.assertEqual(out["low_fps_notes"], [])
        self.assertNotIn("fps", out)

    def test_fixture_with_field_note_drop(self) -> None:
        samples = [
            {
                "fps": 91.0,
                "frametime_ms": 11.0,
                "gpu_load": 72.0,
                "gpu_temp": 65.0,
                "cpu_load": 40.0,
                "note": "solo",
            },
            {
                "fps": 90.5,
                "frametime_ms": 11.1,
                "gpu_load": 74.0,
                "gpu_temp": 66.0,
                "cpu_load": 42.0,
                "note": "solo",
            },
            {
                "fps": 78.0,
                "frametime_ms": 12.8,
                "gpu_load": 97.0,
                "gpu_temp": 72.0,
                "cpu_load": 55.0,
                "note": "field",
            },
            {
                "fps": 76.5,
                "frametime_ms": 13.1,
                "gpu_load": 98.0,
                "gpu_temp": 73.0,
                "cpu_load": 58.0,
                "note": "field",
            },
            {
                "fps": 88.0,
                "frametime_ms": 11.4,
                "gpu_load": 96.0,
                "gpu_temp": 70.0,
                "cpu_load": 50.0,
                "note": "field",
            },
            {
                "fps": None,
                "gpu_load": None,
                "note": "pits",
            },
        ]
        out = summarize_samples(samples, target_hz=90.0)

        self.assertEqual(out["n"], 6)
        self.assertIn("fps", out)
        self.assertIn("p05", out["fps"])
        self.assertIn("p50", out["fps"])
        self.assertIn("p95", out["fps"])
        self.assertIn("min", out["fps"])
        self.assertIn("max", out["fps"])
        self.assertAlmostEqual(out["fps"]["min"], 76.5)
        self.assertAlmostEqual(out["fps"]["max"], 91.0)

        self.assertIn("frametime_ms", out)
        self.assertIn("p50", out["frametime_ms"])
        self.assertIn("p95", out["frametime_ms"])
        self.assertIn("max", out["frametime_ms"])

        self.assertIn("gpu_load", out)
        self.assertIn("gpu_temp", out)
        self.assertIn("cpu_load", out)
        self.assertIn("p50", out["cpu_load"])
        self.assertIn("p95", out["cpu_load"])
        self.assertNotIn("max", out["cpu_load"])

        counts = out["class_counts"]
        # solo ×2 → headroom; field 78/76.5 → fps_low; field 88+96 → gpu_bound; pits → unknown
        self.assertEqual(counts.get("headroom"), 2)
        self.assertEqual(counts.get("fps_low"), 2)
        self.assertEqual(counts.get("gpu_bound"), 1)
        self.assertEqual(counts.get("unknown"), 1)

        self.assertIn("field", out["low_fps_notes"])
        self.assertEqual(out["low_fps_notes"].count("field"), 1)  # distinct
        self.assertNotIn("solo", out["low_fps_notes"])
        self.assertNotIn("pits", out["low_fps_notes"])

        hint = out["bottleneck_hint"]
        self.assertIsInstance(hint, str)
        self.assertTrue(len(hint) > 0)
        self.assertTrue(
            "GPU" in hint or "FPS" in hint or "field" in hint.lower(),
            msg=f"unexpected hint: {hint!r}",
        )

    def test_low_fps_notes_capped_at_10(self) -> None:
        samples = [
            {"fps": 50.0, "gpu_load": 50.0, "note": f"tag{i}"} for i in range(15)
        ]
        out = summarize_samples(samples)
        self.assertEqual(len(out["low_fps_notes"]), 10)
        self.assertEqual(out["low_fps_notes"][0], "tag0")
        self.assertEqual(out["low_fps_notes"][-1], "tag9")

    def test_omits_missing_metric_blocks(self) -> None:
        out = summarize_samples([{"fps": 90.0, "note": "solo"}])
        self.assertIn("fps", out)
        self.assertNotIn("frametime_ms", out)
        self.assertNotIn("gpu_load", out)
        self.assertNotIn("gpu_temp", out)
        self.assertNotIn("cpu_load", out)


if __name__ == "__main__":
    unittest.main()
