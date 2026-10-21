"""Tests for the Word document (.docx) creator and LibreOffice CLI integration."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.docx_creator import (
    create_word_document,
    export_chat_to_docx,
    find_soffice_binary,
    generate_gradient_ascent_chart,
    open_in_office,
    parse_document_request,
)
from src.extractors import extract_document


def test_create_word_document_structure():
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "test_notes.docx"
        sections = [
            {
                "heading": "Introduction to Machine Learning",
                "level": 1,
                "paragraphs": [
                    "Supervised learning trains models on labeled input-output pairs.",
                    "Neural networks optimize a loss function via backpropagation.",
                ],
                "bullets": [
                    "Gradient descent with learning rate alpha",
                    "Overfitting prevention using L2 regularization",
                ],
            },
            {
                "heading": "Key Mathematical Concepts",
                "level": 2,
                "paragraphs": ["Cross-entropy loss quantifies divergence."],
                "bullets": ["Binary cross-entropy", "Categorical cross-entropy"],
            },
        ]

        created = create_word_document(
            title="AI & ML Lecture Summary",
            sections=sections,
            output_path=out_path,
            subtitle="CS2227 Notes",
            author="Test User",
            subject="Machine Learning",
        )

        assert created.exists()
        assert created.is_file()
        assert created.stat().st_size > 1000

        # Verify it can be extracted and parsed back cleanly
        edoc = extract_document(str(created))
        assert edoc.file_type == "docx"
        assert "AI & ML Lecture Summary" in edoc.title or "Introduction to Machine Learning" in edoc.headings
        assert "Supervised learning" in edoc.clean_text
        assert "Gradient descent" in edoc.clean_text


def test_export_chat_to_docx():
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "chat_transcript.docx"
        chat_history = [
            {
                "role": "user",
                "content": "Can you analyze this paragraph about Dijkstra and graph shortest path?",
            },
            {
                "role": "model",
                "content": "I evaluated this text using the dual-perspective RLCD engine.",
                "telemetry": {
                    "subject": "CS2000 - Design and Analysis of Algorithms",
                    "confidence": 0.94,
                    "entropy": 0.32,
                    "normalized_entropy": 0.11,
                    "agreement": 0.98,
                    "status": "CONFIDENT",
                },
            },
        ]

        created = export_chat_to_docx(chat_history, out_path)
        assert created.exists()
        assert created.stat().st_size > 1000

        edoc = extract_document(str(created))
        assert "Dijkstra" in edoc.clean_text
        assert "CONFIDENT" in edoc.clean_text


def test_find_soffice_binary_and_open():
    soffice = find_soffice_binary()
    if soffice:
        assert os.path.isfile(soffice)
        assert os.access(soffice, os.X_OK)

    # Test open_in_office with non-existent file returns False
    assert open_in_office("/nonexistent/file.docx") is False

    # Test open_in_office launches background thread without error
    with tempfile.NamedTemporaryFile(suffix=".docx") as tmp:
        with patch("subprocess.Popen") as mock_popen:
            res = open_in_office(tmp.name)
            assert res is True


def test_academic_cie_document_generation():
    """Verify academic CIE report with cover page, declaration, TOC, tables, and figures."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        prompt = (
            "create a docx for continuous internal evaluation report for calculus on "
            "real world optimization using gradient ascent from src/rlcd.py"
        )
        parsed = parse_document_request(prompt, base_dir=Path.cwd())
        assert parsed["cover_page"] is not None
        assert parsed["declaration"] is not None
        assert parsed["table_of_contents"] is True
        assert parsed["lists_of_figures_and_symbols"] is True
        assert len(parsed["sections"]) >= 6

        out_file = Path(tmp_dir) / "academic_cie_report.docx"
        created = create_word_document(
            title=parsed["title"],
            sections=parsed["sections"],
            output_path=out_file,
            cover_page=parsed["cover_page"],
            declaration=parsed["declaration"],
            table_of_contents=parsed["sections"],
            lists_of_figures_and_symbols=True,
        )

        assert created.exists()
        assert created.stat().st_size > 10000

        # Extract and verify sections
        ed = extract_document(str(created))
        text_upper = ed.clean_text.upper()
        assert "CONTINUOUS INTERNAL EVALUATION" in text_upper
        assert "DECLARATION" in text_upper
        assert "1.0 INTRODUCTION" in text_upper
        assert "2.0 THE MODEL" in text_upper
        assert "3.0 METHOD OF SOLUTIONS" in text_upper
        assert "4.0 RESULT AND DISCUSSION" in text_upper
        assert "5.0 CONCLUSION" in text_upper
        assert "GRADIENT ASCENT" in text_upper


