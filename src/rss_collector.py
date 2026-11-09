"""RSS Collector for fetching, parsing, and filtering Palestine & Gaza news feeds."""

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup
import feedparser
import requests
import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; PalestineHumanitarianNewsBot/1.0; +https://github.com/Zaryab-dev/palestine-news-ai-bot)"


def clean_html(raw_html: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def normalize_url(url: str) -> str:
    """Remove tracking parameters (utm_*, ref, etc.) and fragments from URL."""
    if not url:
        return ""
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    clean_params = {k: v for k, v in query_params.items() if not k.startswith("utm_") and k not in ["ref", "fbclid"]}
    cleaned = parsed._replace(query=urlencode(clean_params, doseq=True), fragment="")
    return urlunparse(cleaned).rstrip("/")


def generate_story_id(url: str, title: str) -> str:
    """Generate an immutable 12-char SHA-256 story ID from canonical URL and title."""
    clean_title = re.sub(r"\W+", "", title.lower())
    payload = f"{url}:{clean_title}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]


def parse_published_date(entry: Any) -> str:
    """Extract and format publication date as ISO 8601 UTC string."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        return dt.isoformat()
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        dt = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
        return dt.isoformat()
def extract_source_image_url(entry: Any, raw_html: str = "") -> Optional[str]:
    """Extract lead journalistic image from RSS enclosures, media tags, or embedded HTML."""
    # 1. Check enclosures
    enclosures = getattr(entry, "enclosures", []) or []
    for enc in enclosures:
        href = enc.get("href", "")
        enc_type = enc.get("type", "")
        if href and (enc_type.startswith("image/") or re.search(r"\.(jpe?g|png|webp)", href, re.IGNORECASE)):
            return href

    # 2. Check media_content
    media_content = getattr(entry, "media_content", []) or []
    for m in media_content:
        url = m.get("url", "")
        if url and (m.get("medium") == "image" or re.search(r"\.(jpe?g|png|webp)", url, re.IGNORECASE)):
            return url

    # 3. Check media_thumbnail
    thumbnails = getattr(entry, "media_thumbnail", []) or []
    for t in thumbnails:
        url = t.get("url", "")
        if url:
            return url

    # 4. Check embedded img in raw description or content
    if raw_html:
        soup = BeautifulSoup(raw_html, "html.parser")
        img = soup.find("img")
        if img and img.get("src"):
            src = img.get("src", "").strip()
            if src.startswith("http") and not any(skip in src.lower() for skip in ["avatar", "favicon", "logo", "tracker", "1x1"]):
                return src

    return None


class RSSCollector:
    def __init__(self, feeds_config_path: str = "config/feeds.yaml"):
        with open(feeds_config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self.feeds = self.config.get("feeds", [])
        self.filter_rules = self.config.get("filter_rules", {})
        self.primary_keywords = [k.lower() for k in self.filter_rules.get("primary_keywords", [])]
        self.exclude_keywords = [k.lower() for k in self.filter_rules.get("exclude_keywords", [])]
        self.topic_keywords = self.filter_rules.get("topic_keywords", {})

    def is_relevant(self, title: str, summary: str) -> bool:
        """Check if an article is relevant to Palestine/Gaza humanitarian reporting."""
        combined = f"{title} {summary}".lower()

        # Check excludes first
        for ex in self.exclude_keywords:
            if re.search(r"\b" + re.escape(ex) + r"\b", combined):
                return False

        # Must have at least one primary keyword
        for pk in self.primary_keywords:
            if re.search(r"\b" + re.escape(pk) + r"\b", combined):
                return True

        return False

    def classify_topic(self, title: str, summary: str) -> str:
        """Classify story into one of the designated topic categories."""
        combined = f"{title} {summary}".lower()
        topic_scores: Dict[str, int] = {}

        for topic, keywords in self.topic_keywords.items():
            score = 0
            for kw in keywords:
                if kw in combined:
                    score += 1
            if score > 0:
                topic_scores[topic] = score

        if topic_scores:
            return max(topic_scores.items(), key=lambda x: x[1])[0]

        return "humanitarian_aid"

    def fetch_feed(self, feed_meta: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fetch and parse a single RSS feed."""
        name = feed_meta.get("name", "Unknown Feed")
        url = feed_meta.get("url")
        if not url:
            return []

        logger.info(f"Fetching feed: {name} ({url})")
        stories: List[Dict[str, Any]] = []

        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=12)
            if resp.status_code != 200:
                logger.warning(f"Feed {name} returned HTTP {resp.status_code}")
                return []

            parsed = feedparser.parse(resp.content)
            for entry in parsed.entries:
                title = clean_html(getattr(entry, "title", ""))
                raw_summary = getattr(entry, "summary", getattr(entry, "description", ""))
                summary = clean_html(raw_summary)
                link = normalize_url(getattr(entry, "link", ""))

                if not title or not link:
                    continue

                if not self.is_relevant(title, summary):
                    continue

                topic = self.classify_topic(title, summary)
                story_id = generate_story_id(link, title)
                published_at = parse_published_date(entry)
                source_image_url = extract_source_image_url(entry, raw_summary)

                stories.append({
                    "story_id": story_id,
                    "title": title,
                    "summary": summary,
                    "canonical_url": link,
                    "source_name": name,
                    "category": feed_meta.get("category", "news"),
                    "reliability_tier": feed_meta.get("reliability_tier", 1),
                    "topic": topic,
                    "published_at_utc": published_at,
                    "source_image_url": source_image_url,
                })

        except Exception as e:
            logger.error(f"Error fetching feed {name}: {e}")

        logger.info(f"Retrieved {len(stories)} relevant stories from {name}")
        return stories

    def collect_all(self) -> List[Dict[str, Any]]:
        """Collect and aggregate stories across all enabled feeds."""
        all_stories: List[Dict[str, Any]] = []
        for feed in self.feeds:
            if feed.get("enabled", True):
                all_stories.extend(self.fetch_feed(feed))
        return all_stories
