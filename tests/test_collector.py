"""Tests for RSS collector cleaning, normalization, and filtering."""

from src.rss_collector import (
    clean_html,
    generate_story_id,
    normalize_url,
    RSSCollector,
)


def test_clean_html():
    raw = "<p>UN OCHA warns that <b>water networks</b> in Gaza are failing.</p>"
    cleaned = clean_html(raw)
    assert cleaned == "UN OCHA warns that water networks in Gaza are failing."


def test_normalize_url():
    url = "https://www.aljazeera.com/news/2026/11/gaza-aid-convoy?utm_source=twitter&utm_medium=social#comments"
    clean = normalize_url(url)
    assert clean == "https://www.aljazeera.com/news/2026/11/gaza-aid-convoy"


def test_generate_story_id_deterministic():
    url = "https://news.un.org/en/story/2026/11/12345"
    title = "WHO delivers emergency supplies to northern Gaza hospitals"
    id1 = generate_story_id(url, title)
    id2 = generate_story_id(url, title)
    assert id1 == id2
    assert len(id1) == 12


def test_relevance_and_topic_classification():
    collector = RSSCollector(feeds_config_path="config/feeds.yaml")

    # Relevant humanitarian story
    title1 = "UNRWA reports acute food and clean water shortages across Deir al-Balah"
    summary1 = "Aid distribution faces severe gridlock as humanitarian corridors remain restricted."
    assert collector.is_relevant(title1, summary1) is True
    assert collector.classify_topic(title1, summary1) == "humanitarian_aid"

    # Relevant healthcare story
    title2 = "Doctors inside Kamal Adwan hospital perform surgeries without anesthesia"
    summary2 = "Medical staff plead for medical aid and emergency fuel."
    assert collector.is_relevant(title2, summary2) is True
    assert collector.classify_topic(title2, summary2) == "healthcare_medical"

    # Irrelevant sports story
    title3 = "Premier League football match highlights and weekend transfers"
    summary3 = "Champions league match review."
    assert collector.is_relevant(title3, summary3) is False
