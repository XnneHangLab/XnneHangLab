from __future__ import annotations

import pytest

from lab.agent.memory.embedding import embedding_model


@pytest.mark.parametrize(
    "query, memorys, thresholds, expected_found",
    [
        ("测试消息22", ["测试消息2", "测试记忆2"], 0.5, True),
        ("今天天气真好", ["今天天气不错", "我喜欢下雨天"], 0.3, True),
        ("什么是机器学习", ["深度学习是机器学习的一个领域", "但是目前大部分人都只关注于深度学习."], 0.3, True),
        ("什么是深度学习", ["完全不相关的内容", "这是一个垃圾消息"], 0.5, False),
    ],
)
def test_embedding_model_with_thresholds(query: str, memorys: list[str], thresholds: float, expected_found: bool):
    input = {"source_sentence": [query], "sentences_to_compare": memorys}
    response = embedding_model(input=input)  # type: ignore[reportCallIssue]
    res_msg = ""
    found_num = 0
    for i in range(len(response["scores"])):  # type: ignore[reportCallIssue]
        if response["scores"][i] > thresholds:  # type: ignore[reportCallIssue]
            print(f"[提示]检索到相关记忆:{memorys[i]}，分数：{response['scores'][i]}")  # type: ignore[reportCallIssue]
            print(response)  # type: ignore[reportCallIssue]
            res_msg += str(memorys[i]) + "\n\n"
            found_num += 1
        else:
            print(f"[提示]未检索到相关记忆:{memorys[i]}，分数：{response['scores'][i]}")  # type: ignore[reportCallIssue]
    if expected_found:
        assert found_num > 0, "期望找到相关记忆，但是没有找到。"
    else:
        assert found_num == 0, f"期望没有找到相关记忆，但是找到 {found_num} 个。检索到的记忆：{res_msg}"
