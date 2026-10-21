"""
Generalized Request Interpretation, Capability Dispatch, and Evidence Synthesis Test Suite
Validates:
1. Reusable request interpretation across natural language variations, polite phrasings,
   adjectives, and indirect instructions without regex brittleness.
2. Capability discovery mapping to create_document, classify_files, and browse_web.
3. Spelling tolerance and entity extraction on unfamiliar subjects.
4. General research pipeline grounded in retrieved evidence (no CS equation fallback on humanities).
5. DocumentIR structural integrity, dual rendering consistency, and citation provenance.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from src.capabilities import TaskSpecification, get_capability_registry
from src.document_ir import CitationIR, ClaimIR, DocumentIR, SectionIR
from src.interpreter import get_request_interpreter
from src.research_pipeline import synthesize_evidence_document
from src.docx_creator import create_word_document
from src.ieee_latex_creator import export_to_ieee_latex
from src.universal_synthesizer import detect_domain


class TestUniversalRequestInterpreter:
    """Test suite for RequestInterpreter generalizing across unseen requests."""

    def setup_method(self):
        self.interpreter = get_request_interpreter()

    def test_equivalent_document_requests_generalize(self):
        """Verifies that diverse phrasings are mapped to create_document with correct subject."""
        queries = [
            ("Create a report on kangroo with images.", "kangroo", True),
            ("Write a visual report about kangaroos.", "kangaroos", False),
            ("Could you prepare a professional report explaining kangaroo biology?", "kangaroo biology", False),
            ("Research this subject and produce a Word document with relevant images: Ancient Roman Aqueducts", "Ancient Roman Aqueducts", False),
            ("Make a formal report using credible sources on honeybee communication mechanisms", "honeybee communication mechanisms", False),
        ]

        for query, expected_subject_keyword, expected_wants_images in queries:
            spec = self.interpreter.interpret(query)
            assert spec.action == "create_document", f"Failed for query: {query}"
            assert expected_subject_keyword.lower() in spec.subject.lower(), (
                f"Subject '{spec.subject}' does not contain '{expected_subject_keyword}' for query: {query}"
            )
            if expected_wants_images:
                assert spec.wants_images is True

    def test_file_classification_disambiguation(self):
        """Ensures file classification requests are routed to classify_files, not document creation."""
        classification_queries = [
            "organize my downloads into course folders",
            "sort these scanned documents into calculus and physics",
            "classify this pdf file into proper category",
            "route these files to their respective directories",
        ]
        for q in classification_queries:
            spec = self.interpreter.interpret(q)
            assert spec.action == "classify_files", f"Failed for query: {q}"

    def test_browser_automation_disambiguation(self):
        """Ensures web navigation requests are routed to browse_web."""
        browser_queries = [
            "go to google docs and open a new document",
            "visit slides.new in default browser",
            "take control of my browser and navigate to github",
        ]
        for q in browser_queries:
            spec = self.interpreter.interpret(q)
            assert spec.action == "browse_web", f"Failed for query: {q}"

    def test_conversational_query_does_not_trigger_classification(self):
        """Ensures informational Q&A does not route to file classification."""
        spec = self.interpreter.interpret("what is the difference between supervised and unsupervised learning")
        assert spec.action != "classify_files"
        assert spec.action in ("answer_query", "create_document")


class TestGeneralEvidenceGroundedSynthesis:
    """Validates that research synthesis uses real evidence and avoids domain hardcoding."""

    def test_unfamiliar_humanities_topic_does_not_receive_cs_equations(self):
        """Ensures humanities topic does not default to CS or receive Knuth / CS equations."""
        topic = "Socio-economic impact of the printing press in renaissance europe"
        domain = detect_domain(topic)
        assert domain != "COMPUTER_SCIENCE_ENGINEERING"
        assert domain == "GENERAL_SCHOLARLY"

        spec = TaskSpecification(
            action="create_document",
            subject=topic,
            deliverable_type="research_paper",
            page_count=8,
            wants_images=False,
        )
        doc_ir = synthesize_evidence_document(spec)

        # Validate title and sections
        assert "Printing Press" in doc_ir.title or "Socio-Economic" in doc_ir.title
        assert len(doc_ir.sections) >= 5

        # Validate that NO computer science equations were injected
        all_eqs = [eq.formula for s in doc_ir.sections for eq in s.equations]
        assert not any(r"\mathcal{L}_\theta" in eq for eq in all_eqs)
        assert not any("Psi" in eq for eq in all_eqs)

        # Validate that Knuth / Hopcroft citations were NOT injected
        all_bib_titles = " ".join(c.title for c in doc_ir.bibliography).lower()
        assert "automata theory" not in all_bib_titles
        assert "art of computer programming" not in all_bib_titles

    def test_document_ir_validation_and_dual_rendering(self):
        """Ensures DocumentIR validates cleanly and renders identically to DOCX and LaTeX."""
        doc = DocumentIR(
            title="Systematic Investigation of Hydrothermal Vent Geochemistry",
            subtitle="An Evidence-Grounded Analysis of Abyssal Mineralization",
            abstract="This paper analyzes hydrothermal vent mineralization and redox chemistry in benthic ocean systems.",
            keywords=["Hydrothermal Vents", "Geochemistry", "Abyssal Plain", "Mineralization"],
            doc_type="research_paper",
            sections=[
                SectionIR(
                    heading="I. INTRODUCTION & GEOLOGICAL SCOPE",
                    paragraphs=["Hydrothermal vents represent dynamic interfaces between basaltic crust and cold abyssal ocean water."],
                    claims=[ClaimIR(statement="Interface dynamics between crust and deep ocean.", citation_keys=["vent1"])],
                ),
                SectionIR(
                    heading="II. CHEMICAL PRECIPITATION MECHANISMS",
                    paragraphs=["High-temperature hydrothermal fluids carry dissolved metallic cations and bisulfide complexes."],
                    page_break=True,
                ),
            ],
            bibliography=[
                CitationIR(
                    key="vent1",
                    title="Geochemistry of Hydrothermal Ore Deposits",
                    authors=["H. L. Barnes"],
                    year="1997",
                    source_url="https://doi.org/10.1002/047172517X",
                    doi="10.1002/047172517X",
                    source_type="peer_reviewed",
                )
            ],
        )

        issues = doc.validate()
        assert len(issues) == 0, f"Validation issues found: {issues}"

        legacy_dict = doc.to_legacy_dict()
        with tempfile.TemporaryDirectory() as tmp_dir:
            docx_path = Path(tmp_dir) / "test_doc.docx"
            tex_path = Path(tmp_dir) / "test_doc.tex"

            created_docx = create_word_document(
                title=legacy_dict["title"],
                sections=legacy_dict["sections"],
                output_path=docx_path,
                is_research=True,
                doc_format="ieee",
            )
            assert created_docx.is_file()
            assert created_docx.stat().st_size > 1000

            created_tex = export_to_ieee_latex(legacy_dict, tex_path)
            assert created_tex.is_file()
            tex_content = created_tex.read_text(encoding="utf-8")
            assert "\\documentclass[conference]{IEEEtran}" in tex_content
            assert "Hydrothermal Vent Geochemistry" in tex_content
            assert "Barnes" in tex_content
