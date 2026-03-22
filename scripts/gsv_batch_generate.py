from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, cast

# Edit these lines for daily use.
INPUT_TEXT_FILE = Path("data/gsv_batch_input.txt")
OUTPUT_DIR = Path("output/gsv_batch")
SERVER = "http://127.0.0.1:12393"
CHARACTER = "baoqiao"
EMOTION = "neutral"
REF_TEXT: str | None = None

# Optional tuning.
REF_AUDIO_PATH: str | None = None
TEXT_LANGUAGE = "zh"
PROMPT_LANGUAGE: str | None = None
BATCH_SIZE = 20
SPEED = 1.0
TOP_K = 5
TOP_P = 1.0
TEMPERATURE = 1.0
CUT_METHOD = "auto_cut"
MAX_CUT_LENGTH = 50
SEED = -1
PARALLEL_INFER = False
REPETITION_PENALTY = 1.35
PRUNE_STALE = False
MAP_FILE_NAME = "_text_index_map.json"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch generate stable-index wav files via the local FastAPI GPT-SoVITS endpoint."
    )
    parser.add_argument("--input", type=Path, default=INPUT_TEXT_FILE, help="Text file, one line = one audio.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="Output directory.")
    parser.add_argument("--server", default=SERVER, help="FastAPI server base URL.")
    parser.add_argument("--character", default=CHARACTER, help="GPT-SoVITS character folder name.")
    parser.add_argument("--emotion", default=EMOTION, help="Emotion name defined in infer.json.")
    parser.add_argument(
        "--ref-text",
        default=REF_TEXT,
        help="Reference text. Omit to auto-use the selected emotion's prompt_text.",
    )
    parser.add_argument(
        "--ref-audio-path",
        default=REF_AUDIO_PATH,
        help="Reference wav path. Omit to auto-use the selected emotion's ref_wav_path.",
    )
    parser.add_argument(
        "--text-language",
        default=TEXT_LANGUAGE,
        help="Input text language, e.g. zh / en / ja / auto.",
    )
    parser.add_argument(
        "--prompt-language",
        default=PROMPT_LANGUAGE,
        help="Reference audio language. Omit to auto-use infer.json.",
    )
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--speed", type=float, default=SPEED)
    parser.add_argument("--top-k", type=int, default=TOP_K)
    parser.add_argument("--top-p", type=float, default=TOP_P)
    parser.add_argument("--temperature", type=float, default=TEMPERATURE)
    parser.add_argument("--cut-method", default=CUT_METHOD)
    parser.add_argument("--max-cut-length", type=int, default=MAX_CUT_LENGTH)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--parallel-infer", action="store_true", default=PARALLEL_INFER)
    parser.add_argument("--repetition-penalty", type=float, default=REPETITION_PENALTY)
    parser.add_argument(
        "--prune-stale",
        action="store_true",
        default=PRUNE_STALE,
        help="Delete old numbered wav files that are no longer in the input file.",
    )
    return parser.parse_args()


def _normalize_text(value: str) -> str:
    return value.strip()


def _read_input_lines(path: Path) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(f"Input text file not found: {path}")
    texts: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        text = _normalize_text(raw_line)
        if text:
            texts.append(text)
    if not texts:
        raise ValueError(f"No usable lines found in: {path}")
    return texts


def _ensure_unique_texts(texts: list[str]) -> None:
    counts: dict[str, int] = {}
    duplicates: list[str] = []
    for text in texts:
        counts[text] = counts.get(text, 0) + 1
        if counts[text] == 2:
            duplicates.append(text)
    if duplicates:
        preview = " | ".join(duplicates[:3])
        raise ValueError(
            "Input file contains duplicate non-empty lines. "
            "Stable numbering is based on exact text content, so duplicates are ambiguous. "
            f"Examples: {preview}"
        )


def _load_index_map(map_path: Path) -> dict[str, int]:
    if not map_path.is_file():
        return {}
    payload = _load_json_object(map_path)
    raw_items = payload.get("items", [])
    if not isinstance(raw_items, list):
        raise ValueError(f"Invalid map file format: {map_path}")
    mapping: dict[str, int] = {}
    for raw_item in cast("list[object]", raw_items):
        if not isinstance(raw_item, dict):
            continue
        item = cast("dict[str, object]", raw_item)
        text = item.get("text")
        index = item.get("index")
        if isinstance(text, str) and isinstance(index, int):
            mapping[text] = index
    return mapping


def _save_index_map(map_path: Path, mapping: dict[str, int]) -> None:
    items = [
        {"index": index, "text": text} for text, index in sorted(mapping.items(), key=lambda pair: (pair[1], pair[0]))
    ]
    payload = {"version": 1, "items": items}
    map_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _assign_indices(texts: list[str], mapping: dict[str, int]) -> dict[str, int]:
    next_index = max(mapping.values(), default=-1) + 1
    for text in texts:
        if text not in mapping:
            mapping[text] = next_index
            next_index += 1
    return {text: mapping[text] for text in texts}


def _safe_stem(text: str, max_len: int = 24) -> str:
    stem = re.sub(r"\s+", "_", text.strip())
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", stem)
    stem = stem.strip(" ._")
    if not stem:
        stem = "text"
    if len(stem) > max_len:
        stem = stem[:max_len].rstrip(" ._")
    return stem or "text"


def _build_output_path(output_dir: Path, index: int, text: str) -> Path:
    return output_dir / f"{index}_{_safe_stem(text)}.wav"


def _cleanup_old_variants(output_path: Path) -> None:
    pattern = f"{output_path.stem.split('_', 1)[0]}_*.wav"
    for candidate in output_path.parent.glob(pattern):
        if candidate != output_path:
            candidate.unlink(missing_ok=True)


def _maybe_prune_stale_files(output_dir: Path, active_files: set[Path]) -> None:
    numbered_wav = re.compile(r"^\d+_.+\.wav$", re.IGNORECASE)
    for candidate in output_dir.glob("*.wav"):
        if numbered_wav.match(candidate.name) and candidate not in active_files:
            candidate.unlink(missing_ok=True)


def _build_temp_output_path(output_path: Path) -> Path:
    return output_path.with_name(f".{output_path.stem}.tmp{output_path.suffix}")


def _load_json_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in: {path}")
    return cast("dict[str, object]", payload)


def _load_infer_json(repo_root: Path, character: str) -> dict[str, object]:
    infer_path = repo_root / "models" / "gptsovits" / character / "infer.json"
    if not infer_path.is_file():
        raise FileNotFoundError(f"infer.json not found for character '{character}': {infer_path}")
    return _load_json_object(infer_path)


def _resolve_reference_settings(
    *,
    repo_root: Path,
    character: str,
    emotion: str,
    ref_audio_path: str | None,
    ref_text: str | None,
    prompt_language: str | None,
) -> tuple[str, str, str, str]:
    infer_data = _load_infer_json(repo_root, character)
    raw_emotion_list = infer_data.get("emotion_list")
    if not isinstance(raw_emotion_list, dict) or not raw_emotion_list:
        raise ValueError(f"No emotion_list found in infer.json for character '{character}'.")
    emotion_list = cast("dict[str, object]", raw_emotion_list)

    selected_emotion = emotion if emotion in emotion_list else next(iter(emotion_list.keys()))
    raw_selected = emotion_list[selected_emotion]
    if not isinstance(raw_selected, dict):
        raise ValueError(f"Invalid emotion config for '{selected_emotion}'.")
    selected = cast("dict[str, object]", raw_selected)

    if ref_audio_path:
        ref_audio_candidate = Path(ref_audio_path)
        if ref_audio_candidate.is_absolute():
            try:
                relative_ref_audio = ref_audio_candidate.resolve().relative_to(
                    (repo_root / "models" / "gptsovits" / character).resolve()
                )
            except ValueError as exc:
                raise ValueError(
                    f"For the FastAPI v2 route, ref_audio_path must stay inside models/gptsovits/{character}."
                ) from exc
            resolved_ref_audio = relative_ref_audio.as_posix()
        else:
            resolved_ref_audio = ref_audio_candidate.as_posix()
    else:
        raw_ref_wav = selected.get("ref_wav_path")
        if not isinstance(raw_ref_wav, str) or not raw_ref_wav.strip():
            raise ValueError(f"Emotion '{selected_emotion}' has no ref_wav_path.")
        resolved_ref_audio = Path(raw_ref_wav).as_posix()

    absolute_ref_audio = (repo_root / "models" / "gptsovits" / character / resolved_ref_audio).resolve()
    if not absolute_ref_audio.is_file():
        raise FileNotFoundError(f"Reference audio not found: {absolute_ref_audio}")

    resolved_ref_text = ref_text
    if resolved_ref_text is None:
        candidate = selected.get("prompt_text")
        resolved_ref_text = candidate if isinstance(candidate, str) else ""

    resolved_prompt_language = prompt_language
    if resolved_prompt_language is None:
        candidate = selected.get("prompt_language")
        resolved_prompt_language = candidate if isinstance(candidate, str) else "auto"

    return selected_emotion, resolved_ref_audio, resolved_ref_text, resolved_prompt_language


def _post_tts(server: str, payload: dict[str, Any]) -> bytes:
    base = server.rstrip("/")
    url = f"{base}/tts/gptsovitsv2/tts"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "audio/wav"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"FastAPI returned HTTP {exc.code}: {details}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to connect to {url}: {exc.reason}") from exc


