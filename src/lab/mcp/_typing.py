from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, RootModel, field_validator

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


class OpenAIMessage(BaseModel):
    """
    我们自己构造的 OpenAI message。

    示例：
        {"role": "system", "content": "你是一个助手"}
        {"role": "user", "content": "现在几点？"}
        {"role": "tool", "content": "...", "tool_call_id": "call_xxx"}
    """

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_call_id: str | None = None


class ToolMessage(BaseModel):
    """
    OpenAI tool message：回填给 Tool Model。

    示例：
        {"role": "tool", "content": "2026-01-27 20:54:37", "tool_call_id": "call_xxx"}
    """

    role: Literal["tool"] = "tool"
    content: str
    tool_call_id: str


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
_TIME_RE = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"


class GetDateAndTimeArgs(BaseModel):
    """
    timeemi.get_date_and_time 入参（无参数）。

    输入示例：
        {}
    """

    model_config = ConfigDict(extra="forbid")


class GetDateAndTimeResult(BaseModel):
    """
    timeemi.get_date_and_time 输出。

    输出示例：
        {"datetime": "2026-01-27 20:54:37"}
    """

    datetime: str = Field(..., description="YYYY-MM-DD HH:MM:SS")

    @field_validator("datetime")
    @classmethod
    def _check_fmt(cls, v: str) -> str:
        import re

        vv = v.strip()
        if not re.match(_TIME_RE, vv):
            raise ValueError(f"bad datetime format: {v!r}")
        return vv


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


class ScreenShotArgs(BaseModel):
    """vision.screen_shot 入参（无参数）"""

    model_config = ConfigDict(extra="forbid")


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


# =============================================================================
# 4) Web/IO tools: Args / Result
# =============================================================================


WebSearchProvider = Literal["duckduckgo", "searxng", "tavily", "bochaai"]


class WebSearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, description="搜索关键词")
    max_results: int = Field(5, ge=1, le=10, description="返回结果数量")

    # ✅ 新增：严格 provider（不允许别名）
    provider: WebSearchProvider | None = Field(
        None,
        description="搜索引擎：duckduckgo / searxng / tavily / bochaai；为空则用服务端默认配置",
    )


class WebSearchResultItem(BaseModel):
    title: str
    url: AnyHttpUrl
    snippet: str | None = None


class WebSearchResult(BaseModel):
    query: str
    results: list[WebSearchResultItem]


class WebFetchArgs(BaseModel):
    """
    tool.web_fetch 入参。

    输入示例：
        {"url": "https://example.com", "max_chars": 8000}
    """

    model_config = ConfigDict(extra="forbid")
    url: AnyHttpUrl
    max_chars: int = Field(8000, ge=256, le=20000, description="最大返回字符数")
    timeout_s: float = Field(10.0, ge=1.0, le=30.0, description="请求超时秒数")


class WebFetchResult(BaseModel):
    url: AnyHttpUrl
    status_code: int
    content_type: str | None = None
    text: str
    truncated: bool = False


class ReadFileArgs(BaseModel):
    """
    tool.read_file 入参。

    输入示例：
        {"path": "README.md", "start_line": 1, "end_line": 200}
    """

    model_config = ConfigDict(extra="forbid")
    path: str = Field(..., min_length=1, description="相对路径或绝对路径")
    start_line: int | None = Field(None, ge=1, description="起始行")
    end_line: int | None = Field(None, ge=1, description="结束行")
    max_chars: int = Field(8000, ge=256, le=20000, description="最大返回字符数")


class ReadFileResult(BaseModel):
    path: str
    text: str
    truncated: bool = False
    start_line: int | None = None
    end_line: int | None = None
    total_lines: int | None = None


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
    Tool model 需要的“结构化记忆”：
    - refs：用于指代消解（last_url/last_file/last_image_ref 等）
    - slots：任务约束（用户选项、偏好、已确认条件等）
    - summary：滚动摘要（短！）
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


# -----------------------------
# Config with validation
# -----------------------------
# TODO Move to lab.toml
class ToolContextConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 粗估 token 预算（工具 schema + 思考也会占用，所以别给太满）
    tool_budget_tokens: int = Field(default=2200, ge=512, le=20000)

    # 需要扩展时，最多向前带多少条 message（user/assistant/tool 都算）
    recent_n_msgs: int = Field(default=10, ge=1, le=60)

    # 扩展时是否尽量保证带上“上一条 assistant”（对“对/不是/第二个”很关键）
    include_prev_assistant: bool = True

    # pinned state 最大字符数（保护上限）
    pinned_max_chars: int = Field(default=2400, ge=256, le=20000)

    # 预留 token 给工具 schema/模型思考（粗估）
    reserve_tokens: int = Field(default=350, ge=0, le=5000)

    # “窗口”最小保留预算（避免全被 pinned 吃掉）
    min_window_tokens: int = Field(default=200, ge=0, le=5000)

    @field_validator("reserve_tokens")
    @classmethod
    def _reserve_lt_budget(cls, v: int, info) -> int:  # type: ignore
        # 在 pydantic v2 里拿到同模型其它字段要用 info.data
        budget = int(info.data.get("tool_budget_tokens", 2200))  # type: ignore
        if v >= budget:
            raise ValueError(f"reserve_tokens({v}) must be < tool_budget_tokens({budget})")
        return v
