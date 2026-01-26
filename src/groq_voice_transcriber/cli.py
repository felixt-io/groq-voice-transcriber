import argparse
import os
from pathlib import Path

from groq_voice_transcriber.audio import (
    SUPPORTED_EXTENSIONS,
    CompressionLimitError,
    chunk_audio_to_mp3,
    compress_to_fit,
)
from groq_voice_transcriber.groq import extract_text, transcribe_file
from groq_voice_transcriber.output import (
    merge_text_chunks,
    output_paths,
    write_text,
)


def parse_extensions(value: str) -> set[str]:
    items = [item.strip().lower() for item in value.split(",") if item.strip()]
    extensions = set()
    for item in items:
        extensions.add(item if item.startswith(".") else f".{item}")
    return extensions


def collect_files(path: str, recursive: bool, extensions: set[str]) -> list[str]:
    path_obj = Path(path)
    if path_obj.is_file():
        return [str(path_obj)]

    if not path_obj.is_dir():
        raise FileNotFoundError(f"Path not found: {path}")

    files = []
    if recursive:
        for root, _, filenames in os.walk(path_obj):
            for name in filenames:
                file_path = Path(root) / name
                if file_path.suffix.lower() in extensions:
                    files.append(str(file_path))
    else:
        for entry in path_obj.iterdir():
            if entry.is_file() and entry.suffix.lower() in extensions:
                files.append(str(entry))

    return sorted(files)


def cleanup_temp_file(file_path: str) -> None:
    try:
        os.remove(file_path)
    except FileNotFoundError:
        return
    parent_dir = os.path.dirname(file_path)
    try:
        os.rmdir(parent_dir)
    except OSError:
        return


def cleanup_temp_dir(path: str) -> None:
    if not path or not os.path.isdir(path):
        return
    for name in os.listdir(path):
        try:
            os.remove(os.path.join(path, name))
        except FileNotFoundError:
            continue
    try:
        os.rmdir(path)
    except OSError:
        return


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Transcribe audio using Groq with automatic compression.",
    )
    parser.add_argument("path", help="Audio file or folder to transcribe")
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively scan folders for audio files",
    )
    parser.add_argument(
        "--model",
        default="whisper-large-v3",
        help="Model ID to use (default: whisper-large-v3)",
    )
    parser.add_argument(
        "--lang",
        default="auto",
        help="Language code (default: auto)",
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="Optional prompt to guide spelling or context",
    )
    parser.add_argument(
        "--max-mb",
        type=float,
        default=24,
        help="Maximum upload size in MB (default: 24)",
    )
    parser.add_argument(
        "--min-compress-kbps",
        type=int,
        default=32,
        help="Minimum bitrate for single-file compression (default: 32)",
    )
    parser.add_argument(
        "--chunk-bitrate-kbps",
        type=int,
        default=64,
        help="Bitrate for chunked audio (default: 64)",
    )
    parser.add_argument(
        "--chunk-overlap-seconds",
        type=float,
        default=0.7,
        help="Overlap between chunks in seconds (default: 0.7)",
    )
    parser.add_argument(
        "--keep-chunks",
        action="store_true",
        help="Keep chunked audio files when chunking is used",
    )
    parser.add_argument(
        "--outdir",
        default="out",
        help="Output directory for transcripts (default: out)",
    )
    parser.add_argument(
        "--keep-compressed",
        action="store_true",
        help="Keep compressed audio file if compression is used",
    )
    parser.add_argument(
        "--extensions",
        default=None,
        help="Comma-separated extensions to include (overrides defaults)",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.max_mb <= 0:
        raise SystemExit("--max-mb must be greater than zero")
    if args.min_compress_kbps <= 0:
        raise SystemExit("--min-compress-kbps must be greater than zero")
    if args.chunk_bitrate_kbps <= 0:
        raise SystemExit("--chunk-bitrate-kbps must be greater than zero")
    if args.chunk_overlap_seconds < 0:
        raise SystemExit("--chunk-overlap-seconds must be non-negative")

    extensions = (
        parse_extensions(args.extensions) if args.extensions else set(SUPPORTED_EXTENSIONS)
    )

    files = collect_files(args.path, args.recursive, extensions)
    if not files:
        raise SystemExit("No audio files found to transcribe.")

    root_dir = args.path if Path(args.path).is_dir() else None

    for file_path in files:
        print(f"Processing: {file_path}")
        try:
            compressed = compress_to_fit(
                file_path,
                max_mb=args.max_mb,
                keep_compressed=args.keep_compressed,
                min_kbps=args.min_compress_kbps,
            )
        except CompressionLimitError:
            compressed = None

        if compressed is not None:
            try:
                transcription = transcribe_file(
                    compressed.path,
                    model=args.model,
                    language=args.lang,
                    prompt=args.prompt,
                )
                text = extract_text(transcription)
                text_path = output_paths(
                    file_path,
                    out_dir=args.outdir,
                    root_dir=root_dir,
                )
                write_text(text_path, text)
                print(f"Saved: {text_path}")
            finally:
                if compressed.is_temporary:
                    cleanup_temp_file(compressed.path)
        else:
            print("File too large for single-file compression, chunking...")
            chunked = chunk_audio_to_mp3(
                file_path,
                max_mb=args.max_mb,
                bitrate_kbps=args.chunk_bitrate_kbps,
                overlap_seconds=args.chunk_overlap_seconds,
                keep_chunks=args.keep_chunks,
            )
            try:
                chunk_transcripts = []
                for chunk_path in chunked.paths:
                    transcript = transcribe_file(
                        chunk_path,
                        model=args.model,
                        language=args.lang,
                        prompt=args.prompt,
                    )
                    chunk_transcripts.append(transcript)

                text_path = output_paths(
                    file_path,
                    out_dir=args.outdir,
                    root_dir=root_dir,
                )

                texts = [extract_text(chunk) for chunk in chunk_transcripts]
                write_text(text_path, merge_text_chunks(texts))

                print(f"Saved: {text_path}")
            finally:
                if chunked.is_temporary:
                    cleanup_temp_dir(chunked.temp_dir)


if __name__ == "__main__":
    main()
