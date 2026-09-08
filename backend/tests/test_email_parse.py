from app.models.user import Role
from app.services.email_parse import parse_email

RAW = """From: Anil Verma <anil.verma@partner.example>
To: rm@example.com
Date: Mon, 1 Sep 2026 10:15:00 +0530
Subject: Re: September CSP targets

Thanks for the update. I will approve the two new onboardings by Friday.
Please share the branch-wise report before the review.

On Sun, 31 Aug 2026 at 18:02, The RM wrote:
> Sharing the August summary for your review.
> Regards
"""


def test_parser_extracts_headers_and_strips_quote():
    p = parse_email(RAW)
    assert p.from_email == "anil.verma@partner.example"
    assert p.from_name == "Anil Verma"
    assert p.subject == "Re: September CSP targets"
    assert p.date is not None and p.date.year == 2026
    assert "approve the two new onboardings" in p.body
    assert "August summary for your review" not in p.body  # quoted history dropped
    assert p.quoted_removed is True


def test_parser_handles_a_plain_paste():
    p = parse_email("From: someone@partner.example\nSubject: quick note\n\nCalled about the mapping issue.")
    assert p.from_email == "someone@partner.example"
    assert p.subject == "quick note"
    assert "mapping issue" in p.body


def test_parse_endpoint_matches_the_sender(client, make_user, login):
    make_user(email="admin@example.com", password="secret123", role=Role.ADMIN)
    login("admin@example.com", "secret123")

    official = client.post(
        "/api/v1/officials",
        json={"name": "Anil Verma", "email": "anil.verma@partner.example"},
    ).json()
    rel = client.post(
        "/api/v1/relationships", json={"official_id": official["id"]}
    ).json()

    resp = client.post("/api/v1/interactions/email/parse", json={"raw_email": RAW})
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched_official_id"] == official["id"]
    assert body["matched_relationship_id"] == rel["id"]
    assert body["subject"] == "Re: September CSP targets"

    # the parsed body then flows through the normal create path
    created = client.post(
        "/api/v1/interactions",
        json={
            "relationship_id": rel["id"],
            "type": "email",
            "direction": "inbound",
            "raw_notes": body["body"],
        },
    )
    assert created.status_code == 201
    assert created.json()["structured"]["commitments"]


def test_parse_endpoint_needs_editor_role(client, make_user, login):
    make_user(email="v@example.com", password="secret123", role=Role.APPROVER_VIEWER)
    login("v@example.com", "secret123")
    assert (
        client.post(
            "/api/v1/interactions/email/parse", json={"raw_email": RAW}
        ).status_code
        == 403
    )
