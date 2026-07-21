from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RedactionFinding:
    category: str
    placeholder: str
    count: int


@dataclass(frozen=True, slots=True)
class RedactionResult:
    redacted_text: str
    findings: tuple[RedactionFinding, ...]

    @property
    def redaction_count(self) -> int:
        return sum(item.count for item in self.findings)

    def disclosure(self) -> dict[str, object]:
        return {
            "redacted": self.redaction_count > 0,
            "redaction_count": self.redaction_count,
            "categories": [item.category for item in self.findings],
            "external_provider_fields": [
                "assignment_description",
                "human_approved_rubric",
                "redacted_source_code",
                "sanitized_primary_evidence",
                "score_bounds",
            ],
        }


_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "PRIVATE_KEY",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
            re.DOTALL,
        ),
    ),
    ("EMAIL", re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("OPENAI_API_KEY", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("GITHUB_TOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("AWS_ACCESS_KEY", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    (
        "BEARER_TOKEN",
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    ),
    (
        "SECRET_ASSIGNMENT",
        re.compile(
            r"(?im)(\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|secret|password)\b\s*[:=]\s*)"
            r"([\"']?)[^\s,;\"']{8,}\2"
        ),
    ),
    (
        "PERSON_NAME",
        re.compile(
            r"(?im)(\b(?:student[_ -]?name|full[_ -]?name|author|name)\b\s*[:=]\s*\\?[\"']?)"
            r"(?:[A-Z][a-z]+(?:[ -][A-Z][a-z]+){1,3}|[가-힣]{2,5})"
        ),
    ),
    (
        "COMMENT_PERSON_NAME",
        re.compile(
            r"(?im)((?:^|\\n|\n|[\"'])\s*#\s*(?:name\s*[:=-]\s*)?)"
            r"(?:[A-Z][a-z]+(?:[ -][A-Z][a-z]+){1,3}|[가-힣]{2,5})"
            r"(?=\s*(?:\\n|\n|[,;]|$))"
        ),
    ),
    ("STUDENT_ID", re.compile(r"(?<!\d)(?:19|20)\d{6,10}(?!\d)")),
)


def _replace_explicit_identifier(text: str, identifier: str, index: int) -> tuple[str, int]:
    identifier = identifier.strip()
    if len(identifier) < 2:
        return text, 0
    pattern = re.compile(re.escape(identifier), re.IGNORECASE)
    return pattern.subn(f"[REDACTED_IDENTIFIER_{index}]", text)


def redact_for_external_provider(
    text: str,
    *,
    explicit_identifiers: Iterable[str] = (),
) -> RedactionResult:
    """Redact likely PII and secrets before sending data to an AI provider.

    The deterministic patterns are a best-effort control and cannot detect every
    form of sensitive data.
    """

    redacted = text
    findings: list[RedactionFinding] = []

    for index, identifier in enumerate(explicit_identifiers, start=1):
        redacted, count = _replace_explicit_identifier(redacted, identifier, index)
        if count:
            findings.append(
                RedactionFinding("EXPLICIT_IDENTIFIER", f"[REDACTED_IDENTIFIER_{index}]", count)
            )

    for category, pattern in _PATTERNS:
        placeholder = f"[REDACTED_{category}]"
        if category in {"SECRET_ASSIGNMENT", "PERSON_NAME", "COMMENT_PERSON_NAME"}:
            redacted, count = pattern.subn(lambda match: f"{match.group(1)}{placeholder}", redacted)
        else:
            redacted, count = pattern.subn(placeholder, redacted)
        if count:
            findings.append(RedactionFinding(category, placeholder, count))

    return RedactionResult(redacted, tuple(findings))
