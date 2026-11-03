"""Input validation and normalisation for CNPJ and CEP values."""
import re

_CNPJ_RE = re.compile(r"^[0-9A-Z]{12}[0-9]{2}$")
_CNPJ_WEIGHTS = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]


def normalize_cnpj(raw: str) -> str:
    """Remove punctuation/spaces and upper-case: '00.000.000/0001-91' -> '00000000000191'."""
    return re.sub(r"[.\-/\s]", "", raw or "").upper()


def _check_digit(base: str) -> int:
    weights = _CNPJ_WEIGHTS[-len(base):]
    # Each character counts as (ASCII code - 48), so digits keep their value
    # and letters (alphanumeric CNPJ) are supported too.
    total = sum((ord(c) - 48) * w for c, w in zip(base, weights))
    rest = total % 11
    return 0 if rest < 2 else 11 - rest


def is_valid_cnpj(raw: str) -> bool:
    cnpj = normalize_cnpj(raw)
    if not _CNPJ_RE.match(cnpj) or len(set(cnpj)) == 1:
        return False
    d1 = _check_digit(cnpj[:12])
    d2 = _check_digit(cnpj[:12] + str(d1))
    return cnpj[12:] == f"{d1}{d2}"


def normalize_cep(raw: str) -> str:
    """'01001-000' -> '01001000'."""
    return re.sub(r"\D", "", raw or "")


def is_valid_cep(raw: str) -> bool:
    return len(normalize_cep(raw)) == 8
