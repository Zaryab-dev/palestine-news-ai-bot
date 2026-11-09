"""Tests for title similarity, clustering, and cross-source verification."""

import pytest
from src.dedupe_and_filter import StoryDeduplicator, compute_title_similarity
from src.state_store import StateStore


def test_title_similarity():
    t1 = "UN warns of severe famine risk in northern Gaza"
    t2 = "UN warns severe famine risk across northern Gaza"
    sim = compute_title_similarity(t1, t2)
    assert sim > 0.85

    t3 = "Washington vetoes UN Security Council ceasefire resolution"
    sim_diff = compute_title_similarity(t1, t3)
    assert sim_diff < 0.40


def test_story_clustering_and_corroboration(tmp_path):
    store = StateStore(state_dir=str(tmp_path))
    deduper = StoryDeduplicator(state_store=store, similarity_threshold=0.70)

    raw_stories = [
        {
            "story_id": "story111",
            "title": "WHO delivers emergency surgical kits to Al-Shifa hospital",
            "summary": "WHO teams reach Al-Shifa with medical supplies.",
            "canonical_url": "https://who.int/news/item/111",
            "source_name": "WHO News",
            "category": "humanitarian_un",
            "topic": "healthcare_medical",
            "published_at_utc": "2026-11-09T02:00:00Z",
        },
        {
            "story_id": "story222",
            "title": "WHO delivers surgical kits to Gaza's Al-Shifa hospital",
            "summary": "Medical kits delivered to northern Gaza.",
            "canonical_url": "https://aljazeera.com/news/who-shifa",
            "source_name": "Al Jazeera",
            "category": "international_news",
            "topic": "healthcare_medical",
            "published_at_utc": "2026-11-09T02:30:00Z",
        },
        {
            "story_id": "story333",
            "title": "US State Department briefs on regional aid corridors",
            "summary": "Diplomatic talks on opening crossings.",
            "canonical_url": "https://reuters.com/news/us-state-dept",
            "source_name": "Reuters",
            "category": "international_news",
            "topic": "diplomacy_politics",
            "published_at_utc": "2026-11-09T03:00:00Z",
        },
    ]

    clustered = deduper.filter_and_deduplicate(raw_stories)

    # 3 raw stories should collapse into 2 clusters (the two WHO/Al Jazeera stories merged)
    assert len(clustered) == 2

    merged = next(c for c in clustered if "Al-Shifa" in c["title"])
    assert len(merged["source_urls"]) == 2
    assert "https://who.int/news/item/111" in merged["source_urls"]
    assert "https://aljazeera.com/news/who-shifa" in merged["source_urls"]
    assert merged["verification_status"] == "verified_multi_source"
