from app.services import knowledge
from app.models.knowledge import KnowledgeChunk


def test_chunk_text_packs_sentences_under_budget():
    text = "First sentence here. Second sentence here. Third one follows."
    chunks = knowledge.chunk_text(text, max_chars=40)
    assert len(chunks) >= 2
    assert all(len(c) <= 60 for c in chunks)  # a little slack for one oversized sentence


def test_chunk_text_empty_returns_nothing():
    assert knowledge.chunk_text("") == []
    assert knowledge.chunk_text("   ") == []


def test_chunk_text_oversized_sentence_is_its_own_chunk():
    long_sentence = "word " * 200 + "."
    chunks = knowledge.chunk_text(long_sentence, max_chars=50)
    assert len(chunks) == 1


def test_index_source_creates_and_replaces_chunks(db, make_official):
    from app.models.relationship import Relationship

    official = make_official(name="Test Official")
    rel = Relationship(official_id=official.id)
    db.add(rel)
    db.commit()
    db.refresh(rel)

    knowledge.index_source(
        db, "interaction", 1, "Interested in a working capital loan for expansion.",
        relationship_id=rel.id, official_id=official.id,
    )
    db.commit()
    rows = db.query(KnowledgeChunk).filter_by(source_type="interaction", source_id=1).all()
    assert len(rows) == 1
    assert rows[0].embedding is not None
    assert rows[0].embedding_model == "stub"

    # replaced wholesale, not appended
    knowledge.index_source(
        db, "interaction", 1, "Completely different note now.",
        relationship_id=rel.id, official_id=official.id,
    )
    db.commit()
    rows = db.query(KnowledgeChunk).filter_by(source_type="interaction", source_id=1).all()
    assert len(rows) == 1
    assert "Completely different" in rows[0].text


def test_index_source_never_raises_on_bad_input(db):
    # no relationship/official actually exist for id 999 - the FK would fail
    # at flush, and index_source must swallow that rather than propagate
    knowledge.index_source(db, "interaction", 999, "some text", relationship_id=999999, official_id=999999)


def test_search_scoped_to_given_relationship_ids(db, make_official):
    from app.models.relationship import Relationship

    off_a = make_official(name="Official A")
    off_b = make_official(name="Official B")
    rel_a = Relationship(official_id=off_a.id)
    rel_b = Relationship(official_id=off_b.id)
    db.add_all([rel_a, rel_b])
    db.commit()
    db.refresh(rel_a)
    db.refresh(rel_b)

    knowledge.index_source(
        db, "interaction", 1, "Interested in a new business loan for expansion.",
        relationship_id=rel_a.id, official_id=off_a.id,
    )
    knowledge.index_source(
        db, "interaction", 2, "Interested in a new business loan for expansion.",
        relationship_id=rel_b.id, official_id=off_b.id,
    )
    db.commit()

    results = knowledge.search(db, relationship_ids=[rel_a.id], query="business loan expansion")
    assert results
    assert all(r["relationship_id"] == rel_a.id for r in results)


def test_search_returns_empty_when_disabled(db, make_official, monkeypatch):
    from app.models.relationship import Relationship

    official = make_official(name="Someone")
    rel = Relationship(official_id=official.id)
    db.add(rel)
    db.commit()
    db.refresh(rel)
    knowledge.index_source(
        db, "interaction", 1, "Interested in a loan.", relationship_id=rel.id, official_id=official.id
    )
    db.commit()

    monkeypatch.setattr(knowledge.settings, "enable_rag", False)
    assert knowledge.search(db, relationship_ids=[rel.id], query="loan") == []


def test_search_empty_with_no_relationship_ids(db):
    assert knowledge.search(db, relationship_ids=[], query="anything") == []


def test_search_below_similarity_threshold_excluded(db, make_official, monkeypatch):
    from app.models.relationship import Relationship

    official = make_official(name="Someone")
    rel = Relationship(official_id=official.id)
    db.add(rel)
    db.commit()
    db.refresh(rel)
    knowledge.index_source(
        db, "interaction", 1, "Completely unrelated topic entirely.",
        relationship_id=rel.id, official_id=official.id,
    )
    db.commit()

    monkeypatch.setattr(knowledge.settings, "rag_min_similarity", 0.999)
    assert knowledge.search(db, relationship_ids=[rel.id], query="loan expansion business") == []
