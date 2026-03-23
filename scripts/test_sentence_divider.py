from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from lab.agent.output_types import AudioOutput
from lab.utils.sentence_divider import SentenceDivider, segment_full

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence


@dataclass(frozen=True)
class FullCase:
    name: str
    text: str
    expected: list[str]
    segment_method: str = "pysbd"
    max_sentence_len: int = 100


@dataclass(frozen=True)
class StreamCase:
    name: str
    chunks: list[str]
    expected: list[str]
    segment_method: str = "pysbd"


FULL_CASES: list[FullCase] = [
    FullCase(
        name="文件名不误切分",
        text="Read test.txt and report back.",
        expected=["Read test.txt and report back."],
        segment_method="regex",
    ),
    FullCase(
        name="版本号不误切分",
        text="Use v1.2.3 today. Ship tomorrow.",
        expected=["Use v1.2.3 today.", "Ship tomorrow."],
    ),
    FullCase(
        name="编号列表不误切分",
        text="1. Check file. 2. Read content.",
        expected=["1. Check file.", "2. Read content."],
        segment_method="regex",
    ),
    FullCase(
        name="中文文件名不误切分",
        text="读取 test.txt 后告诉我结果。然后继续检查日志。",
        expected=["读取 test.txt 后告诉我结果。", "然后继续检查日志。"],
    ),
    FullCase(
        name="中文版本号不误切分",
        text="当前版本是 v1.2.3，请先不要升级。等我确认后再说。",
        expected=["当前版本是 v1.2.3，请先不要升级。", "等我确认后再说。"],
    ),
    FullCase(
        name="中文博客段落分句",
        text="## 更新记录\n今天终于把分句器接上了。现在 Full 模式会先清洗全文，再按段落分句。\n\nStreaming 模式不再急着逐字吐出，而是尽量攒到两句再发。这样整体稳定很多。",
        expected=[
            "更新记录 今天终于把分句器接上了。",
            "现在 Full 模式会先清洗全文，再按段落分句。",
            "Streaming 模式不再急着逐字吐出，而是尽量攒到两句再发。",
            "这样整体稳定很多。",
        ],
    ),
    FullCase(
        name="中文小说对白分句",
        text="“先别急。”她看了我一眼，“等雨停了再走。”窗外的风还在响。",
        expected=[
            "“先别急。”她看了我一眼，“等雨停了再走。”",
            "窗外的风还在响。",
        ],
    ),
    FullCase(
        name="随机段落一",
        text="昨晚我本来只想改一个小 bug，结果一抬头已经两点了。窗外一直在下雨，键盘旁边那杯咖啡早就凉了，不过测试终于全绿，我反而一下子不困了。",
        expected=[
            "昨晚我本来只想改一个小 bug，结果一抬头已经两点了。",
            "窗外一直在下雨，键盘旁边那杯咖啡早就凉了，不过测试终于全绿，我反而一下子不困了。",
        ],
    ),
    FullCase(
        name="随机段落二",
        text="周六的地铁站人特别多。我站在扶梯旁边看了半天，最后还是决定走去公司。路上风很大，但是脑子反而慢慢清楚了，之前卡住的命名问题也突然顺了。",
        expected=[
            "周六的地铁站人特别多。",
            "我站在扶梯旁边看了半天，最后还是决定走去公司。",
            "路上风很大，但是脑子反而慢慢清楚了，之前卡住的命名问题也突然顺了。",
        ],
    ),
    FullCase(
        name="随机段落三",
        text="我把会议纪要重新读了一遍，发现真正需要先处理的只有两件事。第一件是把接口返回值补齐，第二件是把流式输出的边界条件补测，其他那些想优化的东西其实都可以后放。",
        expected=[
            "我把会议纪要重新读了一遍，发现真正需要先处理的只有两件事。",
            "第一件是把接口返回值补齐，第二件是把流式输出的边界条件补测，其他那些想优化的东西其实都可以后放。",
        ],
    ),
    FullCase(
        name="中英混合段落一",
        text="今天把 streaming divider 的 buffer 逻辑重新梳了一遍。结论很简单，Full path 必须是 single source of truth，不然规则迟早会 drift。",
        expected=[
            "今天把 streaming divider 的 buffer 逻辑重新梳了一遍。",
            "结论很简单，Full path 必须是 single source of truth，不然规则迟早会 drift。",
        ],
    ),
    FullCase(
        name="中英混合段落二",
        text="我上午先看了 PR，发现问题不在 model，而是在 prompt cleanup 之后的 display path。下午又补了两个 mixed-language case，现在 `test.txt`、v1.2.3 和中文对白基本都稳了。",
        expected=[
            "我上午先看了 PR，发现问题不在 model，而是在 prompt cleanup 之后的 display path。",
            "下午又补了两个 mixed-language case，现在 test.txt、v1.2.3 和中文对白基本都稳了。",
        ],
    ),
    FullCase(
        name="中英混合段落三",
        text="发布前我又手动过了一遍 web UI，结果比预期顺利。唯一有点尴尬的是 live stream 里偶尔会冒出像 嗯。 这种超短句，所以这次顺手把 TTS threshold 也落到 divider 里了。",
        expected=[
            "发布前我又手动过了一遍 web UI，结果比预期顺利。",
            "唯一有点尴尬的是 live stream 里偶尔会冒出像 嗯。",
            "这种超短句，所以这次顺手把 TTS threshold 也落到 divider 里了。",
        ],
    ),
    FullCase(
        name="长段落按句切分",
        text="# Weekly Notes\nThis is the first paragraph. It has two sentences.\n\nThe second paragraph keeps going without drama. It still ends cleanly.",
        expected=[
            "Weekly Notes This is the first paragraph.",
            "It has two sentences.",
            "The second paragraph keeps going without drama.",
            "It still ends cleanly.",
        ],
    ),
    FullCase(
        name="超长句二次切分",
        text="This sentence is intentionally quite long, with several clauses, and enough commas, to force a secondary split, while still reading naturally.",
        expected=[
            "This sentence is intentionally quite long,",
            "with several clauses, and enough commas,",
            "to force a secondary split,",
            "while still reading naturally.",
        ],
        segment_method="regex",
        max_sentence_len=40,
    ),
    FullCase(
        name="短语气句合并",
        text="欸。我刚刚看错了。然后继续。",
        expected=["欸。我刚刚看错了。然后继续。"],
        segment_method="regex",
    ),
    FullCase(
        name="短句按 TTS 阈值合并",
        text="我懂了。然后继续。",
        expected=["我懂了。然后继续。"],
        segment_method="regex",
    ),
]

