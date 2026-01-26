# Groq Voice Transcriber

Voice is still the most natural way people communicate. In real estate and construction, teams speak constantly: site inspections, defect walkthroughs, progress meetings, handovers. Those recordings are useful, but listening back takes time and makes follow-up harder.

Rather than investing in expensive transcription hardware, gadgets or costly monthly subscriptions, this tool leverages the free Groq API within a simple and privacy-first workflow. It takes any audio file, compresses it only if needed to fit the upload limit, and then sends it to Groq for transcription. The output is a clean and searchable text file that you can paste directly into any AI platform/app for summaries, key points, or to-do list.

## Why Groq and LPU

Groq runs inference on a Language Processing Unit (LPU), a processor built specifically for serving large language and speech models with predictable, low latency. GPUs are excellent general-purpose accelerators (and are essential for training), but serving inference at scale can be less predictable due to batching, scheduling, and memory pressure. LPUs are designed for consistent, high-throughput inference, which is exactly what fast transcription needs.

The result: near-instant transcriptions at high throughput. Groq also offers a free API tier, which makes this tool accessible without heavy infrastructure costs.

## What This Tool Does

- Accepts a single audio file or a folder of files
- Compresses/transcodes first, and only chunks when needed to stay within Groq upload limits
- Sends the audio to Groq Whisper for transcription
- Writes outputs to `out/` as plain text transcripts

## Quickstart

### 1) Install system dependency

macOS (Homebrew):

```bash
brew install ffmpeg
```

### 2) Install the package

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 3) Set your Groq API key

```bash
export GROQ_API_KEY="your_key_here"
```

### 4) Transcribe

```bash
groq-transcribe "/path/to/recording.m4a"
```

## Usage

```bash
groq-transcribe <file-or-folder> \
  [--recursive] \
  [--model whisper-large-v3|whisper-large-v3-turbo] \
  [--lang auto|en|zh|...] \
  [--prompt "context or spelling"] \
  [--max-mb 24] \
  [--min-compress-kbps 32] \
  [--chunk-bitrate-kbps 64] \
  [--chunk-overlap-seconds 0.7] \
  [--outdir out] \
  [--keep-compressed] \
  [--keep-chunks]
```

Examples:

```bash
groq-transcribe "./audio/site-walkthrough.mp3"
```

```bash
groq-transcribe "./audio" --recursive --lang zh
```

```bash
groq-transcribe "./meeting.m4a" --model whisper-large-v3-turbo
```

## How Compression and Chunking Work

Groq free-tier uploads are capped at 25 MB. This tool uses a default limit of 24 MB to stay safely under that cap.

If a file is larger than the limit, the tool first tries to fit it into a single MP3:

- mono audio
- 16 kHz sample rate
- bitrate computed from duration and size limit
- never below the minimum bitrate (default 32 kbps)

If the file still cannot fit without dropping below the minimum bitrate, chunking kicks in:

- the audio is split into overlapping segments
- each chunk is encoded consistently (mono, 16 kHz, MP3)
- transcripts are merged back into one continuous result

## Outputs

All results go to `out/`:

- `out/<name>.txt` for the transcript text

For folder runs, the output path mirrors the input folder structure to avoid name collisions.

## Privacy and Security

- API keys are read from `GROQ_API_KEY` only; never hardcode keys.
- The `.gitignore` ignores `.env`, `out/`, and common audio formats by default to prevent accidental leaks.
- Do not upload audio you are not allowed to share with a third-party API.

## Troubleshooting

- `ffmpeg/ffprobe not found`: install FFmpeg (`brew install ffmpeg`) and retry.
- `GROQ_API_KEY is not set`: export your key in the same shell session before running.
- `No audio files found`: check the path and extension filters, or use `--extensions`.
- File still too large: chunking should kick in automatically. If it fails, lower `--max-mb` or `--chunk-bitrate-kbps`.

## Notes

- Groq supports `whisper-large-v3` and `whisper-large-v3-turbo` for transcription.
- The free tier file upload limit is 25 MB. Large files are automatically chunked after compression attempts.

## License

MIT
