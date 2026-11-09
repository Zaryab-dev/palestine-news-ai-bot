"""Integration tests for state storage, image fallback, and end-to-end dry run."""

from pathlib import Path
import pytest
from src.image_generator import ImageGenerator
from src.pipeline import run_batch
from src.state_store import StateStore


def test_state_store_lifecycle(tmp_path):
    store = StateStore(state_dir=str(tmp_path))

    # Queue management
    stories = [
        {"story_id": "sid_1", "title": "Story 1", "canonical_url": "https://example.org/1"},
        {"story_id": "sid_2", "title": "Story 2", "canonical_url": "https://example.org/2"},
        {"story_id": "sid_3", "title": "Story 3", "canonical_url": "https://example.org/3"},
    ]
    added = store.add_to_pending_queue(stories)
    assert added == 3

    # Adding duplicate should not increase queue
    assert store.add_to_pending_queue(stories) == 0

    # Pop batch of 2
    batch = store.pop_pending_batch(batch_size=2)
    assert len(batch) == 2
    assert batch[0]["story_id"] == "sid_1"

    # 1 remaining in queue
    remaining = store.get_pending_queue()
    assert len(remaining) == 1
    assert remaining[0]["story_id"] == "sid_3"

    # Mark processed
    store.record_processed_story(
        story_id="sid_1",
        canonical_url="https://example.org/1",
        headline="Story 1",
        batch_id="b1",
    )
    assert store.is_story_processed("sid_1") is True
    assert store.is_story_processed("sid_2") is False


def test_fallback_editorial_graphic(tmp_path):
    gen = ImageGenerator(width=640, height=360)
    out_path = tmp_path / "test_graphic.png"

    success = gen.create_fallback_graphic(
        headline="UN OCHA reports critical water pipeline repairs underway",
        source="UN OCHA",
        topic="infrastructure_housing",
        output_path=out_path,
    )

    assert success is True
    assert out_path.exists()
    assert out_path.stat().st_size > 1000


def test_dry_run_batch_execution(tmp_path):
    test_settings = {
        "pipeline": {
            "batch_size": 2,
            "max_story_age_hours": 48,
            "dedupe_similarity_threshold": 0.72,
            "output_dir": str(tmp_path / "output"),
            "state_dir": str(tmp_path / "state"),
        },
        "llm": {
            "provider": "gemini",
            "gemini_model": "gemini-2.5-flash",
            "temperature": 0.2,
        },
        "image": {
            "model": "flux",
            "width": 640,
            "height": 360,
        },
        "google_drive": {
            "root_folder_name": "Test-Gaza-News",
        },
    }

    # Pre-populate pending queue
    store = StateStore(state_dir=str(tmp_path / "state"))
    store.add_to_pending_queue([
        {
            "story_id": "test_s1",
            "title": "Medical teams at Nasser hospital receive pediatric supplies",
            "summary": "Urgent medicine supplied for newborn care and pediatric surgery.",
            "canonical_url": "https://example.org/nasser-pediatric",
            "primary_source": "PRCS Red Crescent",
            "topic": "healthcare_medical",
            "published_at_utc": "2026-11-09T03:00:00Z",
        }
    ])

    result = run_batch(test_settings, batch_size=1, dry_run=True, generate_images=False)
    assert result["status"] == "success"
    assert len(result["posts"]) == 1
    post = result["posts"][0]
    assert post["story_id"] == "test_s1"
    assert "PRCS Red Crescent" in post["x_post"]
