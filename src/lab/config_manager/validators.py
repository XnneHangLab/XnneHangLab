"""声明式配置校验框架。

每个 package 通过 `PackageRule` 声明自己的模型依赖和 package
间依赖。校验引擎只校验已启用的 package，并为每个错误提供具体的修复提示。
"""

from __future__ import annotations

import importlib
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from loguru import logger
from pydantic import ValidationError

from lab.plugin.config import validate_plugin_override

if TYPE_CHECKING:
    from collections.abc import Callable

    from lab.config_manager.config import XnneHangLabSettings


def _default_depends_on() -> list[str]:
    """返回默认的 package 依赖列表。

    Returns:
        空的依赖列表。
    """
    return []


def _default_models() -> list[ModelRequirement]:
    """返回默认的模型依赖列表。

    Returns:
        空的模型依赖列表。
    """
    return []


def _default_extra_checks() -> list[Callable[[XnneHangLabSettings], str | None]]:
    """返回默认的额外校验函数列表。

    Returns:
        空的额外校验列表。
    """
    return []


@dataclass
class ModelRequirement:
    """描述单个模型文件或目录的校验规则。

    Attributes:
        name: 显示名，用于拼接错误信息。
        path_getter: 从完整配置中提取模型路径的函数。
        install_hint: 对应的安装提示命令。
        is_dir: 是否要求目标路径为目录。
    """

    name: str
    path_getter: Callable[[XnneHangLabSettings], Path | None]
    install_hint: str
    is_dir: bool = False


@dataclass
class PackageRule:
    """描述单个 package 的完整校验规则。

    Attributes:
        package_name: 对应 `PackagesSettings` 中的字段名。
        depends_on: 依赖的其他 package 名称列表。
        models: 需要存在的模型文件或目录列表。
        extra_checks: 额外校验函数列表。
    """

    package_name: str
    depends_on: list[str] = field(default_factory=_default_depends_on)
    models: list[ModelRequirement] = field(default_factory=_default_models)
    extra_checks: list[Callable[[XnneHangLabSettings], str | None]] = field(default_factory=_default_extra_checks)


def _resolve_path(settings: XnneHangLabSettings, raw_path: str) -> Path | None:
    """将配置中的路径解析为绝对路径。

    Args:
        settings: 完整配置对象。
        raw_path: 配置中的原始路径字符串。

    Returns:
        解析后的绝对路径；若路径为空则返回 `None`。
    """
    if not raw_path or not raw_path.strip():
        return None
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path(settings.root.root_dir) / path
    return path


def _check_nltk_data(settings: XnneHangLabSettings) -> str | None:
    """校验 `gpt_sovits` 所需的 NLTK 数据是否存在。

    Args:
        settings: 完整配置对象。

    Returns:
        错误信息；若校验通过则返回 `None`。
    """
    del settings

    try:
        nltk = importlib.import_module("nltk")
        nltk.data.find("taggers/averaged_perceptron_tagger_eng")
        return None
    except LookupError:
        return " [gpt_sovits]\n nltk averaged_perceptron_tagger_eng 数据未下载\n -> 运行 `just install-nltk`"
    except ImportError:
        return None


def _check_qwen_asr_preload_models(settings: XnneHangLabSettings) -> str | None:
    """校验 `qwen_asr.preload_models` 中声明的模型路径。

    Args:
        settings: 完整配置对象。

    Returns:
        错误信息；若校验通过则返回 `None`。
    """
    missing: list[str] = []
    for model_name in settings.asr.qwen_asr.preload_models:
        if model_name == "0.6b":
            path = _resolve_path(settings, settings.asr.qwen_asr.model_0_6b_path)
        elif model_name == "1.7b":
            path = _resolve_path(settings, settings.asr.qwen_asr.model_1_7b_path)
        else:
            continue

        if path is not None and not path.exists():
            missing.append(f" preload model '{model_name}' 不存在: {path}")

    if missing:
        return (
            " [asr.qwen_asr]\n"
            " preload_models 中指定的模型不存在:\n" + "\n".join(missing) + "\n"
            " -> 运行 `just install-qwen-asr`"
        )
    return None


