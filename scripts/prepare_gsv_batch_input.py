from __future__ import annotations

import argparse
from pathlib import Path

from lab.utils.sentence_divider import segment_full
from lab.utils.text_cleaner import TextCleaner

DEFAULT_OUTPUT = Path("data/gsv_batch_input.txt")
SUPPORTED_SUFFIXES = {".txt", ".md", ".markdown", ".text"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read a text-like file, segment it into TTS-friendly sentences, and write one sentence per line."
    )
    parser.add_argument("--input", type=Path, required=True, help="Input text file path, for example .txt or .md.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output text file path.")
    parser.add_argument(
        "--segment-method",
        default="pysbd",
        choices=("pysbd", "regex"),
        help="Sentence segmentation backend.",
    )
    parser.add_argument(
        "--max-sentence-len",
        type=int,
        default=20,
        help="Maximum sentence length before secondary splitting inside the shared divider path. Use 0 for no limit.",
    )
    return parser.parse_args()


def _resolve_path(repo_root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def _validate_input(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")
    if path.suffix.lower() and path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(
            f"Unsupported input file type: {path.suffix}. Supported types: {', '.join(sorted(SUPPORTED_SUFFIXES))}"
        )


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _write_output(path: Path, sentences: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(sentences) + "\n", encoding="utf-8")


def main() -> None:
    args = _parse_args()
    repo_root = _repo_root()

    input_path = _resolve_path(repo_root, args.input)
    output_path = _resolve_path(repo_root, args.output)

    _validate_input(input_path)
    source_text = _read_text(input_path)
    sentences = segment_full(
        source_text,
        cleaner=TextCleaner(),
        max_sentence_len=args.max_sentence_len,
        segment_method=args.segment_method,
    )

    if not sentences:
        raise ValueError(f"No usable sentences found in: {input_path}")

    _write_output(output_path, sentences)
    print(f"[input] {input_path}")
    print(f"[output] {output_path}")
    print(f"[sentences] {len(sentences)}")


if __name__ == "__main__":
    main()