def _build_request_payload(
    *,
    text: str,
    character: str,
    emotion: str,
    ref_audio_path: str,
    prompt_text: str,
    prompt_language: str,
    text_language: str,
    batch_size: int,
    speed: float,
    top_k: int,
    top_p: float,
    temperature: float,
    cut_method: str,
    max_cut_length: int,
    seed: int,
    parallel_infer: bool,
    repetition_penalty: float,
) -> dict[str, Any]:
    return {
        "text": text,
        "character": character,
        "emotion": emotion,
        "ref_audio_path": ref_audio_path,
        "prompt_text": prompt_text,
        "prompt_language": prompt_language,
        "text_language": text_language,
        "batch_size": batch_size,
        "speed": speed,
        "top_k": top_k,
        "top_p": top_p,
        "temperature": temperature,
        "cut_method": cut_method,
        "max_cut_length": max_cut_length,
        "seed": seed,
        "parallel_infer": parallel_infer,
        "repetition_penalty": repetition_penalty,
        "audio_type": "wav",
        "streaming_mode": False,
    }


def main() -> None:
    args = _parse_args()
    repo_root = _repo_root()
    os.chdir(repo_root)

    input_path = (repo_root / args.input).resolve() if not args.input.is_absolute() else args.input.resolve()
    output_dir = (
        (repo_root / args.output_dir).resolve() if not args.output_dir.is_absolute() else args.output_dir.resolve()
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    texts = _read_input_lines(input_path)
    _ensure_unique_texts(texts)

    map_path = output_dir / MAP_FILE_NAME
    saved_mapping = _load_index_map(map_path)
    current_mapping = _assign_indices(texts, saved_mapping)
    _save_index_map(map_path, saved_mapping)

    resolved_emotion, resolved_ref_audio, resolved_ref_text, resolved_prompt_language = _resolve_reference_settings(
        repo_root=repo_root,
        character=args.character,
        emotion=args.emotion,
        ref_audio_path=args.ref_audio_path,
        ref_text=args.ref_text,
        prompt_language=args.prompt_language,
    )

    active_files: set[Path] = set()
    total = len(texts)
    print(f"[config] server={args.server.rstrip('/')}")
    print(f"[config] input={input_path}")
    print(f"[config] output_dir={output_dir}")
    print(f"[config] character={args.character} emotion={resolved_emotion}")
    print(f"[config] ref_audio_path={resolved_ref_audio}")
    print(f"[config] ref_text={resolved_ref_text}")
    print(f"[config] prompt_language={resolved_prompt_language}")

    for order, text in enumerate(texts, start=1):
        index = current_mapping[text]
        output_path = _build_output_path(output_dir, index, text)
        active_files.add(output_path)
        temp_output_path = _build_temp_output_path(output_path)
        temp_output_path.unlink(missing_ok=True)

        payload = _build_request_payload(
            text=text,
            character=args.character,
            emotion=resolved_emotion,
            ref_audio_path=resolved_ref_audio,
            prompt_text=resolved_ref_text,
            prompt_language=resolved_prompt_language,
            text_language=args.text_language,
            batch_size=args.batch_size,
            speed=args.speed,
            top_k=args.top_k,
            top_p=args.top_p,
            temperature=args.temperature,
            cut_method=args.cut_method,
            max_cut_length=args.max_cut_length,
            seed=args.seed,
            parallel_infer=args.parallel_infer,
            repetition_penalty=args.repetition_penalty,
        )
        wav_bytes = _post_tts(args.server, payload)
        temp_output_path.write_bytes(wav_bytes)
        temp_output_path.replace(output_path)
        _cleanup_old_variants(output_path)
        print(f"[{order}/{total}] #{index} -> {output_path.name}")

    if args.prune_stale:
        _maybe_prune_stale_files(output_dir, active_files)
        print("[cleanup] pruned stale numbered wav files")

    print(f"[done] generated {total} wav file(s)")
    print(f"[done] index map saved to {map_path}")


if __name__ == "__main__":
    main()
