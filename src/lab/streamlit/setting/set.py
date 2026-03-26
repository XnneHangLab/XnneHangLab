from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, TypedDict, cast

import streamlit as st

from lab.api.clients import ReloadClient
from lab.config_manager import (
    ASRSettings,
    QwenASRSettings,
    SherpaASRSettings,
    XnneHangLabSettings,
    get_setting_title,
    load_settings_file,
    write_settings_file,
)
from lab.streamlit.i18n import ASRModelProvider
from lab.streamlit.session_keys import setting_keys
from lab.streamlit.style import style

if TYPE_CHECKING:
    from lab.config_manager.qwen_asr import QwenASRModelName

style()


@st.dialog("消息")
def message_box(title: str, message: str) -> None:
    """显示简单消息弹窗。

    Args:
        title: 标题。
        message: 正文。

    Returns:
        None.

    Raises:
        None.
    """
    st.markdown("")
    st.markdown(f"### {title}\n{message}")


def check_device_is_available(device: str) -> bool:
    """检查设备配置是否可用。

    Args:
        device: 待检查设备名。

    Returns:
        bool: 当前始终返回 True。

    Raises:
        None.
    """
    if device == "cuda":
        return True
    return True


lab_settings = load_settings_file("lab.toml", setting=XnneHangLabSettings)
asr_settings: ASRSettings = lab_settings.asr
sherpa_settings: SherpaASRSettings = asr_settings.sherpa
qwen_settings: QwenASRSettings = asr_settings.qwen_asr


class BasicSettingsDict(TypedDict):
    device: str
    custom_output_dir: bool
    cache_dir: str
    output_dir: str
    ffmpeg_path: str
    vad_model_path: str
    asr_model_provider: str


class SherpaSettingsDict(TypedDict):
    asr_model_dir: str
    num_threads: int


class QwenSettingsDict(TypedDict):
    model_dir: str
    preload_models: list[QwenASRModelName]
    model_0_6b_path: str
    model_1_7b_path: str
    device: str
    cpu_threads: int


class GlobalSettings(TypedDict):
    basic: BasicSettingsDict
    sherpa: SherpaSettingsDict
    qwen_asr: QwenSettingsDict


if setting_keys["initial_settings"] not in st.session_state:
    st.session_state[setting_keys["initial_settings"]] = {
        "basic": {
            "device": asr_settings.device,
            "custom_output_dir": asr_settings.custom_output_dir,
            "cache_dir": asr_settings.cache_dir,
            "output_dir": asr_settings.output_dir,
            "ffmpeg_path": asr_settings.FFMPEG_PATH,
            "vad_model_path": asr_settings.vad_model_path,
            "asr_model_provider": asr_settings.asr_model_provider,
        },
        "sherpa": {
            "asr_model_dir": sherpa_settings.asr_model_dir,
            "num_threads": sherpa_settings.num_threads,
        },
        "qwen_asr": {
            "model_dir": qwen_settings.model_dir,
            "preload_models": list(qwen_settings.preload_models),
            "model_0_6b_path": qwen_settings.model_0_6b_path,
            "model_1_7b_path": qwen_settings.model_1_7b_path,
            "device": qwen_settings.device,
            "cpu_threads": qwen_settings.cpu_threads,
        },
    }


device = st.session_state.get(setting_keys["device"], asr_settings.device)
ffmpeg_path = st.session_state.get(setting_keys["ffmpeg_path"], asr_settings.FFMPEG_PATH)
cache_dir = st.session_state.get(setting_keys["cache_dir"], asr_settings.cache_dir)
custom_output_dir = st.session_state.get(setting_keys["custom_output_dir"], asr_settings.custom_output_dir)
output_dir = st.session_state.get(setting_keys["output_dir"], asr_settings.output_dir)
asr_model_provider = st.session_state.get(setting_keys["asr_model_provider"], asr_settings.asr_model_provider)
vad_model_path = st.session_state.get(setting_keys["vad_model_path"], asr_settings.vad_model_path)

asr_model_dir = st.session_state.get(setting_keys["asr_model_dir"], sherpa_settings.asr_model_dir)
num_threads = st.session_state.get(setting_keys["num_threads"], sherpa_settings.num_threads)

qwen_model_dir = st.session_state.get(setting_keys["qwen_model_dir"], qwen_settings.model_dir)
qwen_preload_models = cast(
    "list[QwenASRModelName]",
    st.session_state.get(setting_keys["qwen_preload_models"], list(qwen_settings.preload_models)),
)
qwen_model_0_6b_path = st.session_state.get(setting_keys["qwen_model_0_6b_path"], qwen_settings.model_0_6b_path)
qwen_model_1_7b_path = st.session_state.get(setting_keys["qwen_model_1_7b_path"], qwen_settings.model_1_7b_path)
qwen_device = str(st.session_state.get(setting_keys["qwen_device"], qwen_settings.device)).upper()
if qwen_device != "CPU":
    qwen_device = "CPU"
