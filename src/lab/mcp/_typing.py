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


# -----------------------------
# Config with validation
# -----------------------------
# TODO Move to lab.toml
class ToolContextConfig(BaseModel):
    """
    ToolContextConfig = 控制“tool model 上下文构建策略”的配置。

    目标
    - 在“工具 schema + 思考空间 + pinned state + 上下文窗口”之间做预算分配，
      避免把 tool model 喂到很慢/很贵/注意力分散，同时保证在需要时能看见关键历史。

    重要：这个 config 不会自动生效
    - 只有当你实现并调用类似 `build_tool_context(...)` / `trim_to_budget(...)` 的逻辑时，
      这些字段才会真正影响 tool_loop_messages。
    - 如果你只是定义了 config 但仍然用“system + 最后一条 user_input”喂给 tool model，
      那这些参数几乎不会起作用。

    字段说明（建议实现时的使用方式）
    - tool_budget_tokens:
        tool model 输入的粗预算（保守值）。注意工具 schema/函数定义也会占用大量 token。
    - reserve_tokens:
        预留给工具 schema、工具调用协议、模型思考余量的预算；用于从 budget 中先扣掉。
        validator 保证 reserve_tokens < tool_budget_tokens。
    - min_window_tokens:
        给“最近上下文窗口”保底的最小预算，防止 pinned state 或其它内容把窗口挤没。
    - pinned_max_chars:
        pinned state 的字符上限（第二道保护），防止 state JSON 过大影响速度与稳定性。
    - recent_n_msgs:
        当需要历史上下文时，最多向前带多少条 message（user/assistant/tool 都算）。
        工程实现建议：
          1) 先拿最近 N 条作为候选窗口；
          2) 再根据 token 预算逐步裁剪（而不是死保 N 条）。
    - include_prev_assistant:
        处理“对/不是/第二个/同样/继续”等强依赖上一轮 assistant 的短输入时，
        尽量把“上一条 assistant”也纳入窗口，以提升指代/选择解析的稳定性。
        工程注意：
          - 永远对索引做 clamp：即使历史不足也不要越界（避免 list index out of range）。
          - 若上一条 assistant 是 tool_calls 产物，确保协议顺序仍然正确（不要把 user 插到 tool messages 中间）。

    推荐的上下文构建流程（实现提示）
    1) 固定注入 system_prompt（tool router prompt）
    2) 固定注入 pinned state（ConversationState.to_tool_pinned_json 的一条消息）
    3) 依据 user_text 判断是否 context-dependent：
         - 否：窗口可只保留最后 rememberable 的少量消息（甚至只保 last user）
         - 是：扩展到 recent_n_msgs，并按 include_prev_assistant 做补齐
    4) 按 tool_budget_tokens/reserve_tokens 做粗裁剪，必要时对窗口做缩短/摘要替代

    这套配置的价值
    - 在“总是全上下文（慢）”与“永远短上下文（容易跑偏）”之间提供可调的工程折中。
    """

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
