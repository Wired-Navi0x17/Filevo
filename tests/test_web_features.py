import pytest
from unittest.mock import patch, MagicMock
from src.web_fetcher import (
    fetch_web_context,
    enrich_sections_with_web_context,
    format_web_chat_response,
)
from src.web_automator import (
    detect_default_browser,
    resolve_site_url,
    resolve_subtask_url,
)


def test_detect_default_browser():
    browser = detect_default_browser()
    assert isinstance(browser, dict)
    assert "name" in browser
    assert "binary" in browser
    assert "type" in browser
    assert browser["name"] in ("Zen Browser", "Mozilla Firefox", "Default Desktop Browser", "Default Browser")


def test_dynamic_site_and_game_resolution():
    # Dynamic resolution without hardcoding
    y8_url = resolve_site_url("y8 games")
    assert "y8.com" in y8_url

    geo_url = resolve_subtask_url("y8 games", "geometry arrow")
    assert "y8.com" in geo_url
    assert "geometry" in geo_url or "search" in geo_url

    # Check general resolution
    gh_url = resolve_site_url("github")
    assert "github.com" in gh_url


def test_enrich_sections_with_web_context():
    initial_sections = [
        {"heading": "Executive Overview", "body": "Initial base text."}
    ]
    web_data = {
        "status": "success",
        "title": "Quantum Physics",
        "summary": "Quantum physics is the study of matter and energy at the most fundamental level.",
        "sources": ["https://en.wikipedia.org/wiki/Quantum_physics", "https://example.com/research"],
    }
    enriched = enrich_sections_with_web_context(initial_sections, web_data)
    assert len(enriched) == 2
    assert "Quantum physics is the study" in enriched[0]["body"]
    assert "Initial base text." in enriched[0]["body"]
    assert enriched[1]["heading"] == "Verified References and Web Sources"
    assert "https://en.wikipedia.org/wiki/Quantum_physics" in enriched[1]["body"]


def test_enrich_sections_when_offline():
    initial_sections = [
        {"heading": "Intro", "body": "Offline notes."}
    ]
    offline_data = {
        "status": "offline",
        "summary": "No live results",
        "sources": [],
    }
    unchanged = enrich_sections_with_web_context(initial_sections, offline_data)
    assert unchanged == initial_sections


def test_format_web_chat_response():
    web_data = {
        "status": "success",
        "title": "Wildlife",
        "summary": "Wildlife refers to undomesticated animal species.",
        "snippets": ["Conservation of habitat is critical."],
        "sources": ["https://en.wikipedia.org/wiki/Wildlife"],
    }
    msg = format_web_chat_response("wildlife", web_data)
    assert "Web Fetch Results: Wildlife" in msg
    assert "Wildlife refers to undomesticated animal species." in msg
    assert "https://en.wikipedia.org/wiki/Wildlife" in msg


def test_web_fetch_live_or_fallback():
    # Test real fetch or graceful offline fallback
    res = fetch_web_context("Wildlife", timeout=3.0)
    assert isinstance(res, dict)
    assert "status" in res
    assert "summary" in res
    assert "sources" in res
    assert res["status"] in ("success", "offline")


def test_parse_automation_intent_google_docs_writing():
    from src.web_automator import parse_automation_intent
    intent = parse_automation_intent("go to google docs online and write i am human")
    assert intent["site_query"] == "google docs"
    assert intent["is_write"] is True
    assert intent["text_to_type"] == "i am human"

    # URL resolution for Google Docs
    url = resolve_site_url("google docs")
    assert "docs.new" in url or "docs.google.com" in url


def test_parse_automation_intent_gameplay():
    from src.web_automator import parse_automation_intent
    intent = parse_automation_intent("launch default browser, open y8 games, find geometry arrow and play it")
    assert intent["site_query"] == "y8 games"
    assert intent["subtask_query"] == "geometry arrow"
    assert intent["is_play"] is True


def test_parse_automation_intent_google_slides_writing():
    from src.web_automator import parse_automation_intent
    intent = parse_automation_intent("go to google slides and write i am human")
    assert intent["site_query"] == "google slides"
    assert intent["is_write"] is True
    assert intent["text_to_type"] == "i am human"

    # URL resolution for Google Slides
    url = resolve_site_url("google slides")
    assert "slides.new" in url or "presentation" in url or "slides" in url


def test_scan_installed_browsers():
    from src.web_automator import scan_installed_browsers
    installed = scan_installed_browsers()
    assert isinstance(installed, list)
    assert len(installed) >= 1
    names = [b["name"] for b in installed]
    # On this NixOS machine, Zen Browser and Firefox are installed
    assert "Zen Browser" in names or "Mozilla Firefox" in names
    # Chrome is not installed on this system
    assert "Google Chrome" not in names


def test_missing_browser_detection():
    from src.web_automator import resolve_target_browser
    # Chrome is not installed
    browser, err = resolve_target_browser("chrome")
    assert browser is None
    assert err is not None
    assert "Google Chrome is not available on this system" in err
    assert "Available browsers:" in err

    # Edge is not installed
    browser_edge, err_edge = resolve_target_browser("edge")
    assert browser_edge is None
    assert "Microsoft Edge is not available on this system" in err_edge

    # Zen is installed
    b_zen, err_zen = resolve_target_browser("zen")
    assert b_zen is not None
    assert err_zen is None
    assert b_zen["name"] == "Zen Browser"

    # Firefox is installed
    b_ff, err_ff = resolve_target_browser("firefox")
    assert b_ff is not None
    assert err_ff is None
    assert b_ff["name"] == "Mozilla Firefox"


def test_parse_automation_intent_arbitrary_topics_and_browser():
    from src.web_automator import parse_automation_intent
    # 1. Arbitrary topic - Quantum Physics
    intent1 = parse_automation_intent("open firefox and go to google slides and create 1st slide for quantum physics")
    assert intent1["requested_browser"] == "firefox"
    assert "slides" in intent1["site_query"]
    assert intent1["text_to_type"] == "Quantum physics"
    assert intent1["is_write"] is True

    # 2. Arbitrary text - Meeting Notes for Project X
    intent2 = parse_automation_intent("go to google docs and write meeting notes for project x")
    assert intent2["text_to_type"] == "meeting notes for project x"
    assert intent2["is_write"] is True

    # 3. Missing browser request - Chrome
    intent3 = parse_automation_intent("open chrome and go to y8 games and play geometry arrow")
    assert intent3["requested_browser"] == "chrome"
    assert "y8" in intent3["site_query"]
    assert intent3["is_play"] is True

    # 4. Direct domain navigation
    intent4 = parse_automation_intent("visit lichess.org and play chess against computer")
    assert intent4["site_query"] == "lichess.org"
    assert intent4["is_play"] is True

    # 5. User prompt: "run firefox and open google docs write a document 3 pages"
    intent5 = parse_automation_intent("run firefox and open google docs write a document 3 pages")
    assert intent5["requested_browser"] == "firefox"
    assert "docs" in intent5["site_query"]
    assert intent5["is_write"] is True

    # 6. Docx request with web info should NOT hallucinate createa.com as site_query
    intent6 = parse_automation_intent("create a docx with proper info on the latest news and recent maths discovery with")
    assert intent6["site_query"] != "create a"
    assert "createa" not in intent6["site_query"]