qwen_cpu_threads = st.session_state.get(setting_keys["qwen_cpu_threads"], qwen_settings.cpu_threads)

save_container = st.container()
setting_container = st.container(border=True)

with setting_container:
    st.markdown("")
    st.markdown("###### 基础配置")
    st.markdown("")
    device = st.selectbox(
        "设备选择",
        asr_settings.get_labels("device"),
        index=asr_settings.get_index("device"),
        key="device",
    )
    ffmpeg_path = st.text_input(
        get_setting_title("FFMPEG_PATH", ASRSettings),
        value=ffmpeg_path,
        placeholder="FFMPEG Path",
        key="ffmpeg_path",
    )
    asr_model_provider = st.selectbox(
        get_setting_title("asr_model_provider", ASRSettings),
        asr_settings.get_labels("asr_model_provider"),
        index=asr_settings.get_index("asr_model_provider"),
    )
    st.caption("Qwen3-ASR 现在通过独立端点按模型调用，Sherpa-ONNX 保留为轻量 fallback。")
    if st.toggle("自定义输出目录", custom_output_dir, key="custom_output_dir"):
        output_dir = st.text_input(
            get_setting_title("output_dir", ASRSettings),
            value=output_dir,
            placeholder="Output Directory",
            key="output_dir",
        )
        cache_dir = st.text_input(
            get_setting_title("cache_dir", ASRSettings),
            value=cache_dir,
            placeholder="Cache Directory",
            key="cache_dir",
        )
    st.caption("默认输出目录与输入文件相邻；启用后会写入指定目录下的 `audio/` 与 `video/`。")
    st.markdown("")

    st.markdown("###### Sherpa-ONNX 配置")
    st.caption("Sherpa 代码保留，用于 fallback 与 VAD。")
    asr_model_dir = st.text_input(
        get_setting_title("asr_model_dir", SherpaASRSettings),
        value=asr_model_dir,
        placeholder="ASR Model Directory",
        key="asr_model_dir",
    )
    vad_model_path = st.text_input(
        get_setting_title("vad_model_path", ASRSettings),
        value=vad_model_path,
        placeholder="VAD Model Path",
        key="vad_model_path",
    )
    num_threads = st.number_input(
        get_setting_title("num_threads", SherpaASRSettings),
        value=num_threads,
        min_value=1,
        step=1,
        key="num_threads",
    )
    st.markdown("")

    st.markdown("###### Qwen3-ASR 配置")
    st.caption(
        "模型通过 `just install-qwen-asr` 下载到本地 `./models/`，显式端点按模型懒加载；`preload_models` 只控制启动预热。"
    )
    qwen_model_dir = st.text_input(
        get_setting_title("model_dir", QwenASRSettings),
        value=qwen_model_dir,
        placeholder="./models",
        key="qwen_model_dir",
    )
    qwen_preload_models = cast(
        "list[QwenASRModelName]",
        st.multiselect(
            get_setting_title("preload_models", QwenASRSettings),
            options=["0.6b", "1.7b"],
            default=qwen_preload_models,
            key="qwen_preload_models",
        ),
    )
    qwen_model_0_6b_path = st.text_input(
        get_setting_title("model_0_6b_path", QwenASRSettings),
        value=qwen_model_0_6b_path,
        placeholder="./models/Qwen3-ASR-0.6B-INT8-OpenVINO",
        key="qwen_model_0_6b_path",
    )
    qwen_model_1_7b_path = st.text_input(
        get_setting_title("model_1_7b_path", QwenASRSettings),
        value=qwen_model_1_7b_path,
        placeholder="./models/Qwen3-ASR-1.7B-INT8-OpenVINO",
        key="qwen_model_1_7b_path",
    )
    qwen_device = st.selectbox(
        get_setting_title("device", QwenASRSettings),
        options=["CPU"],
        index=0,
        key="qwen_device",
    )
    qwen_cpu_threads = st.number_input(
        get_setting_title("cpu_threads", QwenASRSettings),
        value=int(qwen_cpu_threads),
        min_value=0,
        step=1,
        key="qwen_cpu_threads",
    )
    if lab_settings.package.qwen_asr and not qwen_preload_models:
        st.warning("当前已启用 Qwen3-ASR 服务，但没有选择任何预加载模型。服务仍可按模型端点懒加载。")
    st.markdown("")

