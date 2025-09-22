from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray


class SentenceEmbeddingCompareInput(TypedDict):
    source_sentence: list[
        str
    ]  # 建议 list 长度为 1, 即使函数接受一个 list[str]，但在比较时会将其视为一个整体进行处理，至于为什么请参见 SentenceEmbeddingCompareResponse 的说明
    sentences_to_compare: list[str]


class SentenceEmbeddingCompareResponse(TypedDict):
    text_embedding: NDArray[np.float32]  # 一个 [n_queries, dim] 的数组
    scores: list[float]  # 一个长度为 n_queries 的列表，包含每个查询与比较句子的相似度分数
    # Compare 逻辑就是 n_queries != 0 的与 == 0 的进行比较，在比较过程中。只有 n_queries_index = 0 的 Sentence 会被作为被比较句子。
    # 这时如果输入 source_sentence 是一个 list, 可能会出现 scores 的长度与 source_sentence 不一致的情况。
    # 因为 len(socres) always == len(source_sentence) + len(sentences_to_compare) - 1
    # 如果要比较多个句子，应该把它们合并到一个长度为 1 的 list[str]。


class SentenceEmbeddingInput(TypedDict):
    source_sentence: list[str]


class SentenceEmbeddingResponse(TypedDict):
    text_embedding: NDArray[np.float32]
