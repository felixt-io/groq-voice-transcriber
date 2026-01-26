import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple


SUPPORTED_EXTENSIONS = {
    ".flac",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".m4a",
    ".ogg",
    ".wav",
    ".webm",
}


@dataclass
class CompressionResult:
    path: str
    used_compression: bool
    is_temporary: bool


@dataclass
class ChunkResult:
    paths: List[str]
    starts: List[float]
    temp_dir: str
    is_temporary: bool


class CompressionLimitError(RuntimeError):
    pass


def file_size_mb(path: str) -> float:
    return os.path.getsize(path) / (1024 * 1024)


def ensure_ffmpeg_available() -> None:
    try:
        subprocess.run(["ffmpeg", "-version"], check=False, capture_output=True, text=True)
        subprocess.run(["ffprobe", "-version"], check=False, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg/ffprobe not found. Install with: brew install ffmpeg") from exc


def probe_duration_seconds(path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    duration_str = result.stdout.strip()
    if not duration_str:
        raise RuntimeError(f"Could not read duration for: {path}")
    try:
        duration = float(duration_str)
    except ValueError as exc:
        raise RuntimeError(f"Invalid duration value from ffprobe: {duration_str}") from exc
    if duration <= 0:
        raise RuntimeError(f"Non-positive duration reported for: {path}")
    return duration


def compute_target_bitrate_kbps(duration_seconds: float, max_bytes: int) -> int:
    bits_per_second = (max_bytes * 8) / duration_seconds
    kbps = int(bits_per_second / 1000)
    kbps = int(kbps * 0.9)
    return max(kbps, 24)


def generate_bitrate_steps(start_kbps: int, min_kbps: int = 24, step_kbps: int = 8) -> list[int]:
    steps = []
    current = max(start_kbps, min_kbps)
    while current >= min_kbps:
        steps.append(current)
        current -= step_kbps
    return steps


def compress_to_fit(
    input_path: str,
    max_mb: float,
    keep_compressed: bool = False,
    min_kbps: int = 32,
) -> CompressionResult:
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"File not found: {input_path}")

    size_mb = file_size_mb(input_path)
    if size_mb <= max_mb:
        return CompressionResult(path=input_path, used_compression=False, is_temporary=False)

    ensure_ffmpeg_available()

    max_bytes = int(max_mb * 1024 * 1024)
    duration_seconds = probe_duration_seconds(input_path)
    target_kbps = compute_target_bitrate_kbps(duration_seconds, max_bytes)

    if keep_compressed:
        output_path = str(Path(input_path).with_suffix("")) + "_compressed.mp3"
    else:
        temp_dir = tempfile.mkdtemp(prefix="groq_transcribe_")
        output_path = os.path.join(temp_dir, "compressed.mp3")

    for kbps in generate_bitrate_steps(target_kbps, min_kbps=min_kbps):
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                input_path,
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-map",
                "0:a",
                "-c:a",
                "libmp3lame",
                "-b:a",
                f"{kbps}k",
                output_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        if os.path.isfile(output_path) and os.path.getsize(output_path) <= max_bytes:
            return CompressionResult(
                path=output_path,
                used_compression=True,
                is_temporary=not keep_compressed,
            )

    raise CompressionLimitError(
        "Unable to compress under size limit without dropping below minimum bitrate."
    )


def compute_chunk_duration_seconds(
    max_mb: float,
    bitrate_kbps: int,
    safety_margin: float = 0.85,
) -> float:
    max_bytes = max_mb * 1024 * 1024
    bits_per_second = bitrate_kbps * 1000
    duration = (max_bytes * 8) / bits_per_second
    return duration * safety_margin


def chunk_audio_to_mp3(
    input_path: str,
    max_mb: float,
    bitrate_kbps: int,
    overlap_seconds: float,
    keep_chunks: bool = False,
) -> ChunkResult:
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"File not found: {input_path}")

    ensure_ffmpeg_available()

    duration_seconds = probe_duration_seconds(input_path)
    chunk_duration = compute_chunk_duration_seconds(max_mb, bitrate_kbps)
    if chunk_duration <= 0:
        raise RuntimeError("Chunk duration computed as non-positive.")
    if overlap_seconds < 0:
        raise RuntimeError("Overlap seconds must be non-negative.")
    if overlap_seconds >= chunk_duration:
        raise RuntimeError("Overlap seconds must be smaller than chunk duration.")

    if keep_chunks:
        base_dir = str(Path(input_path).with_suffix("")) + "_chunks"
        os.makedirs(base_dir, exist_ok=True)
        temp_dir = base_dir
        is_temporary = False
    else:
        temp_dir = tempfile.mkdtemp(prefix="groq_chunks_")
        is_temporary = True

    paths: List[str] = []
    starts: List[float] = []

    start = 0.0
    index = 1
    while start < duration_seconds:
        remaining = duration_seconds - start
        segment_duration = min(chunk_duration, remaining)
        if segment_duration <= 0:
            break

        output_path = os.path.join(temp_dir, f"chunk_{index:04d}.mp3")
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                input_path,
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-map",
                "0:a",
                "-c:a",
                "libmp3lame",
                "-b:a",
                f"{bitrate_kbps}k",
                "-ss",
                f"{start:.3f}",
                "-t",
                f"{segment_duration:.3f}",
                output_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        paths.append(output_path)
        starts.append(start)

        if remaining <= chunk_duration:
            break

        start = start + chunk_duration - overlap_seconds
        index += 1

    return ChunkResult(paths=paths, starts=starts, temp_dir=temp_dir, is_temporary=is_temporary)
