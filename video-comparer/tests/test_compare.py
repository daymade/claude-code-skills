#!/usr/bin/env python3
"""Regression tests for video-comparer's PSNR/SSIM extraction."""

import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compare.py"


def _load_compare_module():
    spec = importlib.util.spec_from_file_location("video_compare_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


compare = _load_compare_module()

# Captured from `ffmpeg -i a.mp4 -i b.mp4 -lavfi
# '[0:v][1:v]psnr=stats_file=-;[0:v][1:v]ssim=stats_file=-' -f null -`:
# the per-frame stats go to stdout, the summary lines go to stderr.
FFMPEG_STDOUT = (
    "n:1 mse_avg:17.29 mse_y:21.50 mse_u:9.31 mse_v:8.42 psnr_avg:35.75 "
    "psnr_y:34.81 psnr_u:38.44 psnr_v:38.88 \n"
    "n:1 Y:0.964497 U:0.983803 V:0.990012 All:0.971967 (15.523299)\n"
)
FFMPEG_STDERR = (
    "[Parsed_psnr_0 @ 0x6000005b4000] PSNR y:35.158749 u:38.356948 "
    "v:38.411640 average:35.992749 min:35.561153 max:36.508739\n"
    "[Parsed_ssim_1 @ 0x6000005b40b0] SSIM Y:0.967213 (14.842953) "
    "U:0.981823 (17.404867) V:0.988379 (19.347433) All:0.973176 (15.714687)\n"
)


class QualityMetricsParsingTests(unittest.TestCase):
    def test_metrics_are_read_from_ffmpeg_summary_on_stderr(self):
        completed = subprocess.CompletedProcess(
            args=["ffmpeg"], returncode=0, stdout=FFMPEG_STDOUT, stderr=FFMPEG_STDERR
        )
        with mock.patch.object(compare.subprocess, "run", return_value=completed):
            metrics = compare.calculate_quality_metrics(Path("a.mp4"), Path("b.mp4"))

        self.assertEqual(metrics, {"psnr": 35.99, "ssim": 0.9732})

    def test_identical_inputs_report_infinite_psnr(self):
        stderr = FFMPEG_STDERR.replace("average:35.992749", "average:inf").replace(
            "All:0.973176 (15.714687)", "All:1.000000 (inf)"
        )
        completed = subprocess.CompletedProcess(
            args=["ffmpeg"], returncode=0, stdout="", stderr=stderr
        )
        with mock.patch.object(compare.subprocess, "run", return_value=completed):
            metrics = compare.calculate_quality_metrics(Path("a.mp4"), Path("a.mp4"))

        self.assertEqual(metrics["psnr"], float("inf"))
        self.assertEqual(metrics["ssim"], 1.0)


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is not on PATH")
class QualityMetricsWithFfmpegTests(unittest.TestCase):
    def test_real_ffmpeg_run_yields_nonzero_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp) / "original.mp4"
            degraded = Path(tmp) / "degraded.mp4"
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                 "-i", "testsrc=size=160x120:rate=5:duration=1",
                 "-pix_fmt", "yuv420p", str(original)],
                check=True, capture_output=True, timeout=60,
            )
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", str(original),
                 "-vf", "boxblur=2:1", "-pix_fmt", "yuv420p", str(degraded)],
                check=True, capture_output=True, timeout=60,
            )

            metrics = compare.calculate_quality_metrics(original, degraded)

        self.assertGreater(metrics["psnr"], 0)
        self.assertGreater(metrics["ssim"], 0)
        self.assertLessEqual(metrics["ssim"], 1)


if __name__ == "__main__":
    unittest.main()