def _check_chat_api_key(settings: XnneHangLabSettings) -> str | None:
    """校验当前聊天模型 provider 的 API key。

    Args:
        settings: 完整配置对象。

    Returns:
        错误信息；若校验通过则返回 `None`。
    """
    chat_provider = settings.agent.chat_model.llm_provider
    llm_cfg = getattr(settings.agent.llm, chat_provider.replace("-", "_"), None)
    if llm_cfg is not None and not llm_cfg.llm_api_key:
        return (
            f" [agent.llm.{chat_provider}]\n"
            " llm_api_key 未配置\n"
            f" -> 在 config/lab.toml 的 [agent.llm.{chat_provider}] 下设置 llm_api_key"
        )
    return None


def _check_translate_config(settings: XnneHangLabSettings) -> str | None:
    """校验翻译 provider 与其配置是否一致。

    Args:
        settings: 完整配置对象。

    Returns:
        错误信息；若校验通过则返回 `None`。
    """
    translate_provider = settings.agent.translate_provider
    if translate_provider == "deeplx" and not settings.agent.translate.deeplx.api_key.strip():
        return (
            " [agent.translate.deeplx]\n"
            " 当前翻译 provider 为 deeplx，但 api_key 为空\n"
            ' -> 配置 [agent.translate.deeplx].api_key，或将 [agent].translate_provider 改为 "llm"'
        )

    if translate_provider == "llm" and not settings.package.llm_translate:
        return (
            " [package]\n"
            " 当前翻译 provider 为 llm，但 package.llm_translate = false\n"
            " -> 在 [package] 下设置 llm_translate = true，并运行 `just install-llm-translate`\n"
            ' 或将 [agent].translate_provider 改为 "deeplx" 并配置 key'
        )

    return None


def _check_profiles(settings: XnneHangLabSettings) -> list[str]:
    """校验 profile 路径及其角色字段。

    `memory_agent_profile` 现在不再回退到 `lab.toml`，
    因此激活的 VTuber profile 必须存在且必须声明 `[character]`。

    Args:
        settings: 完整配置对象。

    Returns:
        错误信息列表。
    """
    errors: list[str] = []
    ws_root = Path(settings.root.root_dir)

    memory_agent_profile = settings.agent.memory_agent_profile
    if not memory_agent_profile:
        errors.append(
            " [agent.memory_agent_profile]\n"
            " VTuber 主链路未配置 active profile\n"
            ' -> 在 [agent] 下设置 memory_agent_profile = "profiles/xxx.toml"'
        )
    else:
        profile_path = Path(memory_agent_profile)
        if not profile_path.is_absolute():
            profile_path = ws_root / memory_agent_profile

        if not profile_path.exists():
            errors.append(
                f" [agent.memory_agent_profile]\n"
                f" 文件不存在: {profile_path}\n"
                " -> 检查路径是否正确，或创建对应的 profile 文件"
            )
        else:
            try:
                with profile_path.open("rb") as file:
                    profile_data: dict[str, object] = tomllib.load(file)
            except Exception as exc:
                errors.append(f" [agent.memory_agent_profile]\n profile 解析失败: {profile_path}\n -> {exc}")
            else:
                character_obj = profile_data.get("character")
                if not isinstance(character_obj, dict):
                    errors.append(
                        " [agent.memory_agent_profile]\n"
                        f" profile '{memory_agent_profile}' 缺少 [character] 配置\n"
                        " -> VTuber 主链路的 active profile 必须在 profile 中声明 [character]"
                    )

                plugins_obj = profile_data.get("plugins")
                if isinstance(plugins_obj, dict):
                    plugins_dict = cast("dict[str, object]", plugins_obj)
                    errors += _check_profile_plugin_overrides(
                        ws_root=ws_root,
                        profile_label=memory_agent_profile,
                        plugins_obj=plugins_dict,
                    )
                    enabled_plugins_obj = plugins_dict.get("enabled")
                    enabled_plugins: list[str] = []
                    if isinstance(enabled_plugins_obj, list):
                        for plugin in cast("list[object]", enabled_plugins_obj):
                            if isinstance(plugin, str):
                                enabled_plugins.append(plugin)
                    if "memory" in enabled_plugins and not settings.package.memory_bench:
                        errors.append(
                            " [package]\n"
                            f" profile '{memory_agent_profile}' 启用了 memory 插件，但 memory_bench = false\n"
                            " -> 在 [package] 下设置 memory_bench = true"
                        )

    memory_chat_profile = settings.agent.memory_chat_profile
    if memory_chat_profile:
        chat_profile_path = Path(memory_chat_profile)
        if not chat_profile_path.is_absolute():
            chat_profile_path = ws_root / memory_chat_profile
        if not chat_profile_path.exists():
            errors.append(
                f" [agent.memory_chat_profile]\n"
                f" 文件不存在: {chat_profile_path}\n"
                " -> 检查路径是否正确，或创建对应的 profile 文件"
            )
        else:
            try:
                with chat_profile_path.open("rb") as file:
                    chat_profile_data: dict[str, object] = tomllib.load(file)
            except Exception as exc:
                errors.append(f" [agent.memory_chat_profile]\n profile 解析失败: {chat_profile_path}\n -> {exc}")
            else:
                plugins_obj = chat_profile_data.get("plugins")
                if isinstance(plugins_obj, dict):
                    errors += _check_profile_plugin_overrides(
                        ws_root=ws_root,
                        profile_label=memory_chat_profile,
                        plugins_obj=cast("dict[str, object]", plugins_obj),
                    )

    return errors


