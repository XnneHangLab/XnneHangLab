"""运行 Streamlit 应用前将当前项目的根目录绝对路径写入配置文件
因为 Streamlit 应用启动后，读取根目录绝对路径会默认变成 `.`, 无法访问 `packages`, 而 packages 存储了各自模块的 ui, 必须访问。
所以这里将根目录绝对路径写入配置文件 `root.toml` 中。在 Streamlit 启动前运行，然后供它全局使用。
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

# LLM


class LLMSettingBase(BaseModel):
    llm_api_key: Annotated[str, Field("", title="OpenAI API Key")]
    llm_base_url: Annotated[str, Field("", title="OpenAI API Base URL")]
    llm_model_name: Annotated[str, Field("", title="OpenAI Model Name")]


class LingyiSetting(LLMSettingBase):
    llm_base_url: Annotated[str, Field("https://api.lingyiwanwu.com/v1", title="Lingyi API Base URL")]
    llm_model_name: Annotated[str, Field("yi-lightning", title="Lingyi Model Name")]


class GeminiSetting(LLMSettingBase):
    llm_base_url: Annotated[
        str, Field("https://generativelanguage.googleapis.com/v1beta/openai/", title="Gemini API Base URL")
    ]
    llm_model_name: Annotated[str, Field("gemini-2.5-flash", title="Gemini Model Name")]


class OpenAISetting(LLMSettingBase):
    llm_base_url: Annotated[str, Field("https://api.openai.com/v1", title="ChatGPT API Base URL")]
    llm_model_name: Annotated[str, Field("gpt-4o", title="ChatGPT Model Name")]


class OAIPROSetting(LLMSettingBase):
    llm_model_name: Annotated[str, Field("gpt-5.1-2025-11-13", title="OAIPRO Model Name")]
    llm_base_url: Annotated[str, Field("https://api.oaipro.com/v1", title="OAIPRO API Base URL")]


class CerebrasSetting(LLMSettingBase):
    llm_base_url: Annotated[str, Field("https://api.cerebras.ai/v1", title="Cerebras API Base URL")]
    llm_model_name: Annotated[str, Field("llama-3.3-70b", title="Cerebras Model Name")]


# Long Term Memory


# 我们的长期记忆完全借用了 Moechat 的暴力 RAG 结合时序日记系统想法和做法: https://github.com/AlfreScarlet/MoeChat
class LongTermMemorySettings(BaseModel):
    embedding_model_path: Annotated[
        str, Field("./models/nlp_gte_sentence-embedding_chinese-base", title="Embedding Model Path")
    ]  # 目前只支持中文
    books_thresholds: Annotated[
        float, Field(0.5, title="Books Thresholds", description="知识库检索阈值。")
    ]  # 控制知识库搜索相似度的阈值参数， > 0.5 时才保留
    mem_thresholds: Annotated[
        float,
        Field(
            0.38,
            title="Memory Thresholds",
            description="日记内容搜索阈值，启用日志检索加强是需要，用于判断匹配程度。过高可能会丢失数据，过低则过滤少量无用记忆。",
        ),
    ]
    scan_depth: Annotated[
        int,
        Field(
            4,
            title="Scan Depth",
            description="知识库搜索深度，返回知识的数量，但相似度低于检索阈值的知识不会被返回，所以返回结果数量也可能小于设定的数值。",
        ),
    ]
    enable_check_memorys: Annotated[
        bool,
        Field(
            True,
            title="Enable Check Memorys",
            description="启用日记检索加强，使用嵌入模型对检索到的信息做提取，去除与用户提问不相关的内容。",
        ),
    ]
    enable_core_memmorys: Annotated[
        bool,
        Field(
            True,
            title="Enable Core Memorys",
            description="是否启用核心记忆功能，核心记忆主要储存关于用户重要信息，如：用户的住址、爱好、喜欢的东西等等。区别于日记，使用嵌入模型进行语义匹配（模糊搜索），不能根据时间检索，但记忆带有记录时间。。",
        ),
    ]
    lore_books: Annotated[
        bool,
        Field(
            True,
            title="Enable Lore Books",
            description="是否启用世界书（知识库），用于给大模型添加知识，如：人物、物品、事件等等，强化ai的能力，也可用于强化角色扮演。",
        ),
    ]


class LLMSettings(BaseModel):
    openai: Annotated[OpenAISetting, Field(OpenAISetting())]  # pyright: ignore[reportCallIssue]
    lingyi: Annotated[LingyiSetting, Field(LingyiSetting())]  # pyright: ignore[reportCallIssue]
    gemini: Annotated[GeminiSetting, Field(GeminiSetting())]  # pyright: ignore[reportCallIssue]
    oaipro: Annotated[OAIPROSetting, Field(OAIPROSetting())]  # pyright: ignore[reportCallIssue]
    cerebras: Annotated[CerebrasSetting, Field(CerebrasSetting())]  # pyright: ignore[reportCallIssue]


class AgentSettings(BaseModel):
    llm_provider: Annotated[
        Literal["openai", "lingyi", "gemini", "oaipro", "cerebras"], Field("oaipro", title="LLM Provider")
    ]
    enable_mcp: Annotated[bool, Field(True, title="Enable MCP")]
    llm: Annotated[LLMSettings, Field(LLMSettings())]  # pyright: ignore[reportCallIssue]
    character_name: Annotated[
        str,
        Field(
            "elaina",
            title="比如 elaina, paimeng, 等, 对应 ./prompts/characters/elaina.txt, ./prompts/characters/paimeng.txt 等",
        ),
    ]
    deeplx_api_key: Annotated[
        str,
        Field(
            "",
            title="DeepLX API Key, 用于跨语言对话时(user_lang != speaker lang)将大模型回复翻译成 speaker language 然后再合成语音",
        ),
    ]
    user_lang: Annotated[
        Literal["ZH", "EN", "JA"], Field("ZH", title="User Language, 用户使用的语言，也决定大模型回复的语言")
    ]
    speaker_lang: Annotated[
        Literal["ZH", "EN", "JA"], Field("EN", title="Speaker Language, speaker 合成语音时使用的语言")
    ]
    enable_longterm_memory: Annotated[bool, Field(True, title="Enable Long-term Memory")]
    memory: Annotated[LongTermMemorySettings, Field(LongTermMemorySettings())]  # pyright: ignore[reportCallIssue]
    speaker_model: Annotated[Literal["gpt_sovits"], Field("gpt_sovits", title="选择使用什么模型合成语音")]
    faster_first_response: Annotated[bool, Field(False, title="Enable Faster First Response")]
    segment_method: Literal["regex", "pysbd"] = Field(
        "pysbd",
        title="Segment Method",
        description="Method for segmenting text. 'regex' uses regex, 'pysbd' uses pysbd.",
    )
    interrupt_method: Literal["system", "user"] = Field(
        "user",
        title="Interrupt Method",
        description="Method for writing interruptions signal in chat history. 'system' uses system prompt, 'user' uses user input.",
    )


def main():
    from lab.config_manager.config import (
        XnneHangLabSettings,
        load_settings_file,
        search_for_settings_file,
        write_settings_file,
    )

    agent_settings_path = search_for_settings_file("agent.toml")
    if agent_settings_path is not None and agent_settings_path.exists():
        agent_settings_path.unlink()  # ensure load default
    agent_settings = load_settings_file("agent.toml", AgentSettings)
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    lab_settings.agent = agent_settings
    write_settings_file("lab.toml", lab_settings)
    agent_path = search_for_settings_file("agent.toml")
    if agent_path is not None and agent_path.exists():
        agent_path.unlink()  # remove agent.toml


if __name__ == "__main__":
    main()
