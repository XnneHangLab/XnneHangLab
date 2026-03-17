"""声明式配置校验框架。

每个 package 通过 PackageRule 声明自己的模型依赖和 package 间依赖。
校验引擎只校验已启用的 package，并为每个错误提供具体的修复命令。
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, cast

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Callable

    from lab.config_manager.config import XnneHangLabSettings


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


def _default_depends_on() -> list[str]:
    """Return a typed default dependency list."""
    return []


def _default_models() -> list[ModelRequirement]:
    """Return a typed default model requirement list."""
    return []


def _default_extra_checks() -> list[Callable[[XnneHangLabSettings], str | None]]:
    """Return a typed default extra check list."""
    return []


@dataclass
class ModelRequirement:
    """一个模型文件/目录的校验规则。"""

    name: str
    """显示名，用于错误信息，如 'Silero VAD 模型'"""

    path_getter: Callable[[XnneHangLabSettings], Path | None]
    """从配置中提取路径的函数。返回 None 表示路径未配置。"""

    install_hint: str
    """提示用户如何安装，如 'just install-gsv-model'"""

    is_dir: bool = False
    """True 表示校验目录存在，False 表示校验文件存在"""


@dataclass
class PackageRule:
    """一个 package 的完整校验规则。"""

    package_name: str
    """对应 PackagesSettings 中的字段名，如 'gpt_sovits'"""

    depends_on: list[str] = field(default_factory=_default_depends_on)
    """依赖的其他 package 名，如 ['local_embedding']"""

    models: list[ModelRequirement] = field(default_factory=_default_models)
    """需要存在的模型文件/目录列表"""

    extra_checks: list[Callable[[XnneHangLabSettings], str | None]] = field(default_factory=_default_extra_checks)
    """额外校验函数列表。返回 None 表示通过，返回 str 表示错误信息。"""


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _resolve_path(settings: XnneHangLabSettings, raw_path: str) -> Path | None:
    """将配置中的相对路径解析为基于 root_dir 的绝对路径。"""
    if not raw_path or not raw_path.strip():
        return None
    p = Path(raw_path)
    if not p.is_absolute():
        p = Path(settings.root.root_dir) / p
    return p


# ---------------------------------------------------------------------------
# extra_checks 实现
# ---------------------------------------------------------------------------


def _check_nltk_data(settings: XnneHangLabSettings) -> str | None:
    """校验 gpt_sovits 依赖的 nltk averaged_perceptron_tagger_eng 数据。"""
    del settings

    try:
        nltk = importlib.import_module("nltk")
        nltk.data.find("taggers/averaged_perceptron_tagger_eng")
        return None
    except LookupError:
        return (
            " [gpt_sovits]\n"
            " nltk averaged_perceptron_tagger_eng 数据未下载\n"
            " -> 运行 `just install-nltk`"
        )
    except ImportError:
        # nltk 本身未安装，后续 import 时会报错，这里不重复提示
        return None


def _check_qwen_asr_preload_models(settings: XnneHangLabSettings) -> str | None:
    """校验 qwen_asr.preload_models 中指定的模型路径是否存在。"""
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
            " preload_models 中指定的模型不存在:\n"
            + "\n".join(missing)
            + "\n"
            " -> 运行 `just install-qwen-asr`"
        )
    return None


def _check_chat_api_key(settings: XnneHangLabSettings) -> str | None:
    """校验当前 chat_model 使用的 provider 是否配置了 API key。"""
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
    """校验 translate_provider 与对应配置的一致性。"""
    translate_provider = settings.agent.translate_provider
    if translate_provider == "deeplx":
        if not settings.agent.translate.deeplx.api_key.strip():
            return (
                " [agent.translate.deeplx]\n"
                " 当前翻译 provider 为 deeplx，但 api_key 为空\n"
                ' -> 配置 [agent.translate.deeplx].api_key，或将 [agent].translate_provider 改为 "llm"'
            )

    if translate_provider == "llm":
        if not settings.package.llm_translate:
            return (
                " [package]\n"
                " 当前翻译 provider 为 llm，但 package.llm_translate = false\n"
                " -> 在 [package] 下设置 llm_translate = true，并运行 `just install-llm-translate`\n"
                ' 或将 [agent].translate_provider 改为 "deeplx" 并配置 key'
            )

    return None


def _check_profiles(settings: XnneHangLabSettings) -> list[str]:
    """校验 profile 文件存在性及 memory 插件与 memory_bench 的一致性。"""
    import tomllib

    errors: list[str] = []
    ws_root = Path(settings.root.root_dir)

    # memory_agent_profile
    memory_agent_profile = settings.agent.memory_agent_profile
    if memory_agent_profile:
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
                with profile_path.open("rb") as f:
                    profile_data: dict[str, object] = tomllib.load(f)
                character_obj = profile_data.get("character")
                if not isinstance(character_obj, dict):
                    errors.append(
                        " [agent.memory_agent_profile]\n"
                        f" profile '{memory_agent_profile}' 缺少 [character] 配置\n"
                        " -> VTuber 主链路的 memory_agent_profile 必须在 profile 中声明 [character]"
                    )
                plugins_obj: object = profile_data.get("plugins")
                if isinstance(plugins_obj, dict):
                    plugins_dict = cast("dict[str, object]", plugins_obj)
                    enabled_plugins_obj: object = plugins_dict.get("enabled")
                    enabled_plugins: list[str] = []
                    if isinstance(enabled_plugins_obj, list):
                        for plugin in cast("list[object]", enabled_plugins_obj):
                            if isinstance(plugin, str):
                                enabled_plugins.append(plugin)
                    if "memory" in enabled_plugins:
                        if not settings.package.memory_bench:
                            errors.append(
                                " [package]\n"
                                f" profile '{memory_agent_profile}' 启用了 memory 插件，但 memory_bench = false\n"
                                " -> 在 [package] 下设置 memory_bench = true"
                            )
            except Exception:
                pass

    # memory_chat_profile
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

    return errors


# ---------------------------------------------------------------------------
# Package 规则注册（按依赖拓扑排序：被依赖的在前面）
# ---------------------------------------------------------------------------


PACKAGE_RULES: list[PackageRule] = [
    # --- 基础服务（被其他 package 依赖）---
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
    # --- 依赖其他 package 的服务 ---
    PackageRule(
        package_name="memory_bench",
        depends_on=["local_embedding"],
        # memory_bench 自身无额外模型，依赖 local_embedding 的模型
    ),
    # --- ASR ---
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
    # --- TTS ---
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


# ---------------------------------------------------------------------------
# 校验引擎
# ---------------------------------------------------------------------------


def validate_packages(settings: XnneHangLabSettings) -> list[str]:
    """校验所有已启用 package 的模型依赖和 package 间依赖。

    Args:
        settings: 完整的 XnneHangLabSettings 配置对象

    Returns:
        错误信息列表，空列表表示全部通过
    """
    errors: list[str] = []

    for rule in PACKAGE_RULES:
        enabled = getattr(settings.package, rule.package_name, False)
        if not enabled:
            continue

        # 检查 package 间依赖
        for dep in rule.depends_on:
            if not getattr(settings.package, dep, False):
                errors.append(
                    f" [package]\n"
                    f" {rule.package_name} = true，但依赖的 {dep} = false\n"
                    f" -> 在 [package] 下设置 {dep} = true"
                )

        # 检查模型文件/目录
        for model in rule.models:
            path = model.path_getter(settings)
            if path is None:
                errors.append(
                    f" [{rule.package_name}]\n"
                    f" {model.name} 路径未配置\n"
                    f" -> 运行 `{model.install_hint}`"
                )
                continue
            path_exists = path.is_dir() if model.is_dir else path.is_file()
            if not path_exists:
                errors.append(
                    f" [{rule.package_name}]\n"
                    f" {model.name} 不存在: {path}\n"
                    f" -> 运行 `{model.install_hint}`"
                )

        # 额外检查
        for check in rule.extra_checks:
            err = check(settings)
            if err:
                errors.append(err)

    return errors


def validate_all(settings: XnneHangLabSettings) -> list[str]:
    """执行所有校验：API key、profile、translate、package 模型依赖。

    Args:
        settings: 完整的 XnneHangLabSettings 配置对象

    Returns:
        错误信息列表，空列表表示全部通过
    """
    logger.debug("Running declarative configuration validation")

    errors: list[str] = []

    # 全局校验（不依赖 package 开关）
    api_err = _check_chat_api_key(settings)
    if api_err:
        errors.append(api_err)

    translate_err = _check_translate_config(settings)
    if translate_err:
        errors.append(translate_err)

    errors += _check_profiles(settings)

    # Package 模型依赖校验
    errors += validate_packages(settings)

    return errors
