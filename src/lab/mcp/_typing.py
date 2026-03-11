from __future__ import annotations

from typing import Annotated, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator, model_validator

from lab.mcp.util import normalize_jsonlike

# =============================================================================
# 1) OpenAI tool calling：最小 Protocol（SDK 边界）
# =============================================================================


class _FnLike(Protocol):
    name: str
    arguments: str | None


class ToolCallLike(Protocol):
    id: str
    function: _FnLike


# =============================================================================
# 2) 我们自己构造的 message / trace（IDE 可补全）
# =============================================================================


class TextPart(BaseModel):
    type: Literal["text"]
    text: str
    model_config = ConfigDict(extra="forbid")


class ImageURL(BaseModel):
    url: str
    detail: Literal["auto", "low", "high"] = "auto"
    model_config = ConfigDict(extra="forbid")


class ImagePart(BaseModel):
    type: Literal["image_url"]
    image_url: ImageURL
    model_config = ConfigDict(extra="forbid")


class InputAudio(BaseModel):
    data: str
    format: Literal["wav", "mp3"]
    model_config = ConfigDict(extra="forbid")


class AudioPart(BaseModel):
    type: Literal["input_audio"]
    input_audio: InputAudio
    model_config = ConfigDict(extra="forbid")


class FileObj(BaseModel):
    file_data: str | None = None
    file_id: str | None = None
    filename: str | None = None
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _check(self):
        if not (self.file_data or self.file_id):
            raise ValueError("file must include file_data or file_id")
        return self


class FilePart(BaseModel):
    type: Literal["file"]
    file: FileObj
    model_config = ConfigDict(extra="forbid")


ContentPart = Annotated[
    TextPart | ImagePart | AudioPart | FilePart,
    Field(discriminator="type"),
]

OpenAIContent = str | list[ContentPart]


class SystemMsg(BaseModel):
    role: Literal["system"]
    content: OpenAIContent
    tool_call_id: None = None
    model_config = ConfigDict(extra="forbid")


class UserMsg(BaseModel):
    role: Literal["user"]
    content: OpenAIContent
    tool_call_id: None = None
    model_config = ConfigDict(extra="forbid")


class AssistantMsg(BaseModel):
    role: Literal["assistant"]
    # 如果你不支持 assistant 的 tool_calls，就把它改成 `content: Content`
    content: OpenAIContent | None = None
    tool_call_id: None = None
    model_config = ConfigDict(extra="forbid")


class ToolMsg(BaseModel):
    role: Literal["tool"]
    content: str
    tool_call_id: str  # tool 必填
    model_config = ConfigDict(extra="forbid")


class ToolFunction(BaseModel):
    name: str
    arguments: str  # OpenAI 返回是 JSON 字符串
    model_config = ConfigDict(extra="forbid")


class ToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: ToolFunction
    model_config = ConfigDict(extra="forbid")


class OpenAIMessage(BaseModel):
    role: Literal["developer", "system", "user", "assistant", "tool"]
    content: OpenAIContent | None = None

    # tool role 使用
    tool_call_id: str | None = None

    # assistant role 可能返回
    tool_calls: list[ToolCall] | None = None
    annotations: list[Any] | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _check(self):
        # tool message：必须 tool_call_id + content(str)
        if self.role == "tool":
            if not self.tool_call_id:
                raise ValueError("tool message must include tool_call_id")
            if not isinstance(self.content, str):
                raise ValueError("tool message content must be str")
            if self.tool_calls is not None:
                raise ValueError("tool message must not include tool_calls")
            return self

        # 非 tool：不允许 tool_call_id
        if self.tool_call_id is not None:
            raise ValueError("tool_call_id is only allowed for role='tool'")

        # assistant：content 可以为空，但必须有 content 或 tool_calls 之一
        if self.role == "assistant":
            if (self.content is None or (isinstance(self.content, str) and not self.content)) and not self.tool_calls:
                raise ValueError("assistant message must include content or tool_calls")
            return self

        # system/user/developer：一般要求 content 非空（你可以按需放宽）
        if self.role in ("system", "user", "developer") and self.content is None:
            raise ValueError(f"{self.role} message must include content")

        # 其他 role 不应带 tool_calls
        if self.tool_calls is not None:
            raise ValueError("tool_calls is only allowed for role='assistant'")

        return self

    def to_openai_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role}

        # content 可以是 None / str / parts
        if self.content is None:
            d["content"] = None
        elif isinstance(self.content, str):
            d["content"] = self.content
        else:
            d["content"] = [p.model_dump(mode="json") for p in self.content]

        # tool role 需要 tool_call_id
        if self.role == "tool":
            d["tool_call_id"] = self.tool_call_id

        # assistant role 可能需要 tool_calls
        if self.role == "assistant" and getattr(self, "tool_calls", None):
            d["tool_calls"] = [tc.model_dump(mode="json") for tc in self.tool_calls]  # type: ignore[attr-defined]

        # annotations 通常不需要传回 OpenAI，除非你自己要
        return d


