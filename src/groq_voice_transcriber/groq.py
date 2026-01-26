import os
from typing import Any, Optional

import requests


GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


class GroqTranscriptionError(RuntimeError):
    pass


def load_api_key() -> str:
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise GroqTranscriptionError("GROQ_API_KEY is not set in the environment.")
    return api_key


def transcribe_file(
    file_path: str,
    model: str,
    language: str,
    prompt: Optional[str],
) -> dict[str, Any]:
    api_key = load_api_key()

    data: dict[str, Any] = {"model": model}
    if language and language != "auto":
        data["language"] = language
    if prompt:
        data["prompt"] = prompt

    with open(file_path, "rb") as file_handle:
        files = {"file": (os.path.basename(file_path), file_handle, "application/octet-stream")}
        response = requests.post(
            GROQ_TRANSCRIBE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files=files,
            data=data,
            timeout=300,
        )

    if response.status_code >= 400:
        raise GroqTranscriptionError(
            f"Groq API error {response.status_code}: {response.text.strip()}"
        )

    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        return response.json()

    return {"text": response.text}


def extract_text(transcription: dict[str, Any]) -> str:
    return transcription.get("text", "")