def _check_profile_plugin_overrides(
    *,
    ws_root: Path,
    profile_label: str,
    plugins_obj: dict[str, object],
) -> list[str]:
    errors: list[str] = []
    enabled_plugins_obj = plugins_obj.get("enabled")
    enabled_plugins: list[str] = []
    if isinstance(enabled_plugins_obj, list):
        for plugin in cast("list[object]", enabled_plugins_obj):
            if isinstance(plugin, str):
                enabled_plugins.append(plugin)

    candidate_plugin_dirs = [ws_root / "src" / "lab" / "plugins", Path(__file__).resolve().parents[1] / "plugins"]
    for plugin_id in enabled_plugins:
        plugin_override = plugins_obj.get(plugin_id, {})
        if not isinstance(plugin_override, dict):
            errors.append(
                f" [plugins.{plugin_id}]\n"
                f" profile '{profile_label}' 的插件 override 必须是 table/object"
            )
            continue

        plugin_dir = next(
            (candidate_dir / plugin_id for candidate_dir in candidate_plugin_dirs if (candidate_dir / plugin_id / "plugin.toml").is_file()),
            None,
        )
        if plugin_dir is None:
            continue

        try:
            validate_plugin_override(plugin_id, plugin_dir, cast("dict[str, Any]", plugin_override))
        except ValidationError as exc:
            errors.append(
                f" [plugins.{plugin_id}]\n"
                f" profile '{profile_label}' 的插件配置无效\n"
                f" -> {exc}"
            )

    return errors


