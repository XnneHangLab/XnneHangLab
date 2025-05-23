from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lab._typing import Sentence, Word

# ====
# 根据 combine_line 把间隔较短的两个句子合并成一个句子
# 建议和 cut_line 之间打开一个即可，如果同时打开，需要 combine_line>cut_line 否则会取消所有 cut_line 的效果
# ====


# 做的事情和 cutter 相反，根据 combine_line 把间隔较短的两个句子合并成一个句子
# 需要考虑连续 combine 的情况,即经过一次合并后，这个新句子可能依然需要和下一个句子合并
# 所以我们考虑的实现路径是这样的: 从左到右边，一次性找出连续的并且需要合并的句子，然后合并。
# combine_sentence_lists = [[0,1,2],[3],[4,5]] 这样
# 这代表了六个句子会被合并成三个句子


def count_new_sentences_word_length(sentences: list[Sentence], new_sentence: Sentence) -> int:
    length = 0
    for sentence in sentences:
        length += len(sentence["Words"])
    length += len(new_sentence["Words"])
    return length


def combine_sentences(sentences: list[Sentence], combine_line: int, max_sentence_length: int):
    new_sentences: list[Sentence] = []

    combine_sentence_lists: list[list[Sentence]] = []
    combine_sentence_list: list[Sentence] = []

    latest_end = 0

    for sentence in sentences:
        if latest_end == 0:
            combine_sentence_list.append(sentence)
            latest_end = sentence["end"]
        else:
            if (
                sentence["start"] - latest_end < combine_line
                and count_new_sentences_word_length(combine_sentence_list, sentence) < max_sentence_length
            ):
                combine_sentence_list.append(sentence)
                latest_end = sentence["end"]
            else:
                combine_sentence_lists.append(combine_sentence_list)
                combine_sentence_list = [sentence]
                latest_end = sentence["end"]

        if sentence == sentences[-1]:
            combine_sentence_lists.append(combine_sentence_list)

    sentence_num = 0
    for combine_sentence_list in combine_sentence_lists:
        for _sentence in combine_sentence_list:
            sentence_num += 1
    assert sentence_num == len(sentences), "合并中句子存在遗漏"

    for combine_sentence_list in combine_sentence_lists:
        new_texts = ""
        new_words: list[Word] = []
        for sentence in combine_sentence_list:
            new_texts += " " + sentence["text"]
            new_words += sentence["Words"]

        new_start = combine_sentence_list[0]["start"]
        new_end = combine_sentence_list[-1]["end"]
        new_sentence: Sentence = {
            "text": new_texts,
            "start": new_start,
            "end": new_end,
            "Words": new_words,
        }
        new_sentences.append(new_sentence)

    return new_sentences
