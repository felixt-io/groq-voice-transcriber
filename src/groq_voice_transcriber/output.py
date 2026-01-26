import os
from pathlib import Path
from typing import Optional


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def output_paths(
    input_path: str,
    out_dir: str,
    root_dir: Optional[str] = None,
) -> str:
    input_path = os.path.abspath(input_path)
    out_dir = os.path.abspath(out_dir)

    if root_dir:
        root_dir = os.path.abspath(root_dir)
        rel_path = os.path.relpath(input_path, root_dir)
        rel_dir = os.path.dirname(rel_path)
        target_dir = os.path.join(out_dir, rel_dir)
    else:
        target_dir = out_dir

    ensure_dir(target_dir)
    base_name = Path(input_path).stem
    text_path = os.path.join(target_dir, f"{base_name}.txt")
    return text_path


def write_text(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text.strip() + "\n")


def _find_overlap_suffix_prefix(a: str, b: str, max_len: int = 80) -> int:
    max_len = min(max_len, len(a), len(b))
    for size in range(max_len, 0, -1):
        if a[-size:] == b[:size]:
            return size
    return 0


def merge_text_chunks(texts: list[str]) -> str:
    combined = ""
    for text in texts:
        if not combined:
            combined = text.strip()
            continue
        overlap = _find_overlap_suffix_prefix(combined, text)
        if overlap > 0:
            combined = combined + text[overlap:]
        else:
            combined = combined.rstrip() + "\n" + text.lstrip()
    return combined
