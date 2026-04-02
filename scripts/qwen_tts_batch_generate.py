from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import cast

from lab.api.clients import QwenTTSClient, QwenTTSRequest
from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.profile.schema import Profile

INPUT_TEXT_FILE = Path("data/qwen_tts_batch_input.txt")
OUTPUT_DIR = Path("output/qwen_tts_batch")
SERVER = "http://127.0.0.1:12393"
PROFILE_PATH: str | None = None
EMOTION = "default"
REF_AUDIO_PATH: str | None = None
REF_TEXT: str | None = None
PRUNE_STALE = False
MAP_FILE_NAME = "_text_index_map.json"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch generate stable-index wav files via the local FastAPI Qwen-TTS endpoint."
    )
    parser.add_argument("--input", type=Path, default=INPUT_TEXT_FILE, help="Text file, one line = one audio.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="Output directory.")
    parser.add_argument("--server", default=SERVER, help="FastAPI server base URL.")
    parser.add_argument(
        "--profile",
        default=PROFILE_PATH,
        help="Profile TOML path. Omit to use [agent].memory_agent_profile from lab.toml.",
    )
    parser.add_argument(
        "--emotion",
        default=EMOTION,
        help="Emotion key from profile [character.tts.emotions]. Ignored when --ref-audio-path is set.",
    )
    parser.add_argument(
        "--ref-audio-path",
        default=REF_AUDIO_PATH,
        help="Reference audio path. When set, profile/emotion resolution is skipped.",
    )
    parser.add_argument(
        "--ref-text",
        default=REF_TEXT,
        help="Reference text matching the reference audio. Required when --ref-audio-path is set.",
    )
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


def _load_json_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in: {path}")
    return cast("dict[str, object]", payload)


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


def _resolve_profile_path(repo_root: Path, profile_path_arg: str | None) -> Path:
    if profile_path_arg:
        profile_path = Path(profile_path_arg)
    else:
        settings = load_settings_file("lab.toml", XnneHangLabSettings)
        if not settings.agent.memory_agent_profile.strip():
            raise ValueError("No --profile provided, and [agent].memory_agent_profile is empty in lab.toml.")
        profile_path = Path(settings.agent.memory_agent_profile)

    if not profile_path.is_absolute():
        profile_path = repo_root / profile_path
    profile_path = profile_path.resolve()
    if not profile_path.is_file():
        raise FileNotFoundError(f"Profile not found: {profile_path}")
    return profile_path


def _resolve_manual_ref(repo_root: Path, ref_audio_path: str, ref_text: str | None) -> tuple[Path, str, str]:
    resolved_ref_audio = Path(ref_audio_path)
    if not resolved_ref_audio.is_absolute():
        resolved_ref_audio = repo_root / resolved_ref_audio
    resolved_ref_audio = resolved_ref_audio.resolve()
    if not resolved_ref_audio.is_file():
        raise FileNotFoundError(f"Reference audio not found: {resolved_ref_audio}")

    normalized_ref_text = (ref_text or "").strip()
    if not normalized_ref_text:
        raise ValueError("--ref-text is required when --ref-audio-path is set.")

    return resolved_ref_audio, normalized_ref_text, "manual"


def _resolve_profile_ref(
    repo_root: Path, profile_path: Path, emotion: str, ref_text_override: str | None
) -> tuple[Path, str, str]:
    profile = Profile.from_toml(profile_path)
    if profile.character is None:
        raise ValueError(f"Profile has no [character] config: {profile_path}")

    tts_config = profile.character.tts
    if not tts_config.character_name.strip():
        raise ValueError(f"Profile [character.tts].character_name is empty: {profile_path}")
    if not tts_config.emotions:
        raise ValueError(f"Profile [character.tts.emotions] is empty: {profile_path}")

    selected_emotion = emotion if emotion in tts_config.emotions else next(iter(tts_config.emotions.keys()))
    emotion_config = tts_config.emotions[selected_emotion]
    if not emotion_config.path.strip():
        raise ValueError(f"Emotion '{selected_emotion}' has an empty ref path in: {profile_path}")

    resolved_ref_audio: Path | None = None
    for base_dir in (
        repo_root / "models" / "genie-tts" / tts_config.character_name,
        repo_root / "models" / "gsv-tts-lite" / tts_config.character_name,
    ):
        candidate = (base_dir / emotion_config.path).resolve()
        if candidate.is_file():
            resolved_ref_audio = candidate
            break
    if resolved_ref_audio is None:
        raise FileNotFoundError(
            f"Reference audio not found for emotion '{selected_emotion}' in profile: {profile_path}"
        )

    resolved_ref_text = (ref_text_override or emotion_config.ref_text).strip()
    if not resolved_ref_text:
        raise ValueError(
            f"Emotion '{selected_emotion}' has no ref_text in profile, and --ref-text was not provided: {profile_path}"
        )

    return resolved_ref_audio, resolved_ref_text, selected_emotion


def _post_tts(*, server: str, text: str, ref_audio_path: Path, ref_text: str) -> bytes:
    client = QwenTTSClient()
    client.base_url = server.rstrip("/") + "/tts/qwen-tts/generate"
    response = client.post(
        QwenTTSRequest(
            text=text,
            ref_audio_path=str(ref_audio_path),
            ref_text=ref_text,
        )
    )
    if response is None:
        raise RuntimeError(client.last_error or "Qwen-TTS request failed")
    return response["audio_byte"]


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

    profile_label = "<manual>"
    if args.ref_audio_path:
        resolved_ref_audio, resolved_ref_text, resolved_emotion = _resolve_manual_ref(
            repo_root,
            args.ref_audio_path,
            args.ref_text,
        )
    else:
        profile_path = _resolve_profile_path(repo_root, args.profile)
        profile_label = str(profile_path)
        resolved_ref_audio, resolved_ref_text, resolved_emotion = _resolve_profile_ref(
            repo_root,
            profile_path,
            args.emotion,
            args.ref_text,
        )

    active_files: set[Path] = set()
    total = len(texts)
    print(f"[config] server={args.server.rstrip('/')}")
    print(f"[config] input={input_path}")
    print(f"[config] output_dir={output_dir}")
    print(f"[config] profile={profile_label}")
    print(f"[config] emotion={resolved_emotion}")
    print(f"[config] ref_audio_path={resolved_ref_audio}")
    print(f"[config] ref_text={resolved_ref_text}")

    for order, text in enumerate(texts, start=1):
        index = current_mapping[text]
        output_path = _build_output_path(output_dir, index, text)
        active_files.add(output_path)
        temp_output_path = _build_temp_output_path(output_path)
        temp_output_path.unlink(missing_ok=True)

        wav_bytes = _post_tts(
            server=args.server,
            text=text,
            ref_audio_path=resolved_ref_audio,
            ref_text=resolved_ref_text,
        )
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