PACKAGE_RULES: list[PackageRule] = [
    PackageRule(
        package_name="local_embedding",
        models=[
            ModelRequirement(
                name="Embedding GGUF 模型 (bge-m3)",
                path_getter=lambda s: _resolve_path(s, s.local_embedding.model_path),
                install_hint="just download-local-embedding",
            ),
        ],
    ),
    PackageRule(
        package_name="llm_translate",
        models=[
            ModelRequirement(
                name="LLM Translate GGUF 模型 (Qwen2.5-0.5B)",
                path_getter=lambda s: _resolve_path(s, s.agent.translate.llm.model_path),
                install_hint="just install-llm-translate",
            ),
        ],
    ),
    PackageRule(
        package_name="memory_bench",
        depends_on=["local_embedding"],
    ),
    PackageRule(
        package_name="sherpa_asr",
        models=[
            ModelRequirement(
                name="Sherpa-ONNX Paraformer 模型目录",
                path_getter=lambda s: _resolve_path(s, s.asr.sherpa.asr_model_dir),
                install_hint="just install-sherpa-model",
                is_dir=True,
            ),
            ModelRequirement(
                name="Silero VAD 模型",
                path_getter=lambda s: _resolve_path(s, s.asr.vad_model_path),
                install_hint="just install-sherpa-model",
            ),
        ],
    ),
    PackageRule(
        package_name="qwen_asr",
        models=[
            ModelRequirement(
                name="Qwen3-ForcedAligner 模型",
                path_getter=lambda s: (
                    _resolve_path(s, s.asr.qwen_asr.forced_aligner_path) if s.asr.qwen_asr.forced_aligner_path else None
                ),
                install_hint="just install-qwen-asr",
                is_dir=True,
            ),
        ],
        extra_checks=[_check_qwen_asr_preload_models],
    ),
    PackageRule(
        package_name="gpt_sovits",
        models=[
            ModelRequirement(
                name="GPT-SoVITS elaina 模型",
                path_getter=lambda s: Path(s.root.root_dir) / "models" / "gptsovits" / "elaina",
                install_hint="just install-gsv-model",
                is_dir=True,
            ),
            ModelRequirement(
                name="Chinese HuBERT (chinese-hubert-base)",
                path_getter=lambda s: Path(s.root.root_dir) / "models" / "chinese-hubert-base",
                install_hint="just install-bert-model",
                is_dir=True,
            ),
            ModelRequirement(
                name="Chinese RoBERTa (chinese-roberta-wwm-ext-large)",
                path_getter=lambda s: Path(s.root.root_dir) / "models" / "chinese-roberta-wwm-ext-large",
                install_hint="just install-bert-model",
                is_dir=True,
            ),
        ],
        extra_checks=[_check_nltk_data],
    ),
    PackageRule(
        package_name="qwen_tts",
        models=[
            ModelRequirement(
                name="Qwen3-TTS 模型 (Qwen3-TTS-12Hz-1.7B-Base)",
                path_getter=lambda s: Path(s.root.root_dir) / "models" / "Qwen3-TTS-12Hz-1.7B-Base",
                install_hint="just install-qwen-tts",
                is_dir=True,
            ),
        ],
    ),
]


def validate_packages(settings: XnneHangLabSettings) -> list[str]:
    """校验已启用 package 的依赖与模型文件。

    Args:
        settings: 完整配置对象。

    Returns:
        错误信息列表；空列表表示全部通过。
    """
    errors: list[str] = []

    for rule in PACKAGE_RULES:
        enabled = getattr(settings.package, rule.package_name, False)
        if not enabled:
            continue

        for dep in rule.depends_on:
            if not getattr(settings.package, dep, False):
                errors.append(
                    f" [package]\n"
                    f" {rule.package_name} = true，但依赖的 {dep} = false\n"
                    f" -> 在 [package] 下设置 {dep} = true"
                )

        for model in rule.models:
            path = model.path_getter(settings)
            if path is None:
                errors.append(f" [{rule.package_name}]\n {model.name} 路径未配置\n -> 运行 `{model.install_hint}`")
                continue

            path_exists = path.is_dir() if model.is_dir else path.is_file()
            if not path_exists:
                errors.append(f" [{rule.package_name}]\n {model.name} 不存在: {path}\n -> 运行 `{model.install_hint}`")

        for check in rule.extra_checks:
            err = check(settings)
            if err:
                errors.append(err)

    return errors


def validate_all(settings: XnneHangLabSettings) -> list[str]:
    """执行完整配置校验。

    当前会依次校验：
    1. 聊天模型 API key
    2. 翻译配置
    3. profile 存在性与角色字段
    4. 已启用 package 的模型依赖

    Args:
        settings: 完整配置对象。

    Returns:
        错误信息列表；空列表表示全部通过。
    """
    logger.debug("Running declarative configuration validation")

    errors: list[str] = []

    api_err = _check_chat_api_key(settings)
    if api_err:
        errors.append(api_err)

    translate_err = _check_translate_config(settings)
    if translate_err:
        errors.append(translate_err)

    errors += _check_profiles(settings)
    errors += validate_packages(settings)

    return errors
