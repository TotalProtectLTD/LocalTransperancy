#!/usr/bin/env python3
# metadata_extract.py

import sys
import os
import json
import subprocess

try:
    import ffmpeg  # type: ignore
except Exception:  # Fallback to ffprobe if python-ffmpeg isn't available
    ffmpeg = None  # type: ignore


def _probe_with_ffmpeg_py(video_path: str) -> dict:
    info = ffmpeg.probe(video_path)
    return info


def _probe_with_ffprobe_cli(video_path: str) -> dict:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        video_path,
    ]
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout or "{}")
    except FileNotFoundError:
        print("ffprobe not found in PATH. Please install FFmpeg.", file=sys.stderr)
        return {}
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.strip() if e.stderr else str(e)
        print(f"ffprobe error for {video_path}: {stderr}", file=sys.stderr)
        return {}


def extract_metadata(video_path: str) -> dict:
    """Gather metadata using python-ffmpeg if available, otherwise ffprobe CLI."""
    if ffmpeg is not None:
        try:
            return _probe_with_ffmpeg_py(video_path)
        except Exception as e:
            print(f"python-ffmpeg failed, falling back to ffprobe: {e}", file=sys.stderr)
    return _probe_with_ffprobe_cli(video_path)


def save_metadata(metadata: dict, out_txt: str):
    """Save metadata dict as JSON text (pretty) into out_txt."""
    with open(out_txt, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)


def main():
    if len(sys.argv) != 2:
        print("Usage: python metadata_extract.py <video.mp4>")
        sys.exit(1)
    video_path = sys.argv[1]
    if not os.path.isfile(video_path):
        print(f"File does not exist: {video_path}")
        sys.exit(1)
    base, ext = os.path.splitext(video_path)
    out_txt = base + "_metadata.txt"
    metadata = extract_metadata(video_path)
    save_metadata(metadata, out_txt)
    print(f"Metadata extracted to {out_txt}")


if __name__ == "__main__":
    main()


