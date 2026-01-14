from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, overload

from modelscope.pipelines import pipeline  # type: ignore[reportCallIssue]
from modelscope.utils.constant import Tasks

from lab.config_manager import XnneHangLabSettings, load_settings_file

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

    from lab.agent.memory._typing import (
        SentenceEmbeddingCompareInput,
        SentenceEmbeddingCompareResponse,
        SentenceEmbeddingInput,
        SentenceEmbeddingResponse,
    )

lab_settings: XnneHangLabSettings = load_settings_file("lab.toml", XnneHangLabSettings)


# maxsize=1 保证了 pipeline 只会初始化一次，之后都会直接返回缓存的对象
# TODO 存在的隐患，如果 lab_settings 被修改，比如切换了使用了 embedding_model，但这里会延用第一次初始化的时候的 cache，所以真正多模型切换的时候还得做模型卸载。暂时不这么做。
@lru_cache(maxsize=1)
def get_embedding_pipeline():
    return pipeline(Tasks.sentence_embedding, model=lab_settings.agent.memory.embedding_model_path, sequence_length=100)


@overload
def embedding_model(input: SentenceEmbeddingCompareInput) -> SentenceEmbeddingCompareResponse: ...


@overload
def embedding_model(input: SentenceEmbeddingInput) -> SentenceEmbeddingResponse: ...


def embedding_model(
    input: SentenceEmbeddingInput | SentenceEmbeddingCompareInput,
) -> SentenceEmbeddingResponse | SentenceEmbeddingCompareResponse:
    pipeline_instance = get_embedding_pipeline()
    return pipeline_instance(input=input)  # type: ignore[reportCallIssue]


def t2vect(text: list[str]) -> NDArray[np.float32]:
    return embedding_model(input={"source_sentence": text})["text_embedding"]  # type: ignore[reportCallIssue]


# Test Case
# uv run pytest tests/test_nlp_gte_sentence_embedding.py -vvv -s


# TODO
# 实际上这个无约束的 embedding 是非常操蛋的,它不利于后续的规范化和拓展.
# 应该做的是增加一个中间层,按照一定规则约束 embedding 的输入和输出.这样有利于后续新增其他的 embedding 模型.毕竟这个模型似乎只能处理中文.
