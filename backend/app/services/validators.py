"""Deterministic checks. No LLM here: required fields, numeric limits, cross-section consistency.

Every function returns a CheckResult; `passed=None` means "cannot determine".
"""
import re
from dataclasses import dataclass


@dataclass
class Chunk:
    page: int
    text: str


@dataclass
class CheckResult:
    passed: bool | None
    explanation: str
    page: int | None = None
    quote: str | None = None


def _snippet(text: str, start: int, end: int, pad: int = 60) -> str:
    return " ".join(text[max(0, start - pad) : end + pad].split())


def check_required_terms(chunks: list[Chunk], patterns: list[str], what: str) -> CheckResult:
    """Pass if any pattern appears anywhere in the document."""
    for c in chunks:
        for p in patterns:
            m = re.search(p, c.text, re.I)
            if m:
                return CheckResult(True, f"{what} found.", c.page, _snippet(c.text, m.start(), m.end()))
    return CheckResult(False, f"No {what} was found in the document. Detected by a required-evidence check, not inferred.")


def check_numeric_min(chunks: list[Chunk], pattern: str, minimum: float, unit: str, what: str) -> CheckResult:
    """`pattern` must contain one capture group with the number, e.g. r'(\\d+(?:\\.\\d+)?)\\s*(?:in\\.|inch)'."""
    values: list[tuple[float, Chunk, re.Match]] = []
    for c in chunks:
        for m in re.finditer(pattern, c.text, re.I):
            values.append((float(m.group(1)), c, m))
    if not values:
        return CheckResult(False, f"No {what} value was found, so compliance cannot be confirmed.")
    low, c, m = min(values, key=lambda v: v[0])
    quote = _snippet(c.text, m.start(), m.end())
    if low < minimum:
        return CheckResult(False, f"{what.capitalize()} of {low:g} {unit} is below the required minimum of {minimum:g} {unit}.", c.page, quote)
    return CheckResult(True, f"{what.capitalize()} of {low:g} {unit} meets the minimum of {minimum:g} {unit}.", c.page, quote)


def check_consistency(chunks: list[Chunk], pattern_a: str, pattern_b: str, what: str) -> CheckResult:
    """Two sections must state the same number. Each pattern captures one number."""

    def first(p: str):
        for c in chunks:
            m = re.search(p, c.text, re.I)
            if m:
                return float(m.group(1)), c, m
        return None

    a, b = first(pattern_a), first(pattern_b)
    if not a or not b:
        return CheckResult(None, f"Could not locate both {what} values to compare.")
    if a[0] != b[0]:
        return CheckResult(
            False,
            f"{what.capitalize()} differs: {a[0]:g} (page {a[1].page}) vs {b[0]:g} (page {b[1].page}).",
            a[1].page,
            _snippet(a[1].text, a[2].start(), a[2].end()),
        )
    return CheckResult(True, f"{what.capitalize()} is consistent ({a[0]:g}).", a[1].page, _snippet(a[1].text, a[2].start(), a[2].end()))


def run_rule_check(check_type: str, params: dict, chunks: list[Chunk]) -> CheckResult | None:
    """Dispatch a rule's deterministic check. Returns None for semantic rules (handled by the LLM)."""
    if check_type == "required_term":
        return check_required_terms(chunks, params["patterns"], params.get("what", "required evidence"))
    if check_type == "numeric_min":
        return check_numeric_min(chunks, params["pattern"], params["minimum"], params.get("unit", ""), params.get("what", "value"))
    if check_type == "consistency":
        return check_consistency(chunks, params["pattern_a"], params["pattern_b"], params.get("what", "value"))
    return None


def quote_is_grounded(quote: str | None, chunks: list[Chunk]) -> bool:
    """Guard against LLM hallucination: a quote must appear verbatim (whitespace-normalised)."""
    if not quote:
        return False
    norm = lambda s: " ".join(s.split()).lower()  # noqa: E731
    q = norm(quote)
    return any(q in norm(c.text) for c in chunks)
