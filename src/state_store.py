"""State store for tracking processed and pending stories across runs."""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


class StateStore:
    def __init__(self, state_dir: str = "state"):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.processed_path = self.state_dir / "processed_stories.json"
        self.pending_path = self.state_dir / "pending_queue.json"

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def _write_json(self, path: Path, data: Any) -> None:
        temp_path = path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        temp_path.replace(path)

    # Processed stories tracking
    def get_processed_stories(self) -> Dict[str, Dict[str, Any]]:
        """Return dict of {story_id: record}."""
        return self._read_json(self.processed_path, {})

    def is_story_processed(self, story_id: str) -> bool:
        """Check if a story_id has already been processed in any batch."""
        processed = self.get_processed_stories()
        return story_id in processed

    def record_processed_story(
        self,
        story_id: str,
        canonical_url: str,
        headline: str,
        batch_id: str,
        review_status: str = "READY_FOR_REVIEW",
    ) -> None:
        """Mark a story as permanently processed."""
        processed = self.get_processed_stories()
        from datetime import datetime, timezone
        processed[story_id] = {
            "story_id": story_id,
            "canonical_url": canonical_url,
            "headline": headline,
            "batch_id": batch_id,
            "review_status": review_status,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_json(self.processed_path, processed)

    # Pending queue
    def get_pending_queue(self) -> List[Dict[str, Any]]:
        """Get list of stories waiting for batch synthesis."""
        return self._read_json(self.pending_path, [])

    def add_to_pending_queue(self, stories: List[Dict[str, Any]]) -> int:
        """Add stories to pending queue if not already present or processed."""
        processed = self.get_processed_stories()
        current_queue = self.get_pending_queue()
        existing_ids = {s.get("story_id") for s in current_queue}

        added = 0
        for s in stories:
            sid = s.get("story_id")
            if sid and sid not in processed and sid not in existing_ids:
                current_queue.append(s)
                existing_ids.add(sid)
                added += 1

        self._write_json(self.pending_path, current_queue)
        return added

    def pop_pending_batch(self, batch_size: int = 5) -> List[Dict[str, Any]]:
        """Pop up to batch_size stories from the pending queue."""
        queue = self.get_pending_queue()
        if not queue:
            return []
        batch = queue[:batch_size]
        remaining = queue[batch_size:]
        self._write_json(self.pending_path, remaining)
        return batch
