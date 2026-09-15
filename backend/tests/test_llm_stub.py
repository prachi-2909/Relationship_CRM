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


def test_stub_extracts_reports_to_relation():
    text = "Adarsh Giri reports to Sunil Verma on the new vertical."
    result = extract_interaction(text, interaction_type="call")
    assert len(result.relations) == 1
    rel = result.relations[0]
    assert (rel.from_, rel.type, rel.to) == ("Adarsh Giri", "reports_to", "Sunil Verma")
    # relation participants are folded into people even without an honorific
    assert "Adarsh Giri" in result.people and "Sunil Verma" in result.people


def test_stub_extracts_manager_is_phrasing():
    text = "Met the team. Anita Rao's manager is Deepak Nair."
    result = extract_interaction(text, interaction_type="meeting")
    assert any(
        (r.from_, r.type, r.to) == ("Anita Rao", "reports_to", "Deepak Nair")
        for r in result.relations
    )


def test_stub_extracts_introduced_by_with_correct_direction():
    text = "Prachi Sundaram introduced us to Adarsh Giri at the summit."
    result = extract_interaction(text, interaction_type="meeting")
    assert len(result.relations) == 1
    rel = result.relations[0]
    # the person introduced is `from`, the introducer is `to`
    assert (rel.from_, rel.type, rel.to) == (
        "Adarsh Giri", "introduced_by", "Prachi Sundaram",
    )


def test_stub_extracts_works_with_relation():
    text = "Ravi Kumar works closely with Sunil Verma on the migration."
    result = extract_interaction(text, interaction_type="note")
    assert any(
        (r.from_, r.type, r.to) == ("Ravi Kumar", "works_with", "Sunil Verma")
        for r in result.relations
    )


def test_stub_finds_no_relations_in_plain_text():
    result = extract_interaction(
        "General update, nothing new to report this week.", interaction_type="note"
    )
    assert result.relations == []


def test_json_blob_unwraps_fenced_and_preambled_model_output():
    # bare object
    assert _json_blob('{"a": 1}') == '{"a": 1}'
    # ```json fenced (common from small Ollama models)
    assert _json_blob('```json\n{"a": 1}\n```') == '{"a": 1}'
    # a line of preamble before the object
    assert _json_blob('Here is the JSON:\n{"a": 1}') == '{"a": 1}'
    # trailing commentary after the object
    assert _json_blob('{"a": 1}\nHope that helps!') == '{"a": 1}'
