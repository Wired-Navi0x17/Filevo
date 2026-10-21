"""
Architectural Audit & Regression Test Suite
Verifies that previously identified failure modes now cleanly pass:
1. Brittle regex intent detection replaced with semantic capability matching.
2. Fragile topic extraction replaced with linguistic subject extraction.
3. Fallback domain hardcoding removed in favor of GENERAL_SCHOLARLY.
4. Unfamiliar topics no longer default to computer science engineering.
"""

from __future__ import annotations

import pytest

from src.docx_creator import parse_document_request
from src.research_engine import extract_topic_from_prompt, is_research_paper_request
from src.universal_synthesizer import detect_domain


class TestIntentAndTopicExtractionAudit:
    """Verifies natural language variations pass cleanly through RequestInterpreter."""

    def test_adjective_separated_report_intent(self):
        prompt = "Write a visual report about kangaroos."
        parsed = parse_document_request(prompt)
        assert parsed.get("is_research") is True
        assert "kangaroo" in parsed.get("title", "").lower()

    def test_polite_request_phrasing(self):
        prompt = "Could you prepare a professional report explaining kangaroo biology?"
        parsed = parse_document_request(prompt)
        assert parsed.get("is_research") is True
        assert "kangaroo" in parsed.get("title", "").lower()

    def test_synonym_verbs_and_descriptors(self):
        prompt = "Produce a comprehensive study of honeybee communication mechanisms"
        parsed = parse_document_request(prompt)
        assert parsed.get("is_research") is True
        assert "honeybee" in parsed.get("title", "").lower()

    def test_topic_extraction_on_indirect_prompt(self):
        prompt = "Research this subject and produce a Word document with relevant images: Ancient Roman Aqueducts"
        topic = extract_topic_from_prompt(prompt)
        assert "aqueducts" in topic.lower()
        assert "this subject" not in topic.lower()


class TestDomainHardcodingAudit:
    """Verifies universal synthesizer domain classification on unfamiliar topics."""

    def test_unfamiliar_humanities_topic_defaults_to_general_scholarly(self):
        topic = "Socio-economic impact of the printing press in renaissance europe"
        domain = detect_domain(topic)
        assert domain != "COMPUTER_SCIENCE_ENGINEERING"
        assert domain == "GENERAL_SCHOLARLY"
