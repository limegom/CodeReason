from __future__ import annotations

import pytest

from app.deterministic.comparison import ComparisonMode, compare_outputs


@pytest.mark.parametrize(
    ("policy", "expected", "actual", "matched"),
    [
        (ComparisonMode.EXACT, "answer\n", "answer", False),
        (ComparisonMode.IGNORE_FINAL_NEWLINE, "answer\n", "answer", True),
        (ComparisonMode.IGNORE_FINAL_NEWLINE, "answer\n", "answer\n\n", False),
        (
            ComparisonMode.TRIM_TRAILING_WHITESPACE,
            "alpha  \r\nbeta\t\r\n",
            "alpha\nbeta\n",
            True,
        ),
        (ComparisonMode.TOKEN_BASED, "1  2\n3", "1\t2 3", True),
        (ComparisonMode.JSON_VALUE, '{"b":2,"a":[1,true]}', '{"a":[1.0,true],"b":2}', True),
        (ComparisonMode.JSON_VALUE, "true", "1", False),
    ],
)
def test_comparison_policies(policy, expected, actual, matched):
    result = compare_outputs(expected, actual, policy)

    assert result.matched is matched
    assert result.policy is policy


def test_invalid_or_ambiguous_json_does_not_match():
    result = compare_outputs('{"key":1}', '{"key":1,"key":2}', "JSON_VALUE")

    assert result.matched is False
    assert result.error and result.error.startswith("invalid_json:")
