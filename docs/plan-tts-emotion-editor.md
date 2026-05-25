# Plan: TTS Emotion Editor in Launcher (P2)

## Context

P1 (current PR `fix/neutral-expression-placeholder`) implements dynamic TTS emotion list
injection into the format prompt from `config/voices/<voice_id>.toml`. However, editing
TTS emotions currently requires manually editing the TOML file. This P2 adds a launcher UI
for managing TTS emotions with name/label separation (same pattern as Live2D expressions).

## Data Model

Voice config (`config/voices/luming.toml`) emotion entries gain a `label` field:

```toml
[emotions."平静"]
label = "平静"          # optional, defaults to emotion key name
description = "日常对话、平稳陈述"

[[emotions."平静".clips]]
id = "1"
ref_audio = "平静/1.wav"
ref_text_file = "平静/1.txt"
```

- `name` = emotion key / directory name (e.g., "平静") — auto-scanned from `voices/<bundle>/`, immutable
- `label` = display name used in `[tts:label]` tags — defaults to name, user-editable
- `description` = scene description injected into format prompt

## Implementation

### 1. Rust Backend (launcher/src-tauri/)

New Tauri commands:

- `read_voice_config(voice_id: String) -> VoiceConfig`
  - Reads `config/voices/<voice_id>.toml`
  - Returns structured data including emotions with label/description

- `write_voice_config(voice_id: String, config: VoiceConfig)`
  - Writes back to `config/voices/<voice_id>.toml`
  - Preserves clip data, only updates label/description

- `scan_voice_emotions(voice_id: String) -> Vec<String>`
  - Scans `voices/<asset_bundle>/` directory
  - Returns subdirectory names as available emotion names
  - Used to detect new emotions not yet in config

### 2. Launcher Frontend (launcher/src/)

Location: `ProfilesPage.tsx` → TTS section (after the existing voice/character_name fields)

UI components:
- Emotion list showing each emotion as a row:
  - Name (read-only, from directory scan)
  - Label input (editable, defaults to name)
  - Description input (editable, placeholder: "例：日常对话、平稳陈述")
- "同步目录" button to scan for new emotion directories and add them to config
- Auto-save on change (same pattern as other profile fields)

### 3. Python Backend (src/lab/agent/)

Update `agent_factory.py` TTS emotion list generation:
- When generating `{{TTS_EMOTION_LIST}}`, use `label` field if present, fall back to emotion key name
- Current code already reads `description` — just add `label` reading

### 4. Bridge Types (launcher/src/services/config/)

New file or extend existing:
- `voiceBridge.ts` — Tauri invoke wrappers for voice config commands
- `voiceConfig.ts` — TypeScript interfaces for VoiceConfig, VoiceEmotion

## Files to Create/Modify

| File | Action |
|------|--------|
| `launcher/src-tauri/src/runtime/voice.rs` | Create — Rust commands |
| `launcher/src-tauri/src/lib.rs` | Modify — register new commands |
| `launcher/src/services/config/voiceBridge.ts` | Create — Tauri bridge |
| `launcher/src/services/config/voiceConfig.ts` | Create — TypeScript types |
| `launcher/src/pages/ProfilesPage/ProfilesPage.tsx` | Modify — add TTS emotion editor |
| `src/lab/agent/agent_factory.py` | Modify — use label field in TTS list generation |
| `config/voices/luming.toml` | Modify — add label fields |

## Verification

1. Open launcher → 角色卡片 → select baoqiao → TTS section shows emotion list
2. Edit a label (e.g., "平静" → "calm") → verify config/voices/luming.toml updates
3. Edit description → verify it persists
4. Restart backend → verify format prompt shows updated label and description
5. Add a new emotion directory under voices/luming/ → click "同步目录" → new entry appears
