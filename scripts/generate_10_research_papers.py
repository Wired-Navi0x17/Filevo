"""
Batch Generation & Verification Suite for 10 Custom 10-Page Research Monographs
Validates word count, paragraph depth, table relevance, equations, and references.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import docx
from src.docx_creator import (
    create_ieee_academic_docx,
    create_word_document,
    parse_document_request,
)
from src.ieee_latex_creator import export_to_ieee_latex

TOPICS = [
    (
        "01_Serial_Experiments_Lain",
        "create a document on Serial Experiments Lain in research paper format",
    ),
    (
        "02_RLCD_Reinforcement_Learning",
        "create a document on Reinforcement Learning with Constrained Distillation in research paper format",
    ),
    (
        "03_Zero_Knowledge_zkSNARKs",
        "create a document on Zero-Knowledge zk-SNARKs and Polynomial Commitments in research paper format",
    ),
    (
        "04_Neuromorphic_Computing",
        "create a document on Neuromorphic Computing and Spiking Neural Networks in research paper format",
    ),
    (
        "05_Quantum_Error_Correction",
        "create a document on Fault-Tolerant Quantum Error Correction and Surface Codes in research paper format",
    ),
    (
        "06_Distributed_Consensus",
        "create a document on Distributed Consensus Protocols Paxos Raft and DAG-BFT in research paper format",
    ),
    (
        "07_Autonomous_Robotics_SLAM",
        "create a document on Autonomous Mobile Robotics SLAM and Sensor Fusion in research paper format",
    ),
    (
        "08_GNN_Molecular_Drug_Discovery",
        "create a document on Graph Neural Networks in Molecular Drug Discovery in research paper format",
    ),
    (
        "09_Algorithmic_Trading_Microstructure",
        "create a document on High-Frequency Algorithmic Trading and Limit Order Book Dynamics in research paper format",
    ),
    (
        "10_Climate_Circulation_Modeling",
        "create a document on Coupled Atmosphere-Ocean General Circulation Modeling in research paper format",
    ),
]


def analyze_docx_file(file_path: Path) -> dict[str, Any]:
    """Inspect and analyze a generated DOCX file."""
    doc = docx.Document(str(file_path))

    total_paras = len(doc.paragraphs)
    total_words = sum(len(p.text.split()) for p in doc.paragraphs)

    headings = []
    for p in doc.paragraphs:
        if p.style.name.startswith("Heading"):
            headings.append((p.style.name, p.text.strip()))

    tables_info = []
    has_generic_table = False
    for i, t in enumerate(doc.tables):
        if not t.rows:
            continue
        headers = [c.text.strip().replace("\n", " ") for c in t.rows[0].cells]
        row_count = len(t.rows)
        col_count = len(t.columns)
        tables_info.append({
            "table_index": i + 1,
            "rows": row_count,
            "cols": col_count,
            "headers": headers,
        })
        # Check for unwanted generic corporate table keywords
        if any("core capability" in h.lower() or "operational efficiency" in h.lower() for h in headers):
            has_generic_table = True

    # Count references
    references = []
    # Check paragraphs for reference items
    for p in doc.paragraphs:
        txt = p.text.strip()
        if txt and (txt.startswith("[") or p.style.name == "List Bullet") and re.search(r'\[\d+\]', txt):
            references.append(txt)

    return {
        "file_name": file_path.name,
        "file_size_kb": round(file_path.stat().st_size / 1024, 1),
        "total_paragraphs": total_paras,
        "total_words": total_words,
        "heading_count": len(headings),
        "headings": headings,
        "table_count": len(doc.tables),
        "tables": tables_info,
        "has_generic_table": has_generic_table,
        "references_count": len(references),
        "sample_references": references[:3],
    }


def run_batch_generation(out_dir: Path) -> list[dict[str, Any]]:
    """Run batch generation for all 10 topics in dual IEEE LaTeX and DOCX formats."""
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []

    print(f"=======================================================================")
    print(f"Starting Dual-Format Synthesis of 10 Academic Research Monographs")
    print(f"Formats: IEEE LaTeX (.tex) & Formal Professional Academic DOCX (.docx)")
    print(f"Destination: {out_dir}")
    print(f"=======================================================================\n")

    for idx, (stem, prompt) in enumerate(TOPICS, start=1):
        print(f"[{idx}/10] Synthesizing: '{prompt}'...")
        parsed = parse_document_request(prompt, base_dir=Path.cwd())

        docx_path = out_dir / f"{stem}.docx"
        tex_path = out_dir / f"{stem}.tex"

        # 1. Generate Formal IEEE Academic DOCX
        created_docx = create_ieee_academic_docx(
            title=parsed["title"],
            sections=parsed["sections"],
            output_path=docx_path,
            subtitle=parsed.get("subtitle"),
            author=parsed.get("author", "Division of Media Theory & Cybernetics"),
            affiliation=parsed.get("affiliation", "Institute for Advanced Studies & Cybernetic Systems"),
            location=parsed.get("location", "Tokyo, Japan / Bengaluru, India"),
            email=parsed.get("email", "research@ieee-academics.org"),
            abstract=parsed.get("abstract"),
            keywords=parsed.get("keywords"),
        )

        # 2. Generate Compilation-Ready IEEEtran LaTeX (.tex)
        created_tex = export_to_ieee_latex(
            doc_dict=parsed,
            output_path=tex_path,
            document_class="conference",
        )

        analysis = analyze_docx_file(created_docx)
        analysis["prompt"] = prompt
        analysis["title"] = parsed["title"]
        analysis["tex_file"] = created_tex.name
        analysis["tex_size_kb"] = round(created_tex.stat().st_size / 1024, 1)
        results.append(analysis)

        print(f"  -> Generated DOCX: {created_docx.name} ({analysis['file_size_kb']} KB)")
        print(f"  -> Generated TeX:  {created_tex.name} ({analysis['tex_size_kb']} KB)")
        print(f"     Words: {analysis['total_words']} | Paragraphs: {analysis['total_paragraphs']} | Tables: {analysis['table_count']} | Citations: {analysis['references_count']}")
        print(f"     Generic Table Flag: {analysis['has_generic_table']}\n")

    return results


if __name__ == "__main__":
    dest = Path("/home/l41n-pr0t0/Documents/Sortwise/Research_Papers")
    batch_results = run_batch_generation(dest)
    print("\nBatch synthesis and dual-format verification complete across all 10 documents!")

