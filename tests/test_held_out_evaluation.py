"""
Held-Out Universal Evaluation Suite
Measures:
1. Universal Request Interpretation: Disambiguation across 12 unseen prompt types
   (document creation, file classification, browser navigation, conversational Q&A).
2. Clean Subject Extraction: Tolerating noisy phrasings, polite requests, and compound subjects.
3. Domain Separation & Equation Guard: Guaranteeing zero CS equation leakage into non-CS subjects.
4. Document Quality & Dual Export: Generating valid DocumentIR and rendering identical DOCX + IEEE LaTeX.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from src.capabilities import TaskSpecification, get_capability_registry
from src.document_ir import CitationIR, DocumentIR, SectionIR, TableIR
from src.interpreter import get_request_interpreter
from src.research_pipeline import synthesize_evidence_document
from src.docx_creator import create_word_document
from src.ieee_latex_creator import export_to_ieee_latex
from src.universal_synthesizer import detect_domain


class TestHeldOutInterpretationSuite:
    """Evaluates request interpretation against held-out prompts."""

    def setup_method(self):
        self.interpreter = get_request_interpreter()

    @pytest.mark.parametrize(
        "query,expected_action",
        [
            ("Draft an in-depth academic literature review on CRISPR Cas9 gene therapy", "create_document"),
            ("Please construct an IEEE research paper evaluating solid oxide fuel cell thermodynamics", "create_document"),
            ("Generate an illustrated report about emperor penguin colonies with pictures", "create_document"),
            ("Prepare a technical monograph regarding early bronze age metallurgical techniques", "create_document"),
            ("Organize all the financial receipts in my desktop folder into tax categories", "classify_files"),
            ("Sort these homework assignments into math and physics subdirectories", "classify_files"),
            ("Route incoming medical lab pdfs to their respective clinical archives", "classify_files"),
            ("Classify newly downloaded lecture recordings into semester modules", "classify_files"),
            ("Open Google Chrome and navigate to our internal dashboard", "browse_web"),
            ("Take me to the arxiv repository website and look up recent quantum papers", "browse_web"),
            ("Can you explain how photosynthesis converts solar photon energy into glucose?", "answer_query"),
            ("What are the primary differences between common law and civil law systems?", "answer_query"),
        ],
    )
    def test_held_out_intent_classification(self, query: str, expected_action: str):
        """Verifies zero-shot generalization of capability mapping."""
        spec = self.interpreter.interpret(query)
        assert spec.action == expected_action, f"Failed mapping '{query}': got '{spec.action}', expected '{expected_action}'"

    @pytest.mark.parametrize(
        "query,expected_substring",
        [
            ("Draft an in-depth academic literature review on CRISPR Cas9 gene therapy", "crispr"),
            ("Please construct an IEEE research paper evaluating solid oxide fuel cell thermodynamics", "fuel cell"),
            ("Generate an illustrated report about emperor penguin colonies with pictures", "emperor penguin"),
            ("Prepare a technical monograph regarding early bronze age metallurgical techniques", "metallurgical"),
        ],
    )
    def test_held_out_subject_extraction(self, query: str, expected_substring: str):
        """Verifies clean extraction of domain subjects from varied linguistic structures."""
        extracted = self.interpreter.extract_subject(query).lower()
        assert expected_substring in extracted, f"Subject '{extracted}' missed expected '{expected_substring}' in '{query}'"


class TestDomainSeparationAndSynthesisIntegrity:
    """Ensures domain integrity and absence of synthetic or hardcoded artifacts."""

    @pytest.mark.parametrize(
        "topic",
        [
            "Solid Oxide Fuel Cell Thermodynamics",
            "Early Bronze Age Metallurgical Techniques",
            "Avian Navigation and Quantum Cryptochrome Magnetoreception",
            "Socio-economic impact of the printing press in renaissance europe",
        ],
    )
    def test_domain_separation_prevents_cs_fallback(self, topic: str):
        """Verifies that non-CS subjects are never classified as COMPUTER_SCIENCE_ENGINEERING."""
        domain = detect_domain(topic)
        assert domain != "COMPUTER_SCIENCE_ENGINEERING", f"Non-CS topic '{topic}' fell back to CS domain"

    def test_non_cs_document_has_no_cs_equation_leakage(self):
        """Synthesizes a document on ancient civil engineering and ensures 0 CS equations or citations."""
        topic = "Hydraulic Engineering of Ancient Roman Aqueducts"
        spec = TaskSpecification(
            action="create_document",
            subject=topic,
            deliverable_type="research_paper",
            page_count=6,
            wants_images=False,
        )
        doc_ir = synthesize_evidence_document(spec)

        # Title check
        assert "Roman Aqueduct" in doc_ir.title or "Hydraulic Engineering" in doc_ir.title

        # Check all formulas across all sections
        for sec in doc_ir.sections:
            for eq in sec.equations:
                for f in (eq.formulas or [eq.formula]):
                    assert r"\mathcal{L}_\theta" not in f, f"CS loss found in Roman aqueduct paper: {f}"
                    assert r"\nabla_\theta" not in f, f"Policy gradient found in Roman aqueduct paper: {f}"
                    assert r"D_{KL}" not in f, f"KL divergence found in Roman aqueduct paper: {f}"

        # Check bibliography
        bib_text = " ".join(c.title.lower() for c in doc_ir.bibliography)
        assert "art of computer programming" not in bib_text
        assert "pattern recognition and machine learning" not in bib_text
        assert "serial experiments lain" not in bib_text

    def test_held_out_dual_format_export(self):
        """Verifies that an unfamiliar topic produces valid, non-empty DOCX and IEEE LaTeX files."""
        topic = "Avian Navigation and Quantum Cryptochrome Magnetoreception"
        spec = TaskSpecification(
            action="create_document",
            subject=topic,
            deliverable_type="research_paper",
            page_count=8,
            wants_images=False,
        )
        doc_ir = synthesize_evidence_document(spec)
        assert len(doc_ir.sections) >= 5
        assert len(doc_ir.bibliography) >= 1

        validation_errors = doc_ir.validate()
        assert not validation_errors, f"Validation errors: {validation_errors}"

        doc_dict = doc_ir.to_legacy_dict()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            docx_file = tmp_path / "Avian_Navigation.docx"
            tex_file = tmp_path / "Avian_Navigation.tex"

            created_docx = create_word_document(
                title=doc_dict["title"],
                sections=doc_dict["sections"],
                output_path=docx_file,
                subtitle=doc_dict.get("subtitle"),
                author=doc_dict.get("author", "Sortwise"),
                is_research=True,
                doc_format="ieee",
            )
            assert created_docx.is_file()
            assert created_docx.stat().st_size > 10000

            created_tex = export_to_ieee_latex(doc_dict, tex_file)
            assert created_tex.is_file()
            assert created_tex.stat().st_size > 2000

            tex_str = created_tex.read_text(encoding="utf-8")
            assert "\\documentclass[conference]{IEEEtran}" in tex_str
            assert "\\begin{thebibliography}" in tex_str
            assert "\\begin{table}" in tex_str
            assert "\\toprule" in tex_str