class ToolTraceItem(BaseModel):
    """
    给 Chat Model 的工具调用摘要（结构化）。

    注意：为了让 Chat Model 更好地“口语化 + TTS友好”，建议保留：
    - raw_result：原始结果（可用于精确计算）
    - display_hint：你希望 Chat Model 展示/口语化的方向（可选）

    示例：
        {
          "server":"timeemi",
          "name":"get_date_and_time",
          "args":{},
          "raw_result":{"datetime":"2026-01-27 20:54:37"},
          "ok": true
        }
    """

    server: str
    name: str
    args: dict[str, object] = Field(default_factory=dict)
    raw_result: dict[str, object] = Field(default_factory=dict)
    ok: bool = True
    error: str | None = None


class ImageRefResult(BaseModel):
    """
    用于 ToolTraceItem.raw_result 的“图像引用结果”。
    大 payload（base64）不进 messages，只进 blob_store。
    """

    kind: Literal["image_ref"] = "image_ref"
    image_ref: str = Field(..., min_length=1)
    mime: str = Field(default="image/jpeg", min_length=3)
    b64_len: int = Field(..., ge=0)


# =============================================================================
# 3) 已知工具：Args / Result（pydantic 强校验）
# =============================================================================
class RollDiceArgs(BaseModel):
    """
    timeemi.roll_dice 入参。

    输入示例：
        {"n_dice": 3}
    """

    model_config = ConfigDict(extra="forbid")
    n_dice: int = Field(..., ge=1, le=50, description="骰子数量（建议限制，防止滥用）")


class RollDiceResult(BaseModel):
    """
    timeemi.roll_dice 输出。

    输出示例：
        {"numbers": [5, 3, 1]}
    """

    numbers: list[int]

    @field_validator("numbers")
    @classmethod
    def _check_range(cls, v: list[int]) -> list[int]:
        for x in v:
            if x < 1 or x > 6:
                raise ValueError(f"dice out of range: {x}")
        return v


class RollDiceByTimeArgs(BaseModel):
    """
    timeemi.roll_dice_by_current_time 入参。

    输入示例：
        {"unit": "hour"}
    """

    unit: Literal["hour", "minute", "second"] = Field(..., description="使用的时间单位")


class RollDiceByTimeResult(BaseModel):
    """
    timeemi.roll_dice_by_current_time 输出。

    输出示例：
    {
      "unit": "hour",
      "now": "2026-01-28 09:57:19",
      "n_dice": 9,
      "numbers": [4, 1, 4, 6, 3, 2, 5, 1, 6]
    }
    """

    unit: Literal["hour", "minute", "second"] = Field(..., description="使用的时间单位")
    now: str = Field(..., description="服务器当前时间，格式 YYYY-MM-DD HH:MM:SS")
    n_dice: int = Field(..., description="最终掷骰子的数量（>=1）")
    numbers: list[int] = Field(..., description="掷骰结果列表")

    @field_validator("numbers")
    @classmethod
    def _check_range(cls, v: list[int]) -> list[int]:
        for x in v:
            if x < 1 or x > 6:
                raise ValueError(f"dice out of range: {x}")
        return v


class ScreenShotResult(BaseModel):
    """
    vision.screen_shot 输出。
    返回当前屏幕截图的 base64 编码图像数据（通常为 PNG 或 JPEG）。
    输出示例：
        {
            "image_b64": "iVBORw0KGgoAAAANSUhEUgAA..."
        }
    """

    image_b64: str = Field(
        ...,
        description="当前屏幕截图的 base64 编码图像数据（通常为 PNG 或 JPEG）",
    )


class UnknownArgs(RootModel[dict[str, object]]):
    """未知工具入参：原样透传 dict，不包一层 data。
    留待扩展
    """

    pass


class UnknownResult(BaseModel):
    """
    未知工具输出（扩展点）。
    - data 会被尽量归一化成 JSON-like（dict/list/str/int/bool/None）
    - 遇到真的很怪的对象，退化成 repr，保证不会在 trace/dump 阶段炸
    """

    data: object | None = Field(default=None)

    @field_validator("data", mode="before")
    @classmethod
    def _normalize(cls, v: object) -> object:
        nv = normalize_jsonlike(v)
        # normalize 后如果还是不可控的 exotic 对象，就 repr 保底（只针对 Unknown）
        if nv is None or isinstance(nv, (dict, list, str, int, float, bool)):
            return nv  # type: ignore
        return repr(nv)