STREAM_CASES: list[StreamCase] = [
    StreamCase(
        name="流式保留编号残句",
        chunks=[
            "[平静]1.",
            "根目录里已经有 `test.txt` 了，我刚才查过，不需要重新建。",
        ],
        expected=[
            "[平静]1.根目录里已经有 `test.txt` 了，我刚才查过，不需要重新建。",
        ],
    ),
    StreamCase(
        name="流式攒两句再吐",
        chunks=[
            "First sentence.",
            " Second sentence. Tail fragment",
        ],
        expected=[
            "First sentence.",
            "Second sentence.",
            "Tail fragment",
        ],
        segment_method="regex",
    ),
    StreamCase(
        name="中文流式攒两句再吐",
        chunks=[
            "第一句已经说完了。",
            " 第二句也完整了。尾巴还没说",
        ],
        expected=[
            "第一句已经说完了。",
            "第二句也完整了。",
            "尾巴还没说",
        ],
        segment_method="regex",
    ),
    StreamCase(
        name="中文流式保留版本号",
        chunks=[
            "当前是 v1.2.3 版本，",
            "先不要改配置。等我确认完再继续。",
        ],
        expected=[
            "当前是 v1.2.3 版本，先不要改配置。",
            "等我确认完再继续。",
        ],
    ),
    StreamCase(
        name="流式短语气句合并",
        chunks=[
            "欸。",
            "我刚刚看错了。然后继续。",
        ],
        expected=["欸。我刚刚看错了。然后继续。"],
        segment_method="regex",
    ),
]


def _format_result(parts: Sequence[str]) -> str:
    return "[" + ", ".join(parts) + "]"


async def _source(chunks: Sequence[str]) -> AsyncIterator[str]:
    for chunk in chunks:
        yield chunk


async def _run_stream_case(case: StreamCase) -> list[str]:
    divider = SentenceDivider(
        faster_first_response=False,
        segment_method=case.segment_method,
        valid_tags=["think", "tool"],
    )
    result: list[str] = []
    async for item in divider.process_stream(_source(case.chunks)):
        if isinstance(item, AudioOutput):
            continue
        result.append(item.text)
    return result


def _print_case(index: int, mode: str, name: str, source: str, result: Sequence[str], expected: Sequence[str]) -> bool:
    passed = list(result) == list(expected)
    status = "PASS" if passed else "FAIL"
    print(f"规则{index} [{mode}] {name} {status}")
    print(f"{source} -> {_format_result(result)}")
    if not passed:
        print(f"expected -> {_format_result(expected)}")
    print()
    return passed


def main() -> int:
    logger.disable("lab")
    failures = 0
    case_index = 1

    for case in FULL_CASES:
        result = segment_full(
            case.text,
            segment_method=case.segment_method,
            max_sentence_len=case.max_sentence_len,
        )
        if not _print_case(case_index, "full", case.name, case.text, result, case.expected):
            failures += 1
        case_index += 1

    for case in STREAM_CASES:
        result = asyncio.run(_run_stream_case(case))
        source = " + ".join(case.chunks)
        if not _print_case(case_index, "stream", case.name, source, result, case.expected):
            failures += 1
        case_index += 1

    return failures


if __name__ == "__main__":
    raise SystemExit(main())