def test_finance_domain_document_generation():
    """Verify quantitative finance document with asset allocation and budget tables."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        prompt = "create a docx for financial portfolio optimization and risk allocation with budget tables"
        parsed = parse_document_request(prompt, base_dir=Path.cwd())
        assert len(parsed["sections"]) >= 4

        out_file = Path(tmp_dir) / "finance_portfolio.docx"
        created = create_word_document(
            title=parsed["title"],
            sections=parsed["sections"],
            output_path=out_file,
        )

        assert created.exists()
        ed = extract_document(str(created))
        text_upper = ed.clean_text.upper()
        assert "PORTFOLIO" in text_upper
        assert "SHARPE" in text_upper
        assert "ASSET CLASS" in text_upper


def test_event_club_document_generation():
    """Verify event club proposal with schedule milestones and itemized budget table."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        prompt = "create a docx for annual university hackathon event club proposal with schedule and budget"
        parsed = parse_document_request(prompt, base_dir=Path.cwd())
        assert len(parsed["sections"]) >= 3

        out_file = Path(tmp_dir) / "hackathon_proposal.docx"
        created = create_word_document(
            title=parsed["title"],
            sections=parsed["sections"],
            output_path=out_file,
        )

        assert created.exists()
        ed = extract_document(str(created))
        text_upper = ed.clean_text.upper()
        assert "HACKATHON" in text_upper
        assert "BUDGET" in text_upper
        assert "TIMELINE" in text_upper or "MILESTONE" in text_upper


def test_chart_generation_and_figure_embedding():
    """Verify scientific chart drawing with PIL and embedding into docx."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        chart_p = Path(tmp_dir) / "test_chart.png"
        res = generate_gradient_ascent_chart(chart_p)
        assert res.exists()
        assert res.stat().st_size > 1000

        doc_p = Path(tmp_dir) / "chart_doc.docx"
        created = create_word_document(
            title="Chart Verification",
            sections=[
                {
                    "heading": "Visual Convergence",
                    "level": 1,
                    "paragraphs": ["Demonstration of visual chart embedding."],
                    "image_path": res,
                    "caption": "Figure 1: Mathematical Trajectory",
                }
            ],
            output_path=doc_p,
        )
        assert created.exists()
        assert created.stat().st_size > res.stat().st_size


def test_attachment_handling():
    """Verify attachment parameter ingestion for code and image files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        dummy_code = Path(tmp_dir) / "solver.py"
        dummy_code.write_text(
            "def solve_linear_system(A, b):\n    return np.linalg.solve(A, b)\n",
            encoding="utf-8",
        )

        parsed = parse_document_request(
            "create a docx summarizing this solver",
            base_dir=Path(tmp_dir),
            attachment=dummy_code,
        )
        assert parsed["source_file"] == dummy_code
        assert any("solve_linear_system" in str(s) for s in parsed["sections"])


