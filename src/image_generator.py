"""Image generator using Pollinations FLUX free endpoint with dignified editorial styling."""

import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, Optional
from urllib.parse import quote

from PIL import Image, ImageDraw, ImageFont
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; PalestineHumanitarianNewsBot/1.0; +https://github.com/Zaryab-dev/palestine-news-ai-bot)"


class ImageGenerator:
    def __init__(
        self,
        model: str = "flux",
        width: int = 1280,
        height: int = 720,
        style_directive: Optional[str] = None,
        timeout: int = 45,
    ):
        self.model = model
        self.width = width
        self.height = height
        self.timeout = timeout
        self.style_directive = style_directive or (
            "Dignified and solemn editorial illustration, fine art watercolor and vector digital art, "
            "warm earth tones, dramatic lighting, focusing on civilian resilience, makeshift tents, and humanitarian assistance. "
            "Strictly NO graphic gore, NO violence, NO blood, 16:9 cinematic framing."
        )

    def sanitize_prompt(self, prompt: str) -> str:
        """Replace sensitive/trigger words in visual prompt with safe dignified editorial terms."""
        substitutions = {
            r"\bgunfire\b": "damaged shelter area",
            r"\bbombing\b": "urban impact scene",
            r"\bairstrike\b": "damaged buildings backdrop",
            r"\bshot\b": "emergency aid area",
            r"\bkilled\b": "humanitarian crisis",
            r"\bmassacre\b": "urgent relief scene",
            r"\bcorpse\b": "aid gathering",
        }
        clean = prompt
        for pattern, replacement in substitutions.items():
            import re
            clean = re.sub(pattern, replacement, clean, flags=re.IGNORECASE)
        return clean

    def generate_image(self, prompt: str, output_path: Path, seed: int = 42) -> bool:
        """
        Request image generation via Pollinations.ai FLUX endpoint and save to output_path.
        Returns True if successful, False otherwise.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        safe_prompt = self.sanitize_prompt(prompt)
        full_prompt = f"{safe_prompt}, {self.style_directive}".strip()
        encoded_prompt = quote(full_prompt)

        models_to_try = [self.model, "turbo"]
        for current_model in models_to_try:
            url = (
                f"https://image.pollinations.ai/prompt/{encoded_prompt}"
                f"?width={self.width}&height={self.height}&model={current_model}&seed={seed}&nologo=true"
            )

            logger.info(f"Generating image via Pollinations [{current_model}]: {output_path.name}")
            try:
                resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=self.timeout)
                if resp.status_code == 200 and len(resp.content) > 5000:
                    with open(output_path, "wb") as f:
                        f.write(resp.content)

                    # Validate that the saved file is a valid readable image
                    with Image.open(output_path) as img:
                        img.verify()

                    logger.info(f"Successfully generated image with {current_model}: {output_path}")
                    time.sleep(1.5)  # Polite pacing between generation requests
                    return True
                else:
                    logger.warning(f"Pollinations [{current_model}] returned HTTP {resp.status_code}")
            except Exception as e:
                logger.warning(f"Image generation with {current_model} failed: {e}")
                time.sleep(1.5)

        logger.error(f"Failed to generate remote image for {output_path.name}")
        return False

    def create_fallback_graphic(self, headline: str, source: str, topic: str, output_path: Path) -> bool:
        """Create a clean, dignified editorial typography card if image API fails."""
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            img = Image.new("RGB", (self.width, self.height), color="#1A1F2C")
            draw = ImageDraw.Draw(img)

            # Elegant accent banner
            draw.rectangle([0, 0, self.width, 16], fill="#007A3D")  # Green accent line
            draw.rectangle([0, self.height - 16, self.width, self.height], fill="#CE1126")  # Red accent line

            # Topic Pill
            topic_clean = topic.replace("_", " ").upper()
            draw.rectangle([80, 80, 360, 130], fill="#263145")
            draw.text((100, 95), f"• {topic_clean}", fill="#48CAE4")

            # Main Headline & Source
            draw.text((80, 200), "PALESTINE HUMANITARIAN MONITOR", fill="#E0E6ED")
            
            # Simple text wrap for headline
            words = headline.split()
            lines = []
            cur_line = []
            for w in words:
                cur_line.append(w)
                if len(" ".join(cur_line)) > 55:
                    lines.append(" ".join(cur_line))
                    cur_line = []
            if cur_line:
                lines.append(" ".join(cur_line))

            y = 280
            for line in lines[:4]:
                draw.text((80, y), line, fill="#FFFFFF")
                y += 50

            draw.text((80, self.height - 100), f"Source: {source} | Verified Reporting", fill="#94A3B8")

            img.save(output_path, "PNG")
            logger.info(f"Created editorial fallback graphic: {output_path}")
            return True
        except Exception as e:
            logger.error(f"Failed creating fallback graphic: {e}")
            return False
