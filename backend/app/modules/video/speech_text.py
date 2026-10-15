"""Pronunciation-only transformations; never modify the published article."""
import re

_NUMERIC_X = re.compile(r"(?<![\w])(?P<left>\d+(?:[.,]\d+)?)\s*[xX×]\s*(?P<right>\d+(?:[.,]\d+)?)(?![\w])")
_DIGITS = {
    "0": "zero", "1": "um", "2": "dois", "3": "três", "4": "quatro",
    "5": "cinco", "6": "seis", "7": "sete", "8": "oito", "9": "nove",
    "12": "doze", "24": "vinte e quatro", "36": "trinta e seis", "48": "quarenta e oito",
}


def normalize_speech_text(text: str) -> str:
    """Read numeric 'x' as 'por', including 6x1, 5 X 2 and 12×36.

    A standalone X or X inside words/model names is not changed. Larger or
    decimal numbers remain numeric for the Portuguese speech engine to read.
    """
    def replace(match):
        left, right = match.group("left", "right")
        return f"{_DIGITS.get(left, left)} por {_DIGITS.get(right, right)}"
    return " ".join(_NUMERIC_X.sub(replace, text).split())