def test_a4_dimensions_and_academic_typography():
    """Verify document dimensions are A4 and default styling uses Times New Roman."""
    from docx import Document
    from docx.shared import Inches

    with tempfile.TemporaryDirectory() as tmp_dir:
        doc_p = Path(tmp_dir) / "a4_academic_test.docx"
        created = create_word_document(
            title="A4 Formatting Verification",
            sections=[
                {
                    "heading": "1.0 Section One",
                    "level": 1,
                    "paragraphs": ["Paragraph in Times New Roman 12pt with 1.5 line spacing."],
                }
            ],
            output_path=doc_p,
        )

        doc = Document(str(created))
        sec = doc.sections[0]
        # A4 width = 8.27 in (~210mm), height = 11.69 in (~297mm)
        assert abs(sec.page_width.inches - 8.27) < 0.05
        assert abs(sec.page_height.inches - 11.69) < 0.05
        assert abs(sec.left_margin.inches - 1.25) < 0.05
        assert abs(sec.right_margin.inches - 1.00) < 0.05


def test_code_to_math_transpilation_and_equations():
    """Verify AST / regex code transpilation into paper-style mathematical formulas."""
    from src.docx_creator import transpile_code_to_math_formulas

    code = (
        "def update_policy_gradient_ascent(theta, x, action, reward, alpha):\n"
        "    probs = tempered_softmax(theta @ x, temperature=0.15)\n"
        "    js = jensen_shannon_divergence(p, q)\n"
        "    ent = normalized_entropy(probs)\n"
    )
    formulas = transpile_code_to_math_formulas(code)
    assert len(formulas) >= 3

    # Check for gradient ascent and score function
    ascent_f = next((f for f in formulas if "θ_{t+1}" in str(f)), None)
    assert ascent_f is not None
    assert "∇_θ log π_θ" in str(ascent_f)

    # Check for tempered softmax
    softmax_f = next((f for f in formulas if "exp(" in str(f)), None)
    assert softmax_f is not None

    # Check for JSD and entropy
    assert any("D_JS" in str(f) for f in formulas)
    assert any("H_norm" in str(f) for f in formulas)


def test_toc_generation_and_guarded_page_breaks():
    """Verify Table of Contents handles raw sections without printing empty dots lines."""
    from src.docx_creator import build_table_of_contents_page
    from docx import Document

    doc = Document()
    raw_sections = [
        {"heading": "1.0 INTRODUCTION", "level": 1},
        {"heading": "1.1 Mathematical Foundations", "level": 2},
        {"heading": "2.0 THE MODEL", "level": 1},
        {"heading": "APPENDIX: Technical Details", "level": 1},
    ]

    build_table_of_contents_page(doc, raw_sections)

    # Verify paragraphs contain extracted titles and page numbers
    toc_texts = [p.text for p in doc.paragraphs]
    combined_toc = " ".join(toc_texts)
    assert "TABLE OF CONTENTS" in combined_toc
    assert "INTRODUCTION" in combined_toc
    assert "Mathematical Foundations" in combined_toc
    assert "THE MODEL" in combined_toc
    # Ensure no empty dots line (which happened when title was missing)
    for p_txt in toc_texts[1:-1]:
        assert len(p_txt.strip(". ")) > 0
        assert any(c.isalnum() for c in p_txt)


def test_create_docx_of_topic_natural_language():
    """Verify 'create docx of <topic>' parses topic as title and synthesizes multi-section document."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        prompt = "create docx of wildlife"
        parsed = parse_document_request(prompt, base_dir=Path(tmp_dir))
        assert parsed["title"] == "Wildlife"
        assert len(parsed["sections"]) >= 4

        out_file = Path(tmp_dir) / "wildlife.docx"
        created = create_word_document(
            title=parsed["title"],
            sections=parsed["sections"],
            output_path=out_file,
        )
        assert created.exists()
        ed = extract_document(str(created))
        text_upper = ed.clean_text.upper()
        assert "WILDLIFE" in text_upper
        assert "BIODIVERSITY" in text_upper or "ECOLOGICAL" in text_upper
        assert "HABITAT" in text_upper
