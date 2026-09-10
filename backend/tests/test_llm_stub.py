from app.models.interaction import Sentiment
from app.services.llm import _json_blob, extract_interaction


def test_stub_detects_positive_sentiment_and_summary():
    text = (
        "Met the AGM at Head Office. They were very pleased with the rollout and "
        "thanked the team. He will share the revised targets by Monday."
    )
    result = extract_interaction(text, interaction_type="meeting")
    assert result.model == "stub"
    assert result.sentiment == Sentiment.POSITIVE
    assert result.summary
    assert any("share the revised targets" in c.lower() for c in result.commitments)


def test_stub_detects_negative_and_requests():
    text = (
        "Branch manager raised a complaint about the pending settlement issue. "
        "Please expedite the reconciliation and revert with a timeline."
    )
    result = extract_interaction(text, interaction_type="call")
    assert result.sentiment == Sentiment.NEGATIVE
    assert any("expedite" in r.lower() or "revert" in r.lower() for r in result.requests)


def test_stub_picks_up_named_people():
    text = "Call with Mr. Rajesh Kumar and Ms. Anita Rao about the branch mapping."
    result = extract_interaction(text, interaction_type="call")
    assert "Rajesh Kumar" in result.people
    assert "Anita Rao" in result.people


def test_empty_text_is_safe():
    result = extract_interaction("   ", interaction_type="note")
    assert result.sentiment == Sentiment.UNKNOWN
    assert result.summary == ""


def test_json_blob_unwraps_fenced_and_preambled_model_output():
    # bare object
    assert _json_blob('{"a": 1}') == '{"a": 1}'
    # ```json fenced (common from small Ollama models)
    assert _json_blob('```json\n{"a": 1}\n```') == '{"a": 1}'
    # a line of preamble before the object
    assert _json_blob('Here is the JSON:\n{"a": 1}') == '{"a": 1}'
    # trailing commentary after the object
    assert _json_blob('{"a": 1}\nHope that helps!') == '{"a": 1}'
