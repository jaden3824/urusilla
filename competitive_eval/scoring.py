"""Deterministic answer metrics used by the public QA task harness."""

from __future__ import annotations

from collections import Counter
import re
import string
from typing import Any


_ARTICLES = re.compile(r"\b(a|an|the)\b", flags=re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


def normalize_answer(value: str) -> str:
    lowered = value.lower()
    without_punctuation = "".join(character for character in lowered if character not in string.punctuation)
    without_articles = _ARTICLES.sub(" ", without_punctuation)
    return _WHITESPACE.sub(" ", without_articles).strip()


def exact_match(prediction: str, gold: str) -> float:
    return float(normalize_answer(prediction) == normalize_answer(gold))


def token_f1(prediction: str, gold: str) -> float:
    predicted = normalize_answer(prediction).split()
    expected = normalize_answer(gold).split()
    if not predicted or not expected:
        return float(predicted == expected)
    overlap = Counter(predicted) & Counter(expected)
    common = sum(overlap.values())
    if common == 0:
        return 0.0
    precision = common / len(predicted)
    recall = common / len(expected)
    return 2 * precision * recall / (precision + recall)


def rouge_l(prediction: str, gold: str) -> float:
    predicted = normalize_answer(prediction).split()
    expected = normalize_answer(gold).split()
    if not predicted or not expected:
        return float(predicted == expected)
    previous = [0] * (len(expected) + 1)
    for left in predicted:
        current = [0]
        for index, right in enumerate(expected, start=1):
            if left == right:
                current.append(previous[index - 1] + 1)
            else:
                current.append(max(current[-1], previous[index]))
        previous = current
    lcs = previous[-1]
    precision = lcs / len(predicted)
    recall = lcs / len(expected)
    return 2 * precision * recall / (precision + recall)


def score_answer(prediction: str | None, gold: str) -> dict[str, Any]:
    if prediction is None:
        return {"normalized_exact_match": 0.0, "token_f1": 0.0, "rouge_l": 0.0}
    return {
        "normalized_exact_match": exact_match(prediction, gold),
        "token_f1": token_f1(prediction, gold),
        "rouge_l": rouge_l(prediction, gold),
    }

