"""Master Orchestration Pipeline for Palestine & Gaza News AI Bot."""

import argparse
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
import yaml
from dotenv import load_dotenv

from src.dedupe_and_filter import StoryDeduplicator
from src.drive_uploader import DriveUploader
from src.image_generator import ImageGenerator
from src.llm_writer import LLMWriter
from src.rss_collector import RSSCollector
from src.state_store import StateStore

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("Pipeline")


def load_settings(config_path: str = "config/settings.yaml") -> Dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_test_feeds(feeds_config: str = "config/feeds.yaml"):
    """Test connectivity and relevance of all feeds in feeds.yaml."""
    collector = RSSCollector(feeds_config_path=feeds_config)
    print("\n" + "=" * 60)
    print("TESTING CONFIGURED FEEDS FOR PALESTINE & GAZA NEWS")
    print("=" * 60)

    total_relevant = 0
    for feed in collector.feeds:
        name = feed.get("name")
        url = feed.get("url")
        print(f"\n[+] Testing: {name}")
        stories = collector.fetch_feed(feed)
        print(f"    URL: {url}")
        print(f"    Relevant Stories Found: {len(stories)}")
        if stories:
            sample = stories[0]
            print(f"    Sample: \"{sample['title']}\"")
            print(f"    Topic:  [{sample['topic']}]")
        total_relevant += len(stories)

    print("\n" + "=" * 60)
    print(f"SUMMARY: {len(collector.feeds)} feeds tested. Total relevant articles: {total_relevant}")
    print("=" * 60 + "\n")


def run_collect(settings: Dict[str, Any], feeds_config: str = "config/feeds.yaml") -> int:
    """Collect latest news from feeds, deduplicate, and enqueue into pending_queue."""
    state_dir = settings.get("pipeline", {}).get("state_dir", "state")
    state_store = StateStore(state_dir=state_dir)
    collector = RSSCollector(feeds_config_path=feeds_config)
    deduplicator = StoryDeduplicator(
        state_store=state_store,
        similarity_threshold=settings.get("pipeline", {}).get("dedupe_similarity_threshold", 0.72),
    )

    logger.info("Starting scheduled RSS news collection...")
    raw_stories = collector.collect_all()
    if not raw_stories:
        logger.info("No relevant stories returned by feeds.")
        return 0

    unique_candidates = deduplicator.filter_and_deduplicate(raw_stories)
    added = state_store.add_to_pending_queue(unique_candidates)
    logger.info(f"Enqueued {added} new unique stories into pending queue.")
    return added


