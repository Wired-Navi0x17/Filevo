"""Verification of domain-authentic titles, outlines, and content generation for arbitrary topics."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest
from src.doc_gen.document_brief import DocumentPlan, DocumentBrief, PLACEHOLDER_BLACKLIST
from src.doc_gen.docx_renderer import DocxRenderer


class TestDomainGeneralization(unittest.TestCase):
    def test_humanities_topic_sections_and_title(self):
        """Verify that a humanities topic (Renaissance Art) receives authentic title and sections."""
        brief = DocumentBrief.from_request("comprehensive study on Renaissance Art and Humanism")
        
        # 1. Title must be proper and grounded in Renaissance Art
        self.assertNotIn(brief.title.lower(), PLACEHOLDER_BLACKLIST)
        self.assertIn("renaissance art", brief.title.lower())
        self.assertNotIn("technical report on", brief.title.lower())
        self.assertNotIn("academic monograph: theoretical and empirical analysis of", brief.title.lower())

        # 2. Sections must be authentic humanities/arts sections
        headings = [s.heading for s in brief.sections]
        self.assertGreaterEqual(len(headings), 4)
        
        # Must NOT have generic software engineering headings
        for forbidden in ("Technical Architecture and Core Components", "Implementation Methodology and Workflows", "Sensor Acquisition"):
            self.assertNotIn(forbidden, headings)
            
        # Must have cultural/historical/thematic concepts
        headings_str = " ".join(headings).lower()
        self.assertTrue(any(w in headings_str for w in ("history", "cultural", "context", "foundations", "principles", "movements", "innovations", "perspectives", "legacy")))

    def test_quantum_physics_topic_sections(self):
        """Verify that a physics topic (Quantum Error Correction) receives scientific physical sections."""
        brief = DocumentBrief.from_request("technical report on Quantum Error Correction")
        
        self.assertIn("quantum error correction", brief.title.lower())
        headings = [s.heading for s in brief.sections]
        headings_str = " ".join(headings).lower()
        
        # Must NOT have feline or biology headings
        self.assertNotIn("felis", headings_str)
        self.assertNotIn("feline", headings_str)
        self.assertNotIn("taurine", headings_str)
        
        # Must have physical science concepts
        self.assertTrue(any(w in headings_str for w in ("theoretical", "physical", "phenomenological", "experimental", "quantum", "benchmarks", "efficiency")))

    def test_biological_topic_without_hardcoded_feline_cheat(self):
        """Verify that biological topics (including cats or plants) receive natural science sections dynamically without hardcoded cheats."""
        brief_cat = DocumentBrief.from_request("study on Feline Biology and Domestication")
        self.assertIn("feline biology", brief_cat.title.lower())
        
        headings = [s.heading for s in brief_cat.sections]
        headings_str = " ".join(headings).lower()
        
        # Sections should be natural biological sections
        self.assertTrue(any(w in headings_str for w in ("evolutionary", "taxonomic", "anatomical", "ecological", "behavioral", "overview")))
        # Must not have IT systems boilerplate
        self.assertNotIn("Technical Architecture and Core Components", headings)
        self.assertNotIn("Problem Formulation and System Scope", headings)

    def test_fallback_prose_avoids_it_jargon_for_humanities(self):
        """Verify that fallback prose for non-IT topics contains zero IT systems engineering jargon."""
        from src.doc_gen.llm_client import LocalTransformersClient
        client = LocalTransformersClient()
        
        brief = DocumentBrief.from_request("monograph on Renaissance Art")
        prose = client.generate_section_content(
            section_title="Historical Context and Cultural Foundations",
            doc_title=brief.title,
            archetype=brief.genre,
            brief=brief,
        )
        
        prose_lower = prose.lower()
        # Verify absence of leaked IT systems jargon
        for forbidden in (
            "deterministic state transitions",
            "cross-functional diagnostics",
            "operational stress regimes",
            "subsystem telemetry",
            "optical gate",
            "interrupt service routines",
        ):
            self.assertNotIn(forbidden, prose_lower)
            
        # Verify presence of analytical scholarly prose
    def test_plan_topic_sections_heading_prefix_cleanup(self):
        """Verify that plan_topic_sections strips leading Section/Chapter prefixes."""
        import json
        from unittest.mock import MagicMock
        from src.doc_gen.llm_client import LocalTransformersClient

        client = LocalTransformersClient()
        client._is_loaded = True
        client.model = MagicMock()
        client.tokenizer = MagicMock()
        
        # Simulate LLM output returning numbered sections
        raw_json_response = json.dumps([
            {"heading": "Section 1: Renaissance Art and Humanism", "purpose": "Intro"},
            {"heading": "Chapter 2 - Key Principles of Renaissance Art", "purpose": "Principles"},
            {"heading": "Part 3: Humanism in Renaissance Art", "purpose": "Humanism"},
            {"heading": "Impact of Renaissance Art on Society", "purpose": "Impact"},
        ])
        
        client.tokenizer.decode.return_value = raw_json_response
        class MockBatch(dict):
            pass
        batch = MockBatch()
        input_ids_mock = MagicMock()
        input_ids_mock.shape = [1, 10]
        batch["input_ids"] = input_ids_mock
        batch.input_ids = input_ids_mock
        mock_to = MagicMock()
        mock_to.to.return_value = batch
        client.tokenizer.return_value = mock_to
        client.model.generate.return_value = [[0] * 20]
        
        sections = client.plan_topic_sections("Renaissance Art", "Academic Monograph")
        self.assertEqual(len(sections), 4)
        self.assertEqual(sections[0]["heading"], "Renaissance Art and Humanism")
        self.assertEqual(sections[1]["heading"], "Key Principles of Renaissance Art")
        self.assertEqual(sections[2]["heading"], "Humanism in Renaissance Art")
        self.assertEqual(sections[3]["heading"], "Impact of Renaissance Art on Society")


if __name__ == "__main__":
    unittest.main()

