"""Validation tests ensuring post structure complies with post.schema.json."""

import json
from pathlib import Path
from src.llm_writer import LLMWriter


def test_dry_run_post_conforms_to_schema():
    writer = LLMWriter()
    sample_story = {
        "story_id": "abc123xyz789",
        "title": "UNICEF delivers 10,000 hygiene kits and therapeutic food to southern Gaza",
        "summary": "Critical nutrition supplies dispatched to children and displaced families in tent encampments.",
        "canonical_url": "https://unicef.org/press/gaza-supplies",
        "source_urls": ["https://unicef.org/press/gaza-supplies"],
        "primary_source": "UNICEF",
        "topic": "education_children",
        "published_at_utc": "2026-11-09T04:00:00Z",
        "verification_status": "verified_multi_source",
        "priority": "high",
    }

    draft = writer.generate_post_draft(sample_story, batch_id="20261109_0500_utc")

    # Required fields
    required = [
        "batch_id",
        "story_id",
        "topic",
        "headline",
        "source_name",
        "source_urls",
        "published_at_utc",
        "x_post",
        "image_prompt",
        "image_filename",
        "verification_status",
        "review_status",
    ]
    for req in required:
        assert req in draft, f"Missing required field: {req}"

    # Character limit check
    assert len(draft["x_post"]) <= 280
    assert len(draft["source_urls"]) >= 1
    assert draft["image_filename"].endswith(".png")
    assert draft["review_status"] in ["PENDING_IMAGE", "READY_FOR_REVIEW"]