def run_batch(
    settings: Dict[str, Any],
    batch_size: Optional[int] = None,
    dry_run: bool = False,
    generate_images: bool = True,
) -> Dict[str, Any]:
    """Execute batch processing: synthesize posts, render illustrations, and archive to Drive."""
    batch_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M_utc")
    state_dir = settings.get("pipeline", {}).get("state_dir", "state")
    output_dir = Path(settings.get("pipeline", {}).get("output_dir", "output"))
    batch_dir = output_dir / "batches" / batch_id
    images_dir = batch_dir / "images"

    limit = batch_size or settings.get("pipeline", {}).get("batch_size", 5)
    state_store = StateStore(state_dir=state_dir)

    # 1. Pop candidates from pending queue
    candidates = state_store.pop_pending_batch(batch_size=limit)

    # If pending queue is empty, do an on-the-fly collection
    if not candidates:
        logger.info("Pending queue empty. Running live RSS fetch...")
        run_collect(settings)
        candidates = state_store.pop_pending_batch(batch_size=limit)

    if not candidates:
        logger.info("No candidates available for batch generation.")
        return {"status": "empty", "batch_id": batch_id, "posts": []}

    logger.info(f"Starting batch {batch_id} with {len(candidates)} candidate stories...")

    # 2. Initialize Generators
    llm_settings = settings.get("llm", {})
    writer = LLMWriter(
        provider=llm_settings.get("provider", "gemini"),
        gemini_model=llm_settings.get("gemini_model", "gemini-2.5-flash"),
        gemini_fallback_model=llm_settings.get("gemini_fallback_model", "gemini-1.5-flash"),
        groq_model=llm_settings.get("groq_model", "llama-3.3-70b-versatile"),
        temperature=llm_settings.get("temperature", 0.2),
    )

    img_settings = settings.get("image", {})
    image_gen = ImageGenerator(
        model=img_settings.get("model", "flux"),
        width=img_settings.get("width", 1280),
        height=img_settings.get("height", 720),
        style_directive=img_settings.get("style_directive"),
    )

    drive_settings = settings.get("google_drive", {})
    uploader = DriveUploader(root_folder_name=drive_settings.get("root_folder_name", "Gaza-Palestine-News-AI-Bot"))

    # 3. Process each candidate
    posts: List[Dict[str, Any]] = []

    for idx, story in enumerate(candidates, 1):
        sid = story["story_id"]
        logger.info(f"[{idx}/{len(candidates)}] Processing story: {sid} - {story['title'][:60]}...")

        # A. Draft Post via LLM
        post = writer.generate_post_draft(story, batch_id=batch_id)
        post["generated_at_utc"] = datetime.now(timezone.utc).isoformat()

        # B. Generate Editorial Illustration
        img_filename = f"{sid}.png"
        img_path = images_dir / img_filename

        if generate_images:
            prompt = post.get("image_prompt", story["title"])
            success = image_gen.generate_image(prompt, img_path, seed=(hash(sid) % 100000))
            if success:
                post["image_status"] = "GENERATED"
            else:
                # Use elegant fallback typography card
                fallback_success = image_gen.create_fallback_graphic(
                    headline=post.get("headline", story["title"]),
                    source=post.get("source_name", story.get("primary_source", "News Agency")),
                    topic=post.get("topic", story.get("topic", "humanitarian_aid")),
                    output_path=img_path,
                )
                post["image_status"] = "GENERATED" if fallback_success else "IMAGE_FAILED"
        else:
            post["image_status"] = "SKIPPED"

        post["review_status"] = "READY_FOR_REVIEW"
        posts.append(post)

        # Record to permanent state unless in dry-run
        if not dry_run:
            state_store.record_processed_story(
                story_id=sid,
                canonical_url=story.get("canonical_url", ""),
                headline=post.get("headline", story["title"]),
                batch_id=batch_id,
                review_status="READY_FOR_REVIEW",
            )

    # 4. Archive & Sync to Drive
    archive_result = uploader.archive_batch(batch_id=batch_id, posts=posts, batch_dir=batch_dir)

    print("\n" + "=" * 60)
    print(f"BATCH {batch_id} COMPLETED SUCCESSFULLY")
    print("=" * 60)
    print(f"Posts Created:    {len(posts)}")
    print(f"Local Directory:  {archive_result.get('local_dir')}")
    print(f"Synced to Drive:  {archive_result.get('synced_to_drive')}")
    if archive_result.get("drive_folder_id"):
        print(f"Drive Folder ID:  {archive_result.get('drive_folder_id')}")
    print("=" * 60 + "\n")

    return {
        "status": "success",
        "batch_id": batch_id,
        "posts": posts,
        "archive": archive_result,
    }


def main():
    parser = argparse.ArgumentParser(description="Palestine & Gaza News AI Bot Orchestrator")
    parser.add_argument(
        "--mode",
        choices=["collect", "batch", "dry-run", "test-feeds"],
        default="batch",
        help="Pipeline execution mode",
    )
    parser.add_argument("--batch-size", type=int, default=5, help="Number of stories to include in batch")
    parser.add_argument("--no-images", action="store_true", help="Skip image generation to speed up testing")
    parser.add_argument("--config", default="config/settings.yaml", help="Path to settings.yaml")
    args = parser.parse_args()

    settings = load_settings(args.config)

    if args.mode == "test-feeds":
        run_test_feeds()
    elif args.mode == "collect":
        run_collect(settings)
    elif args.mode == "batch":
        run_batch(settings, batch_size=args.batch_size, generate_images=not args.no_images)
    elif args.mode == "dry-run":
        run_batch(settings, batch_size=args.batch_size, dry_run=True, generate_images=not args.no_images)


if __name__ == "__main__":
    main()
