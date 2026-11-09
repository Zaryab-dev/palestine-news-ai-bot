"""LLM Writer using Google Gemini Flash (and Groq fallback) with structured JSON output."""

import base64
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior, highly principled international humanitarian correspondent specializing in reporting on Palestine, Gaza, and civilian impact.

Your editorial mandate:
1. Strict Factual Sourcing: State only what is verified in the source information. Directly attribute claims (e.g. "According to UN OCHA...", "Al Jazeera reports...", "WHO warns..."). Never invent casualty counts, quotes, or unverified claims.
2. Humanitarian Focus & Dignity: Humanize the situation by focusing on the plight of innocent civilians, access to clean water, food security, healthcare crises, child education in refugee tents, destroyed infrastructure, and international diplomatic decisions (UN, Washington, international law).
3. X (Twitter) Post Requirements:
   - Must be strictly under 270 characters to leave room for the source URL.
   - Use impactful, clear, professional tone.
   - Include 2-3 standard hashtags: #Gaza #Palestine #HumanitarianCrisis.
4. Editorial Illustration Prompt:
   - Provide a vivid, dignified visual prompt for an editorial image model (FLUX).
   - Style: Full natural, lifelike editorial digital art, authentic natural lighting, realistic atmospheric depth, soft overcast daylight.
   - Composition: Respectfully feature the Palestinian flag (red, black, white, green) displayed on a resilient tent or gently flying above the encampment.
   - Subject: Focus on civilian resilience, humanitarian aid trucks, makeshift classrooms, enduring olive trees with green leaves, water collection lines.
   - ABSOLUTE PROHIBITION: NO blood, NO graphic gore, NO severed bodies, NO weapon close-ups. Focus on dignity and the human condition.

