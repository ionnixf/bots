import tempfile
import unittest
import wave
from pathlib import Path

from media import (
    BLACK_VIDEO_NAME,
    SILENCE_NAME,
    build_fake_media_args,
    ensure_black_video,
    ensure_silence_wav,
)


class FakeMediaTests(unittest.TestCase):
    def test_silence_wav_is_valid_pcm(self):
        with tempfile.TemporaryDirectory() as directory:
            path = ensure_silence_wav(Path(directory) / SILENCE_NAME)
            with wave.open(str(path), "rb") as stream:
                self.assertEqual(stream.getnchannels(), 1)
                self.assertEqual(stream.getsampwidth(), 2)
                self.assertEqual(stream.getframerate(), 48_000)
                self.assertEqual(stream.getnframes(), 48_000)

    def test_black_video_is_one_y4m_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            path = ensure_black_video(Path(directory) / BLACK_VIDEO_NAME)
            data = path.read_bytes()
            self.assertTrue(data.startswith(b"YUV4MPEG2 W640 H480 F30:1"))
            self.assertIn(b"\nFRAME\n", data)
            expected = 640 * 480 + 2 * (640 * 480 // 4)
            self.assertEqual(len(data.split(b"FRAME\n", 1)[1]), expected)

    def test_generation_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            first = ensure_silence_wav(base / SILENCE_NAME)
            modified = first.stat().st_mtime_ns
            second = ensure_silence_wav(base / SILENCE_NAME)
            self.assertEqual(first, second)
            self.assertEqual(second.stat().st_mtime_ns, modified)

    def test_chromium_flags_point_at_generated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            args = build_fake_media_args(Path(directory))
            joined = " ".join(args)
            self.assertIn("--use-fake-ui-for-media-stream", args)
            self.assertIn("--use-fake-device-for-media-stream", args)
            self.assertIn(SILENCE_NAME, joined)
            self.assertIn(BLACK_VIDEO_NAME, joined)
            self.assertTrue((Path(directory) / SILENCE_NAME).is_file())
            self.assertTrue((Path(directory) / BLACK_VIDEO_NAME).is_file())


if __name__ == "__main__":
    unittest.main()
