#!/usr/bin/env python3
"""Synthetic route controls; live media acceptance is performed separately."""

import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "download_video", Path(__file__).parents[1] / "scripts/download_video.py"
)
downloader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(downloader)


def result(code=0, text=""):
    return subprocess.CompletedProcess([], code, text, "")


TOKEN = (
    "WARNING: mweb client https formats require a GVS PO Token which was not provided.\n"
    "ERROR: Requested format is not available"
)

# Shape emitted by yt-dlp's skipped-format diagnostic, with synthetic identity.
SKIPPED_TOKEN_WARNING = (
    "WARNING: [youtube] VIDEO_ID: mweb client https formats require a GVS "
    "PO Token which was not provided. They will be skipped as they may "
    "yield HTTP Error 403."
)


class DownloadRoutes(unittest.TestCase):
    def invoke(self, outcomes=None, **kwargs):
        with tempfile.TemporaryDirectory() as root, \
                patch.object(downloader.subprocess, "run", return_value=result()) as base, \
                patch.object(downloader, "run_yt_dlp", side_effect=outcomes or [result()]) as run, \
                patch.object(downloader, "ensure_po_token_provider", return_value="bgutil") as provider, \
                patch.object(downloader, "print_video_info", return_value=0) as info, \
                patch.object(downloader, "get_proxy_settings", return_value=(None, None)), \
                redirect_stdout(io.StringIO()):
            code = downloader.download_video("https://youtu.be/VIDEO_ID", output_dir=root, **kwargs)
            return code, [call.args[0] for call in run.call_args_list], provider.call_count, info.call_args

    def test_default_preserves_native_clients_without_provider(self):
        code, calls, providers, _ = self.invoke()
        self.assertEqual((code, len(calls), providers), (0, 1, 0))
        self.assertNotIn("--extractor-args", calls[0])
        self.assertNotIn("--cookies-from-browser", calls[0])
        self.assertIn("--no-playlist", calls[0])

    def test_opt_in_does_not_start_provider_for_success(self):
        code, calls, providers, _ = self.invoke(auto_po_token=True)
        self.assertEqual((code, len(calls), providers), (0, 1, 0))
        self.assertNotIn("--extractor-args", calls[0])

    def test_explicit_token_failure_uses_authorized_provider_after_first_attempt(self):
        code, calls, providers, _ = self.invoke([result(1, TOKEN), result()], auto_po_token=True)
        self.assertEqual((code, len(calls), providers), (0, 2, 1))
        self.assertNotIn("--extractor-args", calls[0])
        self.assertIn("youtube:player_client=mweb", calls[1])

    def test_token_requirement_without_setup_authorization_returns_failure(self):
        code, calls, providers, _ = self.invoke([result(1, TOKEN)])
        self.assertEqual((code, len(calls), providers), (1, 1, 0))

    def test_authorized_provider_failure_reaches_wpc_without_service_restart(self):
        with patch.object(downloader, "ensure_wpc_provider", return_value=True) as wpc, \
                patch.object(downloader, "restart_po_token_provider") as restart, \
                patch.object(downloader, "find_chrome_path", return_value="/synthetic/chrome"):
            code, calls, providers, _ = self.invoke(
                [result(1, TOKEN), result(1, "ERROR: [pot:bgutil:http] provider connection failed"), result()],
                auto_po_token=True)
        self.assertEqual((code, len(calls), providers, wpc.call_count), (0, 3, 1, 1))
        restart.assert_not_called()
        self.assertIn("youtubepot-wpc:browser_path=/synthetic/chrome", calls[2])

    def test_provider_setup_failure_preserves_original_exit(self):
        with tempfile.TemporaryDirectory() as root, \
                patch.object(downloader.subprocess, "run", return_value=result()), \
                patch.object(downloader, "run_yt_dlp", return_value=result(7, TOKEN)) as run, \
                patch.object(downloader, "ensure_po_token_provider", return_value=None), \
                redirect_stdout(io.StringIO()):
            code = downloader.download_video("URL", output_dir=root, auto_po_token=True)
        self.assertEqual((code, run.call_count), (7, 1))

    def test_non_token_failures_do_not_install_or_retry_formats(self):
        for diagnostic in (
            "ERROR: The read operation timed out",
            TOKEN + "\nERROR: Connection timed out",
            "ERROR: Requested format is not available",
            "WARNING: Only images are available\nERROR: Requested format is not available",
            "ERROR: nsig extraction failed",
            "ERROR: Sign in to confirm you're not a bot",
            "WARNING: PO Token missing\nERROR: ffmpeg failed",
            SKIPPED_TOKEN_WARNING + "\nERROR: Postprocessing: ffmpeg not found. Please install or provide the path using --ffmpeg-location",
            SKIPPED_TOKEN_WARNING + "\nERROR: unable to open for writing: Permission denied",
            SKIPPED_TOKEN_WARNING + "\nERROR: HTTP Error 403\nERROR: Postprocessing: ffmpeg failed",
            "ERROR: transport failed",
        ):
            with self.subTest(diagnostic=diagnostic):
                code, calls, providers, _ = self.invoke([result(1, diagnostic)], auto_po_token=True)
                self.assertEqual((code, len(calls), providers), (1, 1, 0))

    def test_real_warning_shape_plus_real_format_failure_can_recover(self):
        code, calls, providers, _ = self.invoke(
            [result(1, SKIPPED_TOKEN_WARNING + "\nERROR: Requested format is not available"), result()],
            auto_po_token=True)
        self.assertEqual((code, len(calls), providers), (0, 2, 1))

    def test_403_only_uses_bounded_progressive_retry(self):
        code, calls, providers, _ = self.invoke([result(1, "HTTP Error 403"), result()], auto_po_token=True)
        self.assertEqual((code, len(calls), providers), (0, 2, 0))
        self.assertIn("protocol!*=m3u8", calls[1][calls[1].index("-f") + 1])

    def test_metadata_and_format_listing_do_not_start_provider_or_force_android(self):
        code, calls, providers, info = self.invoke(info_only=True, auto_po_token=True)
        self.assertEqual((code, len(calls), providers), (0, 0, 0))
        self.assertNotIn("--extractor-args", info.args[0])
        code, calls, providers, _ = self.invoke(list_formats=True, auto_po_token=True)
        self.assertEqual((code, len(calls), providers), (0, 1, 0))
        self.assertNotIn("--extractor-args", calls[0])

    def test_browser_and_file_cookies_survive_token_retry(self):
        for option, flag in (("cookies_from_browser", "--cookies-from-browser"), ("cookies_file", "--cookies")):
            with self.subTest(option=option):
                code, calls, providers, _ = self.invoke(
                    [result(1, TOKEN), result()], auto_po_token=True, **{option: "synthetic"})
                self.assertEqual((code, providers), (0, 1))
                self.assertIn(flag, calls[1])
                self.assertIn("youtube:player_client=web_safari", calls[1])

    def test_incompatible_cookie_client_fails_before_download(self):
        for client in ("android", "android_vr", "ios", "tv_simply"):
            code, calls, providers, _ = self.invoke(cookies_file="synthetic.txt", player_client=client)
            self.assertEqual((code, len(calls), providers), (2, 0, 0))

    def test_explicit_non_web_client_does_not_install_web_token_provider(self):
        code, calls, providers, _ = self.invoke([result(1, TOKEN)], auto_po_token=True, player_client="android")
        self.assertEqual((code, len(calls), providers), (2, 1, 0))

    def test_custom_formats_audio_playlist_subtitles_and_runtime_preserved(self):
        code, calls, providers, _ = self.invoke(
            format_spec="bestaudio", audio_only=True, subtitles=True,
            subtitle_lang="fr", allow_playlist=True, js_runtimes="node")
        self.assertEqual(code, 0)
        for expected in ("-x", "mp3", "-f", "bestaudio", "--write-subs", "--write-auto-subs", "fr", "node"):
            self.assertIn(expected, calls[0])
        self.assertNotIn("--no-playlist", calls[0])

    def test_legacy_android_is_explicit_and_cookies_take_precedence(self):
        _, calls, _, _ = self.invoke(use_android_client=True)
        self.assertIn("youtube:player_client=android", calls[0])
        _, calls, _, _ = self.invoke(use_android_client=True, cookies_file="synthetic.txt")
        self.assertNotIn("youtube:player_client=android", calls[0])

    def test_client_change_retains_token_and_provider_configuration(self):
        cmd = ["yt-dlp", "--extractor-args", "youtube:player_client=mweb;po_token=mweb.gvs+FAKE",
               "--extractor-args", "youtubepot-wpc:browser_path=/synthetic/chrome", "URL"]
        actual = downloader.with_player_client(cmd, "web_safari")
        self.assertIn("youtube:po_token=mweb.gvs+FAKE;player_client=web_safari", actual)
        self.assertIn("youtubepot-wpc:browser_path=/synthetic/chrome", actual)
        self.assertEqual(sum(value.startswith("youtube:") for value in actual), 1)

    def test_capture_diagnostics_without_cookies(self):
        with redirect_stdout(io.StringIO()):
            actual = downloader.run_yt_dlp([sys.executable, "-c", "import sys; print('ERROR: missing PO Token', file=sys.stderr); sys.exit(1)"])
        self.assertEqual(actual.returncode, 1)
        self.assertTrue(downloader.has_pot_error(actual))

    def test_success_warning_and_empty_diagnostics_are_not_failures(self):
        self.assertFalse(downloader.has_pot_error(result(0, TOKEN)))
        self.assertFalse(downloader.has_pot_error(subprocess.CompletedProcess([], 1)))

    def test_cli_default_and_explicit_authorization(self):
        for flags, expected in (([], False), (["--auto-po-token"], True), (["--no-auto-po-token"], False)):
            with patch.object(sys, "argv", ["download_video.py", "URL", *flags]), \
                    patch.object(downloader, "download_video", return_value=0) as download:
                with self.assertRaises(SystemExit) as exited:
                    downloader.main()
                self.assertEqual(exited.exception.code, 0)
                self.assertEqual(download.call_args.kwargs["auto_po_token"], expected)
                self.assertFalse(download.call_args.kwargs["use_android_client"])


if __name__ == "__main__":
    unittest.main()
