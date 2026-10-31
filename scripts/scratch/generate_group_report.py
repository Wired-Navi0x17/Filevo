#!/usr/bin/env python3
"""Generate the CIE-3 Optimization Report for the full team.

Takes the existing 'report template .docx' from ~/Downloads, updates it with
all four team members in alphabetical order, and writes the final report to
the project output directory.

Team (alphabetical by first name):
    1. Harshul Kala       — 1RUA25CSE0188
    2. Khushi Krishna     — 1RUA25CSE0217
    3. Medha Umesh        — 1RUA25CSE0257
    4. Meghna Pant        — 1RUA25CSE0259
"""

from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────
TEMPLATE = Path.home() / "Downloads" / "report template .docx"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
OUTPUT_FILE = OUTPUT_DIR / "Filevo_Optimization_Report_CIE3.docx"

# ── Team Data (alphabetical order by first name) ───────────────────────
TEAM = [
    ("Harshul Kala",   "1RUA25CSE0188"),
    ("Khushi Krishna", "1RUA25CSE0217"),
    ("Medha Umesh",    "1RUA25CSE0257"),
    ("Meghna Pant",    "1RUA25CSE0259"),
]


def build_submitted_by_text() -> str:
    """Build the 'Submitted by:' block with all team members."""
    lines = ["Submitted by:"]
    for name, usn in TEAM:
        lines.append(f"{name} (USN: {usn})")
    lines.append("School of Computer Science and Engineering, RV University, Bengaluru")
    return "\n".join(lines)


def build_declaration_text() -> str:
    """Build the DECLARATION block listing every member."""
    names_csv = ", ".join(n for n, _ in TEAM)
    names_and = ", ".join(n for n, _ in TEAM[:-1]) + f" and {TEAM[-1][0]}"
    return (
        "DECLARATION:\n"
        f"We, {names_and}, students of 3rd semester B.Tech in Computer Science &amp; Engineering "
        "at the School of Computer Science and Engineering, RV University, hereby declare that the "
        "project work titled &apos;Continuous Optimization via Gradient Descent and Ascent in Machine "
        "Learning&apos; has been independently carried out by us and submitted in partial fulfilment "
        "for the course evaluation during the academic year 2026-2027. The content presented in this "
        "report has not been submitted elsewhere for the award of any degree or diploma."
    )


def build_certificate_text() -> str:
    """Build the CERTIFICATE block listing every member."""
    names_and = ", ".join(n for n, _ in TEAM[:-1]) + f" and {TEAM[-1][0]}"
    usn_block = "; ".join(f"{n} ({u})" for n, u in TEAM)
    return (
        "CERTIFICATE:\n"
        "This is to certify that the project work titled &apos;Continuous Optimization via Gradient "
        "Descent and Ascent in Machine Learning&apos; is performed by "
        f"{usn_block}, "
        "bonafide students of Bachelor of Technology at the School of Computer Science and Engineering, "
        "RV University, Bengaluru, as part of the CIE-3 component for CS2227 AI and ML offered in "
        "Semester III during the Academic Year 2026-2027."
    )


def patch_document_xml(xml: str) -> str:
    """Apply all text replacements on the document.xml content."""

    # ── 1. Fix the 'Submitted by' paragraph ────────────────────────────
    old_submitted = (
        "Submitted by:\n"
        "Harshul Kala (Student ID / USN: 1RVU25CSE000)\n"
        "School of Computer Science and Engineering, RV University, Bengaluru"
    )
    xml = xml.replace(old_submitted, build_submitted_by_text())

    # ── 2. Fix the DECLARATION paragraph ───────────────────────────────
    old_decl_start = "DECLARATION:\nI, Harshul Kala, student of 3rd semester"
    new_decl = build_declaration_text()
    # Find and replace the full declaration paragraph text
    decl_idx = xml.find(old_decl_start)
    if decl_idx != -1:
        # Find the closing </w:t> after this position
        end_tag = "</w:t>"
        end_idx = xml.find(end_tag, decl_idx)
        if end_idx != -1:
            xml = xml[:decl_idx] + new_decl + xml[end_idx:]

    # ── 3. Fix the CERTIFICATE paragraph ───────────────────────────────
    old_cert_start = "CERTIFICATE:\nThis is to certify that the project work"
    new_cert = build_certificate_text()
    cert_idx = xml.find(old_cert_start)
    if cert_idx != -1:
        end_idx = xml.find("</w:t>", cert_idx)
        if end_idx != -1:
            xml = xml[:cert_idx] + new_cert + xml[end_idx:]

    # ── 4. Fix the Submission Date to November 1, 2026 ─────────────────
    xml = xml.replace(
        "Submission Date: October 30, 2026",
        "Submission Date: November 1, 2026",
    )

    # ── 5. Fix single-author references in the rest of the document ────
    # Replace any remaining "Harshul Kala" solo references with team list
    # (only in non-structural locations — the template body text is fine as-is)

    return xml


def generate_report():
    """Read the template, patch team members, and write the output DOCX."""
    if not TEMPLATE.exists():
        raise FileNotFoundError(f"Template not found at {TEMPLATE}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Read all files from the template ZIP
    with zipfile.ZipFile(TEMPLATE, "r") as zin:
        file_contents: dict[str, bytes] = {}
        for name in zin.namelist():
            file_contents[name] = zin.read(name)

    # Patch the document.xml
    doc_xml = file_contents["word/document.xml"].decode("utf-8")
    doc_xml = patch_document_xml(doc_xml)
    file_contents["word/document.xml"] = doc_xml.encode("utf-8")

    # Write the output DOCX
    with zipfile.ZipFile(OUTPUT_FILE, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in file_contents.items():
            zout.writestr(name, data)

    print(f"✅ Report generated: {OUTPUT_FILE}")
    print(f"   File size: {OUTPUT_FILE.stat().st_size:,} bytes")
    print()
    print("   Team members (alphabetical):")
    for name, usn in TEAM:
        print(f"     • {name:<20} {usn}")
    print()
    print(f"   Template source: {TEMPLATE}")

    # Validate
    validate_report(OUTPUT_FILE)


def validate_report(path: Path):
    """Quick validation of the generated DOCX."""
    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(path, "r") as z:
        names = z.namelist()
        required = [
            "[Content_Types].xml",
            "_rels/.rels",
            "word/document.xml",
            "word/styles.xml",
        ]
        for req in required:
            assert req in names, f"Missing required file: {req}"

        # Parse document.xml to ensure valid XML
        doc_xml = z.read("word/document.xml").decode("utf-8")
        ET.fromstring(doc_xml)

        # Verify all team members are present
        for name, usn in TEAM:
            assert name in doc_xml, f"Team member {name} not found in document"
            assert usn in doc_xml, f"USN {usn} not found in document"

        # Verify no placeholder USN remains
        assert "1RVU25CSE000" not in doc_xml, "Placeholder USN still present"

    print("   ✅ Validation passed: XML valid, all members present, no placeholders")


if __name__ == "__main__":
    generate_report()