with save_container:
    col1, col2 = st.columns([0.75, 0.25])
    with col2:
        st.markdown("")
        st.markdown("")
        if st.button("**保存更改**", type="primary", use_container_width=True):
            initial_settings: GlobalSettings = st.session_state[setting_keys["initial_settings"]]
            current_settings: GlobalSettings = {
                "basic": {
                    "device": device,
                    "custom_output_dir": custom_output_dir,
                    "ffmpeg_path": ffmpeg_path or initial_settings["basic"]["ffmpeg_path"],
                    "cache_dir": cache_dir or initial_settings["basic"]["cache_dir"],
                    "output_dir": output_dir or initial_settings["basic"]["output_dir"],
                    "vad_model_path": vad_model_path or initial_settings["basic"]["vad_model_path"],
                    "asr_model_provider": asr_model_provider,
                },
                "sherpa": {
                    "asr_model_dir": asr_model_dir or initial_settings["sherpa"]["asr_model_dir"],
                    "num_threads": int(num_threads),
                },
                "qwen_asr": {
                    "model_dir": qwen_model_dir or initial_settings["qwen_asr"]["model_dir"],
                    "preload_models": list(qwen_preload_models),
                    "model_0_6b_path": qwen_model_0_6b_path or initial_settings["qwen_asr"]["model_0_6b_path"],
                    "model_1_7b_path": qwen_model_1_7b_path or initial_settings["qwen_asr"]["model_1_7b_path"],
                    "device": qwen_device,
                    "cpu_threads": int(qwen_cpu_threads),
                },
            }

            if current_settings != initial_settings:
                selected_provider = current_settings["basic"]["asr_model_provider"]
                if selected_provider == ASRModelProvider.sherpa.value and not lab_settings.package.sherpa_asr:
                    message_box(
                        "保存失败",
                        "当前已选择 Sherpa-ONNX 作为 ASR provider，但 [package].sherpa_asr 仍为 false。请先启用 Sherpa ASR 服务。",
                    )
                    st.stop()

                if selected_provider == ASRModelProvider.qwen.value and not lab_settings.package.qwen_asr:
                    message_box(
                        "保存失败",
                        "当前已选择 Qwen3-ASR 作为 ASR provider，但 [package].qwen_asr 仍为 false。请先启用 Qwen3-ASR 服务。",
                    )
                    st.stop()

                if not check_device_is_available(current_settings["basic"]["device"]):
                    message_box("保存失败", "当前设备不可用，请检查配置。")
                    st.stop()

                asr_settings.set_by_label("device", device)
                asr_settings.custom_output_dir = current_settings["basic"]["custom_output_dir"]
                asr_settings.FFMPEG_PATH = current_settings["basic"]["ffmpeg_path"]
                asr_settings.cache_dir = current_settings["basic"]["cache_dir"]
                asr_settings.output_dir = current_settings["basic"]["output_dir"]
                asr_settings.vad_model_path = current_settings["basic"]["vad_model_path"]
                asr_settings.set_by_label("asr_model_provider", current_settings["basic"]["asr_model_provider"])

                sherpa_settings.asr_model_dir = current_settings["sherpa"]["asr_model_dir"]
                sherpa_settings.num_threads = current_settings["sherpa"]["num_threads"]

                qwen_settings.model_dir = current_settings["qwen_asr"]["model_dir"]
                qwen_settings.preload_models = current_settings["qwen_asr"]["preload_models"]
                qwen_settings.model_0_6b_path = current_settings["qwen_asr"]["model_0_6b_path"]
                qwen_settings.model_1_7b_path = current_settings["qwen_asr"]["model_1_7b_path"]
                qwen_settings.device = current_settings["qwen_asr"]["device"]
                qwen_settings.cpu_threads = current_settings["qwen_asr"]["cpu_threads"]

                asr_settings.sherpa = sherpa_settings
                asr_settings.qwen_asr = qwen_settings
                lab_settings.asr = asr_settings

                write_settings_file(settings_name="lab.toml", settings=lab_settings)

                if (
                    current_settings["basic"]["device"] != initial_settings["basic"]["device"]
                    or current_settings["basic"]["asr_model_provider"]
                    != initial_settings["basic"]["asr_model_provider"]
                    or current_settings["sherpa"] != initial_settings["sherpa"]
                    or current_settings["qwen_asr"] != initial_settings["qwen_asr"]
                ):
                    reload_client = ReloadClient("asr")
                    st.toast("正在重新加载 ASR 引擎，请稍候...")
                    reload_client.post()

                st.session_state[setting_keys["initial_settings"]] = current_settings
                message_box("保存成功", "也可以直接修改 `config/lab.toml` 调整配置。")
            else:
                message_box("未检测到更改", "配置未发生变化，无需保存。")

        if st.button("**恢复默认设置**", type="secondary", use_container_width=True):
            asr_setting_path = Path("config") / "asr.toml"
            if asr_setting_path.exists():
                asr_setting_path.unlink()
            reset_asr_settings = load_settings_file("asr.toml", ASRSettings)
            lab_settings.asr = reset_asr_settings
            if asr_setting_path.exists():
                asr_setting_path.unlink()
            write_settings_file("lab.toml", lab_settings)
            reload_client = ReloadClient("asr")
            st.toast("正在重新加载 ASR 引擎，请稍候...")
            reload_client.post()
            message_box("恢复成功", "配置已恢复为默认设置，刷新页面即可查看更改。")

    with col1:
        st.markdown("")
        st.markdown("")
        st.markdown("### 设置")
        st.caption("Settings")
        st.markdown("")
