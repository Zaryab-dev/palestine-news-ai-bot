"""Deduplication and qualification engine for Palestine & Gaza news stories."""

from difflib import SequenceMatcher
import logging
import re
from typing import Any, Dict, List, Tuple

from src.state_store import StateStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def compute_title_similarity(title1: str, title2: str) -> float:
    """Compute string similarity ratio between two normalized titles."""
    norm1 = re.sub(r"\W+", " ", title1.lower()).strip()
    norm2 = re.sub(r"\W+", " ", title2.lower()).strip()
    return SequenceMatcher(None, norm1, norm2).ratio()


class StoryDeduplicator:
    def __init__(
        self,
        state_store: StateStore,
        similarity_threshold: float = 0.72,
    ):
        self.state_store = state_store
        self.similarity_threshold = similarity_threshold

    def filter_and_deduplicate(self, raw_stories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deduplicate raw stories against previously processed state and against each other.
        Clusters multiple reporting sources reporting on the same event.
        """
        processed_records = self.state_store.get_processed_stories()
        processed_urls = {r.get("canonical_url") for r in processed_records.values() if r.get("canonical_url")}

        valid_stories: List[Dict[str, Any]] = []

        # Step 1: Discard stories already processed in previous batches
        for story in raw_stories:
            sid = story.get("story_id")
            url = story.get("canonical_url")

            if sid in processed_records or url in processed_urls:
                continue

            valid_stories.append(story)

        # Step 2: Intra-batch clustering by title similarity & event matching
        clustered: List[Dict[str, Any]] = []

        for candidate in valid_stories:
            matched_cluster = None
            for existing in clustered:
                sim = compute_title_similarity(candidate["title"], existing["title"])
                if sim >= self.similarity_threshold:
                    matched_cluster = existing
                    break

            if matched_cluster is not None:
                # Merge into existing cluster: add source URL and source name
                if candidate["canonical_url"] not in matched_cluster["source_urls"]:
                    matched_cluster["source_urls"].append(candidate["canonical_url"])
                if candidate["source_name"] not in matched_cluster["sources"]:
                    matched_cluster["sources"].append(candidate["source_name"])
                if not matched_cluster.get("source_image_url") and candidate.get("source_image_url"):
                    matched_cluster["source_image_url"] = candidate.get("source_image_url")
                # Corroborated by multiple independent agencies!
                matched_cluster["verification_status"] = "verified_multi_source"
                matched_cluster["priority"] = "high"
            else:
                # Initialize new cluster
                clustered.append({
                    "story_id": candidate["story_id"],
                    "title": candidate["title"],
                    "summary": candidate["summary"],
                    "canonical_url": candidate["canonical_url"],
                    "source_urls": [candidate["canonical_url"]],
                    "sources": [candidate["source_name"]],
                    "primary_source": candidate["source_name"],
                    "topic": candidate["topic"],
                    "category": candidate["category"],
                    "published_at_utc": candidate["published_at_utc"],
                    "source_image_url": candidate.get("source_image_url"),
                    "verification_status": (
                        "verified_multi_source"
                        if candidate.get("category") == "humanitarian_un"
                        else "single_source_attributed"
                    ),
                    "priority": (
                        "high"
                        if candidate["topic"] in ["humanitarian_aid", "healthcare_medical", "food_famine"]
                        else "normal"
                    ),
                })

        logger.info(
            f"Deduplication complete: {len(raw_stories)} raw stories -> "
            f"{len(valid_stories)} new -> {len(clustered)} unique story clusters."
        )
        return clustered
