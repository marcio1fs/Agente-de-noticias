"""Pronunciation-only transformations; never modify the published article."""
import re

_NUMERIC_X = re.compile(r"(?<![\w])(?P<left>\d+(?:[.,]\d+)?)\s*[xX×]\s*(?P<right>\d+(?:[.,]\d+)?)(?![\w])")
_DIGITS = {
    "0": "zero", "1": "um", "2": "dois", "3": "três", "4": "quatro",
    "5": "cinco", "6": "seis", "7": "sete", "8": "oito", "9": "nove",
    "12": "doze", "24": "vinte e quatro", "36": "trinta e seis", "48": "quarenta e oito",
}


_MONTHS = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro"
}

_NUM_WORDS = {
    0: "zero", 1: "um", 2: "dois", 3: "três", 4: "quatro", 5: "cinco",
    6: "seis", 7: "sete", 8: "oito", 9: "nove", 10: "dez", 11: "onze",
    12: "doze", 13: "treze", 14: "quatorze", 15: "quinze", 16: "dezesseis",
    17: "dezessete", 18: "dezoito", 19: "dezenove", 20: "vinte", 21: "vinte e um",
    22: "vinte e dois", 23: "vinte e três", 24: "vinte e quatro", 25: "vinte e cinco",
    26: "vinte e seis", 27: "vinte e sete", 28: "vinte e oito", 29: "vinte e nove",
    30: "trinta", 31: "trinta e um"
}

_TENS = {
    20: "vinte", 30: "trinta", 40: "quarenta", 50: "cinquenta",
    60: "sessenta", 70: "setenta", 80: "oitenta", 90: "noventa"
}


def _int_to_words(n: int) -> str:
    """Converte inteiros comuns de datas e anos para extenso em português."""
    if n in _NUM_WORDS:
        return _NUM_WORDS[n]
    if n < 100:
        t = (n // 10) * 10
        u = n % 10
        return f"{_TENS.get(t, str(t))} e {_NUM_WORDS.get(u, str(u))}" if u else _TENS.get(t, str(t))
    if 2000 <= n < 2100:
        remainder = n - 2000
        return f"dois mil e {_int_to_words(remainder)}" if remainder else "dois mil"
    return str(n)


# Regex para datas no formato DD/MM/AAAA ou DD-MM-AAAA ou DD/MM
_DATE_PATTERN = re.compile(r"\b(?P<day>0?[1-9]|[12][0-9]|3[01])[/\-\.](?P<month>0?[1-9]|1[0-2])(?:[/\-\.](?P<year>\d{4}))?\b")

# Regex para horas no formato 03:00 ou 15:30
_TIME_PATTERN = re.compile(r"\b(?P<hour>[01]?[0-9]|2[0-3]):(?P<minute>[0-5][0-9])\b")


def _replace_date(match: re.Match) -> str:
    d = int(match.group("day"))
    m = int(match.group("month"))
    y = int(match.group("year")) if match.group("year") else None

    # No Brasil, o primeiro dia do mês é tradicionalmente "primeiro" ou "um"
    day_str = "primeiro" if d == 1 else _int_to_words(d)
    month_str = _MONTHS.get(m, str(m))

    if y:
        return f"{day_str} de {month_str} de {_int_to_words(y)}"
    return f"{day_str} de {month_str}"


def _replace_time(match: re.Match) -> str:
    h = int(match.group("hour"))
    m = int(match.group("minute"))

    if h == 0 and m == 0:
        return "meia-noite"
    if h == 12 and m == 0:
        return "meio-dia"

    # Horas femininas ("uma hora", "duas horas", "três horas")
    hour_str = "uma" if h in (1, 13) else ("duas" if h in (2, 14) else _int_to_words(h))

    if m == 0:
        suffix = "hora" if h in (1, 13) else "horas"
        return f"{hour_str} {suffix}"
    return f"{hour_str} horas e {_int_to_words(m)} minutos"


def normalize_speech_text(text: str) -> str:
    """Read numeric 'x' as 'por', including 6x1, 5 X 2 and 12×36.

    A standalone X or X inside words/model names is not changed. Larger or
    decimal numbers remain numeric for the Portuguese speech engine to read.
    Preserves and formats punctuation (commas, periods, semicolons) to ensure
    the TTS engine renders distinct pauses and cadenced natural breathing.
    Converte datas (15/10/2026) e horários (03:00) em locução natural por extenso.
    """
    def replace_x(match):
        left, right = match.group("left", "right")
        return f"{_DIGITS.get(left, left)} por {_DIGITS.get(right, right)}"

    result = _NUMERIC_X.sub(replace_x, text)

    # 1. Converte datas (ex: 15/10/2026 -> quinze de outubro de dois mil e vinte e seis)
    result = _DATE_PATTERN.sub(_replace_date, result)

    # 2. Converte horários (ex: às 03:00 -> às três horas)
    result = _TIME_PATTERN.sub(_replace_time, result)

    # 3. Garante que haja espaço após vírgulas e pontos seguidos de letras maiúsculas ou início de frase
    result = re.sub(r"([,;:])(?=[A-Za-zÀ-ÿ])", r"\1 ", result)
    result = re.sub(r"([.!?]+)(?=[A-ZÀ-Ý])", r"\1 ", result)

    # 4. Retira pontos repetidos desnecessários mantendo pausas limpas
    result = re.sub(r"\.{2,}", "...", result)

    # 5. Retira espaços duplicados sem achatar a pontuação
    result = re.sub(r"[ \t]+", " ", result).strip()
    return result