You must respond ONLY with a valid JSON object matching the requested schema. No conversational filler or markdown fences outside the JSON.
"""


def clean_json_response(raw_text: str) -> Dict[str, Any]:
    """Extract and parse JSON from LLM output."""
    raw_text = raw_text.strip()
    if raw_text.startswith("```json"):
        raw_text = raw_text[7:]
    elif raw_text.startswith("```"):
        raw_text = raw_text[3:]
    if raw_text.endswith("```"):
        raw_text = raw_text[:-3]
    return json.loads(raw_text.strip())


class LLMWriter:
    def __init__(
        self,
        provider: str = "gemini",
        gemini_model: str = "gemini-2.5-flash",
        gemini_fallback_model: str = "gemini-1.5-flash",
        groq_model: str = "llama-3.3-70b-versatile",
        temperature: float = 0.2,
    ):
        self.provider = provider
        self.gemini_model = gemini_model
        self.gemini_fallback_model = gemini_fallback_model
        self.groq_model = groq_model
        self.temperature = temperature

        self.gemini_api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        self.groq_api_key = os.environ.get("GROQ_API_KEY", "").strip()

    def generate_post_draft(self, story: Dict[str, Any], batch_id: str) -> Dict[str, Any]:
        """Generate structured post package for a qualified story."""
        # Check if live keys are present, otherwise run deterministic editorial generator
        if self.gemini_api_key:
            try:
                return self._call_gemini(story, batch_id, self.gemini_model)
            except Exception as e:
                logger.warning(f"Gemini {self.gemini_model} failed: {e}. Trying fallback model...")
                try:
                    return self._call_gemini(story, batch_id, self.gemini_fallback_model)
                except Exception as e2:
                    logger.error(f"Gemini fallback failed: {e2}")

        if self.groq_api_key:
            try:
                return self._call_groq(story, batch_id)
            except Exception as e:
                logger.error(f"Groq generation failed: {e}")

        logger.info("No live LLM key detected or all APIs failed; using built-in editorial generator.")
        return self._generate_dry_run_draft(story, batch_id)

    def _fetch_image_inline_data(self, image_url: str) -> Optional[Dict[str, Any]]:
        """Download image from RSS feed and format as base64 inline_data for Gemini Vision."""
        try:
            resp = requests.get(image_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
            if resp.status_code == 200 and 1000 < len(resp.content) < 6 * 1024 * 1024:
                content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
                if not content_type.startswith("image/"):
                    content_type = "image/jpeg"
                b64_data = base64.b64encode(resp.content).decode("utf-8")
                return {
                    "inline_data": {
                        "mime_type": content_type,
                        "data": b64_data,
                    }
                }
        except Exception as e:
            logger.warning(f"Could not load RSS source image for vision analysis ({image_url}): {e}")
        return None

    def _call_gemini(self, story: Dict[str, Any], batch_id: str, model_name: str) -> Dict[str, Any]:
        """Call Google Gemini generateContent REST API with multimodal vision support."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.gemini_api_key}"
        user_prompt = self._build_prompt(story, batch_id)

        parts = []
        source_image_url = story.get("source_image_url")
        if source_image_url:
            img_part = self._fetch_image_inline_data(source_image_url)
            if img_part:
                parts.append(img_part)
                logger.info(f"Attached RSS journalistic photo to Gemini Vision: {source_image_url[:80]}...")

        parts.append({"text": f"{SYSTEM_PROMPT}\n\nTask:\n{user_prompt}"})

        payload = {
            "contents": [
                {"role": "user", "parts": parts}
            ],
            "generationConfig": {
                "temperature": self.temperature,
                "responseMimeType": "application/json",
            },
        }

        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=35)
        if resp.status_code != 200:
            raise RuntimeError(f"Gemini API returned HTTP {resp.status_code}: {resp.text}")

        result_json = resp.json()
        raw_text = result_json["candidates"][0]["content"]["parts"][0]["text"]
        post_data = clean_json_response(raw_text)
        if source_image_url:
            post_data["source_image_url"] = source_image_url
        return post_data

    def _call_groq(self, story: Dict[str, Any], batch_id: str) -> Dict[str, Any]:
        """Call Groq OpenAI-compatible Chat Completions API."""
        url = "https://api.groq.com/openai/v1/chat/completions"
        user_prompt = self._build_prompt(story, batch_id)

        payload = {
            "model": self.groq_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
        }

        headers = {
            "Authorization": f"Bearer {self.groq_api_key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"Groq API returned HTTP {resp.status_code}: {resp.text}")

        raw_text = resp.json()["choices"][0]["message"]["content"]
        return clean_json_response(raw_text)

    def _build_prompt(self, story: Dict[str, Any], batch_id: str) -> str:
        photo_guidance = ""
        if story.get("source_image_url"):
            photo_guidance = (
                "\nREAL JOURNALISTIC PHOTO ATTACHED:\n"
                "- A genuine photojournalist image from this reporting is attached to your input.\n"
                "- Carefully examine its real-world setting, background environment, weather, lighting, canvas/clothing textures, and subjects.\n"
                "- Ground the `image_prompt` in these authentic journalistic visual elements for lifelike realism.\n"
                "- Integrate the Palestinian flag respectfully into the scene.\n"
                "- STRICT FILTER: If the real photo depicts blood, open injuries, or gore, DO NOT include graphic violence. Instead, translate it into solemn, dignified human resilience and natural environmental realism.\n"
            )

        return f"""Analyze this verified news report and produce a JSON post package:

STORY DETAILS:
- Story ID: {story['story_id']}
- Title: {story['title']}
- Sources: {', '.join(story.get('sources', [story.get('primary_source', 'Unknown')]))}
- Primary URL: {story.get('canonical_url')}
- Topic: {story.get('topic')}
- Summary: {story.get('summary')}
- Published at: {story.get('published_at_utc')}
{photo_guidance}
REQUIRED JSON OUTPUT FORMAT:
{{
  "batch_id": "{batch_id}",
  "story_id": "{story['story_id']}",
  "topic": "{story.get('topic', 'humanitarian_aid')}",
  "headline": "Clear, objective, factual headline",
  "source_name": "{story.get('primary_source', 'Humanitarian News')}",
  "source_urls": {json.dumps(story.get('source_urls', [story.get('canonical_url')]))},
  "published_at_utc": "{story.get('published_at_utc')}",
  "source_image_url": {json.dumps(story.get('source_image_url'))},
  "x_post": "Concise post summarizing verified facts with direct source attribution. Max 250 chars. #Gaza #Palestine #HumanitarianCrisis",
  "summary_facts": [
    "Verified point 1 with source reference",
    "Verified point 2 on civilian/infrastructure impact"
  ],
  "image_prompt": "Full natural lifelike editorial depicting [authentic journalistic scene from photo or story], natural soft overcast daylight, featuring Palestinian flag on canvas shelter, olive tree, dignified civilian resilience, no gore, no violence, 16:9 aspect ratio",
  "image_style": "natural_editorial_realism",
  "image_filename": "{story['story_id']}.png",
  "verification_status": "{story.get('verification_status', 'single_source_attributed')}",
  "priority": "{story.get('priority', 'normal')}",
  "review_status": "PENDING_IMAGE"
}}
"""

    def _generate_dry_run_draft(self, story: Dict[str, Any], batch_id: str) -> Dict[str, Any]:
        """Deterministic high-quality fallback generator when no API key is set."""
        headline = story["title"]
        source = story.get("primary_source", "Humanitarian Agency")
        topic = story.get("topic", "humanitarian_aid")
        url = story.get("canonical_url", "")
        source_image_url = story.get("source_image_url")

        # Format concise draft under 260 chars
        summary_snip = story.get("summary", "")[:120].strip()
        if summary_snip and not summary_snip.endswith("."):
            summary_snip += "..."

        x_post = f"Report via {source}: {headline[:130]}. Factual update on civilian & humanitarian impact. #Gaza #Palestine"
        if len(x_post) > 270:
            x_post = x_post[:265] + "..."

        image_prompt = (
            f"Full natural lifelike editorial illustration about {headline[:70]}, authentic overcast daylight, "
            f"displaying Palestinian flag with quiet dignity on a resilient shelter, ancient olive tree, "
            f"focusing on civilian resilience and humanitarian aid, strictly no gore, no violence, 16:9 cinematic framing"
        )

        return {
            "batch_id": batch_id,
            "story_id": story["story_id"],
            "topic": topic,
            "headline": headline,
            "source_name": source,
            "source_urls": story.get("source_urls", [url]),
            "published_at_utc": story.get("published_at_utc"),
            "source_image_url": source_image_url,
            "x_post": x_post,
            "summary_facts": [
                f"Source: {source} reporting on {topic.replace('_', ' ')}.",
                summary_snip or "Factual monitoring report on civilian humanitarian conditions.",
            ],
            "image_prompt": image_prompt,
            "image_style": "natural_editorial_realism",
            "image_filename": f"{story['story_id']}.png",
            "image_status": "SKIPPED",
            "priority": story.get("priority", "normal"),
            "verification_status": story.get("verification_status", "single_source_attributed"),
            "review_status": "PENDING_IMAGE",
        }
