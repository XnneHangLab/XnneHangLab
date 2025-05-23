from __future__ import annotations

from typing import TYPE_CHECKING

from lab.BasicRunner.converter import rewrite_sentence_text_by_words

if TYPE_CHECKING:
    from lab._typing import CutPoint, Sentence, Word

# ====
# 根据 cut_line 把单个句子拆成多个句子，如果句子停顿时间超过 cut_line 。
# 可以用于调整字幕长度和速度。
# ====

# 卧槽，这比之前简洁了不止一点点。
# 拆分 Sentence 为 Word 果然是对的。


def cut_sentences(sentences: list[Sentence], cut_line: int):
    all_new_sentences: list[Sentence] = []

    for sentence_index, sentence in enumerate(sentences):
        latest_end = 0
        cut_points: list[CutPoint] = []
        new_text_lists: list[str] = []
        new_words_lists: list[list[Word]] = []

        for word_index, word in enumerate(sentence["Words"]):
            if (word["start"] - latest_end > cut_line) and (
                latest_end != 0
            ):  # 这一个字的开始时间 - 上一个字的结束时间 > cut_line
                cut_points.append({"sentence_index": sentence_index, "word_index": word_index})
            latest_end = word["end"]

        if cut_points == []:  # 无切分点
            new_sentence = sentence  # 无需变换
            all_new_sentences.append(new_sentence)

        else:
            for index, cut_point in enumerate(cut_points):  # 存在至少一个切分点，需要重组形成多个 Sentence
                if index == 0:  # 第一字句
                    new_words = sentence["Words"][: cut_point["word_index"]]
                    new_words_lists.append(new_words)
                elif index != 0 and index < len(cut_points):  ## 中间字句
                    new_words = sentence["Words"][cut_points[index - 1]["word_index"] : cut_point["word_index"]]
                    new_words_lists.append(new_words)

            # 最后字句,只要有切分，必然会有最后字句。就像一段木头被切两刀，会变成三段。
            new_words = sentence["Words"][cut_points[-1]["word_index"] :]
            new_words_lists.append(new_words)

            # 获取new texts
            for new_words in new_words_lists:
                texts = ""
                for word in new_words:
                    texts += " " + word["text"]

                new_text_lists.append(texts)

            # 生成new_sentences
            assert len(new_text_lists) == len(new_words_lists), (
                "生成句子时出现错误：句子列表长度和句子包含的单词列表数必须相同。"
                f"当前文本列表长度为 {len(new_text_lists)}，单词列表长度为 {len(new_words_lists)}。"
            )

            for text, words in zip(new_text_lists, new_words_lists, strict=True):
                new_sentence: Sentence = {
                    "text": text,
                    "start": words[0]["start"],
                    "end": words[-1]["end"],
                    "Words": words,
                }
                all_new_sentences.append(new_sentence)

    sentences = []
    for sentence in all_new_sentences:
        sentence["text"] = rewrite_sentence_text_by_words(sentence["Words"])
        sentences.append(sentence)

    return sentences
