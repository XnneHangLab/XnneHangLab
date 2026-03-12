from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from lab.plugin.loader import SkillDescriptor
    from lab.tools.manager import ToolManager


class SystemPromptBuilder:
    def __init__(self, workspace_root: Path) -> None:
        self._root = workspace_root

    def build(
        self,
        *,
        persona_path: str | None,
        format_path: str | None,
        skills: list[SkillDescriptor],
        tool_manager: ToolManager | None,
        emotion_keys: list[str] | None = None,
    ) -> str:
        parts: list[str] = []

        if persona_path:
            persona_file = self._root / persona_path
            if persona_file.exists():
                parts.append(persona_file.read_text(encoding="utf-8").strip())

        if format_path:
            format_file = self._root / format_path
            if format_file.exists():
                parts.append(format_file.read_text(encoding="utf-8").strip())

        # emotion key 紧跟 format，语义上属于表情系统的一部分
        if emotion_keys:
            lines = ["以下是你可用的全部 Emotion Tag，请从中选择，不要使用列表以外的 Tag："]
            lines.extend(f"- {k}" for k in emotion_keys)
            parts.append("\n".join(lines))

        if skills:
            lines = ["你有以下技能可按需调用："]
            for skill in sorted(skills, key=lambda item: item.priority):
                files_str = ", ".join(str(skill.plugin_dir / file_path) for file_path in skill.files)
                lines.append(f"- {skill.id}: {skill.description} -> {files_str}")
            lines.append("需要时读取对应文件获取详细指引。")
            parts.append("\n".join(lines))

        if tool_manager:
            tool_prompt = tool_manager.build_system_prompt()
            if tool_prompt:
                parts.append(tool_prompt)

        return "\n\n".join(parts)
