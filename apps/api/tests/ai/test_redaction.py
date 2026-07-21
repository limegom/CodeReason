import json

from app.ai.redaction import redact_for_external_provider


FAKE_OPENAI_KEY = "sk-" + "abcdefghijklmnopqrstuv"


def test_redacts_explicit_identifiers_email_and_openai_key():
    source = (
        '# Kim Jisu, 2026123456\nemail="jisu@example.edu"\n'
        f'key="{FAKE_OPENAI_KEY}"'
    )
    result = redact_for_external_provider(source, explicit_identifiers=["Kim Jisu"])

    assert "Kim Jisu" not in result.redacted_text
    assert "jisu@example.edu" not in result.redacted_text
    assert FAKE_OPENAI_KEY not in result.redacted_text
    assert result.redaction_count == 4


def test_disclosure_lists_only_external_payload_categories():
    result = redact_for_external_provider("print('hello')")
    disclosure = result.disclosure()
    assert disclosure["redacted"] is False
    assert "redacted_source_code" in disclosure["external_provider_fields"]


def test_redacts_labeled_person_names_without_an_explicit_identifier():
    result = redact_for_external_provider(
        '# student_name = "Kim Jisu"\n# author: 김지수\nname = "Ada Lovelace"\n'
    )

    assert "Kim Jisu" not in result.redacted_text
    assert "김지수" not in result.redacted_text
    assert "Ada Lovelace" not in result.redacted_text
    assert any(item.category == "PERSON_NAME" and item.count == 3 for item in result.findings)

    serialized = json.dumps({"redacted_source_code": '# name = "Grace Hopper"'})
    serialized_result = redact_for_external_provider(serialized)
    assert "Grace Hopper" not in serialized_result.redacted_text

    comment_payload = json.dumps({"redacted_source_code": "# Alan Turing\nprint('ok')"})
    comment_result = redact_for_external_provider(comment_payload)
    assert "Alan Turing" not in comment_result.redacted_text
