from __future__ import annotations

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


# 加载embedding模型
def load_model():
    return pipeline(Tasks.sentence_embedding, model=lab_settings.agent.memory.embedding_model_path, sequence_length=100)


embedding_model_pipeline = load_model()


@overload
def embedding_model(input: SentenceEmbeddingCompareInput) -> SentenceEmbeddingCompareResponse: ...


@overload
def embedding_model(input: SentenceEmbeddingInput) -> SentenceEmbeddingResponse: ...


def embedding_model(
    input: SentenceEmbeddingInput | SentenceEmbeddingCompareInput,
) -> SentenceEmbeddingResponse | SentenceEmbeddingCompareResponse:
    return embedding_model_pipeline(input=input)  # type: ignore[reportCallIssue]


def t2vect(text: list[str]) -> NDArray[np.float32]:
    return embedding_model(input={"source_sentence": text})["text_embedding"]  # type: ignore[reportCallIssue]


def test(msg: str, memorys: list[str], thresholds: float):
    input = {"source_sentence": [msg], "sentences_to_compare": memorys}
    response = embedding_model(input=input)  # type: ignore[reportCallIssue]
    res_msg = ""
    for i in range(len(response["scores"])):  # type: ignore[reportCallIssue]
        if response["scores"][i] > thresholds:  # type: ignore[reportCallIssue]
            print(f"[提示]检索到相关记忆，分数：{response['scores'][i]}")  # type: ignore[reportCallIssue]
            print(response)  # type: ignore[reportCallIssue]
            res_msg += str(memorys[i]) + "\n\n"
    if res_msg:
        return res_msg


if __name__ == "__main__":
    print(test("测试消息22", ["测试消息2", "测试记忆2"], 0.5))