# -----------------------------
# Message schema (宽松校验)
# -----------------------------
Role = Literal["system", "user", "assistant", "tool"]


class TolerantOpenAIChatMessage(BaseModel):
    """
    宽松版 OpenAI message 校验：
    - role 必须是合法值
    - content 允许 str 或 list（多模态）或其他（我们会 best-effort 转文字）
    - extra 字段允许（比如 tool_call_id / name / tool_calls / etc）
    """

    model_config = ConfigDict(extra="allow")

    role: Role
    content: Any = ""


# -----------------------------
# Conversation pinned state
# -----------------------------
class ConversationState(BaseModel):
    """
    ConversationState = “pinned / structured memory” for Tool Model.

    目标
    - 给 Tool Model 提供一份稳定、结构化、可控长度的“记忆与锚点”，用于：
      1) 指代消解（“上一个链接/刚才那张图/那个文件/继续”）
      2) 缺参补全（用户省略 URL/path 或复用上一次 image_ref）
      3) 多轮任务约束（用户选项、偏好、已确认条件）
      4) 可选：滚动摘要 summary（当上下文很长时替代历史全文）

    重要：这个 state 本身不会“自动生效”
    - state 只有在你把 `to_tool_pinned_json()` 注入到 tool model 的 messages 里时，Tool Model 才“看得到”。
    - state 也不会自动更新：需要你在每轮对话/工具返回后，调用 updater 逻辑写入 refs/slots/summary/active_task。

    字段说明
    - user_prefs:
        长期偏好（语言、风格、单位、禁用/偏好工具等），适合跨任务复用。
    - active_task:
        当前任务类型标记（如 "web" / "image" / "file" / "time"），用于帮助 Tool Model 做策略选择与复用策略。
        注意：它只是提示信号；需要你在 tool prompt 中明确写“如何用 active_task”才会真正提升稳定性。
    - refs:
        “可复用实体”的引用与元信息，用于指代消解与复用。
        推荐约定键（你可以按需扩展）：
          * last_url: 最近一次被提及/尝试的 URL（不一定成功）
          * last_url_ok: 最近一次成功抓取且内容非空的 URL（强烈建议优先使用它）
          * last_url_failed / last_url_failed_status: 最近一次失败的 URL 与状态（避免重复撞墙）
          * last_file: 最近一次被读取/被用户提及的文件路径
          * last_image_ref: 最近一次截图/图像工具返回的 image_ref（避免重复截图）
          * last_image_mime / last_image_b64_len: 图像元信息（用于调试/策略）
        关键工程规则（强烈建议）：
          - “失败的 web_fetch 不要覆盖 last_url_ok”，否则会污染后续“上一个链接”的解析。
          - 用户说“刚才那张截图”时默认复用 last_image_ref，除非用户明确要求“重新截图/现在截图”。

    - slots:
        与当前任务强相关的结构化槽位（本轮/近期有效），例如：
          * last_user_text: 上一条用户输入（用于一些弱消歧/回显）
          * choice_index / selected_item / constraints: 用户选了第几个、选择了哪项、有哪些约束
        slots 适合短期、任务内变量；不建议塞长期偏好（放到 user_prefs）。

    - summary:
        “滚动摘要”，用于在长对话时替代历史全文，降低 tool model 上下文开销。
        注意：本字段不会自动生成；需要你实现一个 summarizer（可由 chat model 或 tool model 生成）并写回。
        本类 validator 仅做长度上限保护（避免 pinned state 失控膨胀）。

    输出
    - to_tool_pinned_json():
        返回“注入给 tool model 的 JSON”（会再截断保护长度）。
        典型用法：作为一条固定的 user/system 消息注入 tool loop 的最前部，或紧跟 system prompt 之后。
    """

    model_config = ConfigDict(extra="forbid")

    user_prefs: dict[str, Any] = Field(default_factory=dict)
    active_task: str | None = None
    refs: dict[str, Any] = Field(default_factory=dict)
    slots: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""

    @field_validator("summary")
    @classmethod
    def _summary_not_too_long(cls, v: str) -> str:
        # 这里不是硬限制 token，只做一个上限保护，避免 pinned 爆炸
        v = (v or "").strip()
        return v[:4000]

    def to_tool_pinned_json(self) -> dict[str, Any]:
        # 给 tool routing 用的 pinned JSON（再截一层，保证更短）
        return {
            "user_prefs": self.user_prefs,
            "active_task": self.active_task,
            "refs": self.refs,
            "slots": self.slots,
            "summary": (self.summary or "")[:1000],
        }
