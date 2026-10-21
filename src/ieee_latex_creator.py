"""
IEEE LaTeX Creator Module
Converts structured academic research paper specifications into
compilation-ready IEEEtran-compliant LaTeX (.tex) documents.
Follows official IEEE Conference and Journal formatting standards.
"""

from __future__ import annotations

import glob
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def sanitize_latex(text: str) -> str:
    """
    Escapes special LaTeX characters outside math environments.
    Preserves math delimiters ($ ... $ and $$ ... $$).
    """
    if not text:
        return ""

    # Normalize unicode typographic characters to standard LaTeX ASCII
    text_str = str(text)
    text_str = text_str.replace("\u2013", "--")   # en-dash
    text_str = text_str.replace("\u2014", "---")  # em-dash
    text_str = text_str.replace("\u00a0", " ")    # non-breaking space
    text_str = text_str.replace("\u2018", "'")    # curly single quote
    text_str = text_str.replace("\u2019", "'")
    text_str = text_str.replace("\u201c", "``")   # curly double quote
    text_str = text_str.replace("\u201d", "''")
    text_str = text_str.replace("°", "$^\\circ$") # degree symbol

    # Split by math environments ($...$) to preserve math
    parts = re.split(r'(\$[^$]+\$)', text_str)
    escaped_parts = []
    for part in parts:
        if part.startswith("$") and part.endswith("$"):
            # Inside inline math, preserve LaTeX math syntax
            escaped_parts.append(part)
        else:
            # Outside math: escape %, &, _, #, ~, ^
            s = part
            s = s.replace("\\", "\\textbackslash{}")
            s = s.replace("%", "\\%")
            s = s.replace("&", "\\&")
            s = s.replace("_", "\\_")
            s = s.replace("#", "\\#")
            s = s.replace("~", "\\textasciitilde{}")
            s = s.replace("^", "\\textasciicircum{}")
            # Restore standard quotes (two backticks and two single apostrophes)
            s = re.sub(r'"([^"]+)"', r"``\1''", s)
            # Convert markdown bold and italic formatting to LaTeX commands
            s = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', s)
            s = re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)', r'\\textit{\1}', s)
            escaped_parts.append(s)

    return "".join(escaped_parts)


def export_to_ieee_latex(
    doc_dict: dict[str, Any],
    output_path: str | Path,
    document_class: str = "conference",  # 'conference' or 'journal'
) -> Path:
    """
    Exports a structured research document dictionary into an IEEEtran .tex file.
    Ensures required IEEEtran class and style files exist in the target directory.
    """
    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    # Ensure IEEEtran.cls, cite.sty, and booktabs.sty exist in target directory
    template_dir = Path(__file__).resolve().parent.parent / "assets" / "templates"
    for sty_file in ("IEEEtran.cls", "cite.sty", "booktabs.sty"):
        target_sty = out_file.parent / sty_file
        src_sty = template_dir / sty_file
        if not target_sty.is_file() and src_sty.is_file():
            try:
                shutil.copy2(src_sty, target_sty)
            except Exception:
                pass

    title = doc_dict.get("title", "Research Paper Title")
    subtitle = doc_dict.get("subtitle", "")
    abstract = doc_dict.get("abstract", "")
    keywords = doc_dict.get("keywords", [])
    raw_author = doc_dict.get("author")
    author_name = raw_author if raw_author and raw_author not in ("Division of Media Theory & Cybernetics", "Sortwise") else "[Author Name]"
    raw_aff = doc_dict.get("affiliation")
    affiliation = raw_aff if raw_aff and "Institute for Advanced Studies" not in raw_aff else "[Author Institution / Department]"
    raw_loc = doc_dict.get("location")
    location = raw_loc if raw_loc and "Tokyo" not in raw_loc else "[City, Country]"
    raw_email = doc_dict.get("email")
    email = raw_email if raw_email and "ieee-academics" not in raw_email and "sortwise.local" not in raw_email else "[author@domain.edu]"
    raw_sections = doc_dict.get("sections", [])

    # Extract Abstract & Keywords from sections if not passed at top level
    cleaned_sections = []
    for sec in raw_sections:
        h = sec.get("heading", "")
        if "abstract" in h.lower() and not abstract:
            for p in sec.get("paragraphs", []):
                p_str = str(p)
                if p_str.startswith("**Abstract**—") or p_str.startswith("**Abstract**"):
                    abstract = re.sub(r'^\*\*Abstract\*\*—?\s*', '', p_str).strip()
                elif p_str.startswith("**Keywords:**") and not keywords:
                    k_str = re.sub(r'^\*\*Keywords:\*\*\s*', '', p_str).strip()
                    keywords = [k.strip() for k in k_str.split(",") if k.strip()]
                elif not p_str.startswith("### "):
                    cleaned_sections.append({
                        "heading": "I. INTRODUCTION",
                        "level": 1,
                        "paragraphs": [p_str],
                    })
        else:
            cleaned_sections.append(sec)

    tex_lines = [
        f"\\documentclass[{document_class}]{{IEEEtran}}",
        "\\usepackage{cite}",
        "\\usepackage{amsmath,amssymb,amsfonts}",
        "\\usepackage{graphicx}",
        "\\usepackage{booktabs}",
        "",
        "\\def\\BibTeX{{\\rm B\\kern-.05em{\\sc i\\kern-.025em b}\\kern-.08em",
        "    T\\kern-.1667em\\lower.7ex\\hbox{E}\\kern-.125emX}}",
        "",
        "\\begin{document}",
        "",
    ]

    # Title & Subtitle (Use single clean line break \\ for subtitle)
    if subtitle:
        tex_lines.append(f"\\title{{{sanitize_latex(title)}\\\\ \\large {sanitize_latex(subtitle)}}}")
    else:
        tex_lines.append(f"\\title{{{sanitize_latex(title)}}}")

    # Author Block (Single line break \\ between institution and email)
    tex_lines.extend([
        "",
        "\\author{",
        f"    \\IEEEauthorblockN{{\\textbf{{{sanitize_latex(author_name)}}}}}\\\\",
        f"    \\IEEEauthorblockA{{\\textit{{{sanitize_latex(affiliation)}}}, {sanitize_latex(location)}\\\\Email: {email}}}",
        "}",
        "",
        "\\maketitle",
        "",
    ])

    # Abstract & Keywords
    if abstract:
        tex_lines.extend([
            "\\begin{abstract}",
            sanitize_latex(abstract),
            "\\end{abstract}",
            "",
        ])

    if keywords:
        kw_str = ", ".join(keywords)
        tex_lines.extend([
            "\\begin{IEEEkeywords}",
            f"{kw_str}",
            "\\end{IEEEkeywords}",
            "",
        ])

    # Sections & Body
    sections = cleaned_sections
    sec_roman = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
    sec_counter = 0

    table_counter = 1
    equation_counter = 1
    figure_counter = 1
    bib_items: list[str] = []

    for sec in sections:
        heading = sec.get("heading", "")

        # Check if this is the references section
        if "reference" in heading.lower() or "bibliography" in heading.lower():
            bullets = sec.get("bullets", [])
            for b in bullets:
                bib_items.append(b)
            continue

        # Clean section heading
        clean_h = re.sub(r'^(?:\d+\.\d+|\d+\.0|[I|V|X]+\.)\s*', '', heading).strip()
        lvl = sec.get("level", 1)

        if lvl == 1:
            tex_lines.append(f"\\section{{{sanitize_latex(clean_h)}}}")
            sec_counter += 1
        elif lvl == 2:
            tex_lines.append(f"\\subsection{{{sanitize_latex(clean_h)}}}")
        else:
            tex_lines.append(f"\\subsubsection{{{sanitize_latex(clean_h)}}}")

        # Paragraphs
        for para in sec.get("paragraphs", []):
            if not para:
                continue
            p_text = str(para).strip()
            # If paragraph starts with markdown header, convert to subsection
            if p_text.startswith("### "):
                sub_title = p_text[4:].strip()
                tex_lines.append(f"\\subsection{{{sanitize_latex(sub_title)}}}")
                continue
            if p_text.startswith("**Abstract**") or p_text.startswith("**Keywords:**"):
                continue  # already handled in top block

            # Convert bracket citations [1], [2] to \cite{ref1}, \cite{ref2} if desired or sanitize
            tex_lines.append(sanitize_latex(p_text) + "\n")

        # Equations
        for eq in sec.get("equations", []):
            formulas = eq.get("formulas") or [eq.get("formula", "")]
            expl = eq.get("explanation", "")
            for f in formulas:
                if f:
                    clean_f = f.strip().strip("$")
                    tex_lines.append("\\begin{equation}")
                    tex_lines.append(clean_f)
                    tex_lines.append(f"\\label{{eq:{equation_counter}}}")
                    tex_lines.append("\\end{equation}")
                    equation_counter += 1
            if expl:
                tex_lines.append(f"\\noindent \\textit{{{sanitize_latex(expl)}}}\n")

        # Bullet items
        bullets = sec.get("bullets", [])
        if bullets:
            tex_lines.append("\\begin{itemize}")
            for item in bullets:
                tex_lines.append(f"  \\item {sanitize_latex(str(item))}")
            tex_lines.append("\\end{itemize}\n")

        # Tables (Booktabs style)
        if sec.get("table"):
            t = sec["table"]
            caption = t.get("caption", f"Analytical Data Matrix")
            headers = t.get("headers", [])
            rows = t.get("rows", [])
            if headers:
                if len(headers) == 4:
                    cols_fmt = "p{1.8cm}p{2.2cm}p{1.8cm}p{2.4cm}"
                elif len(headers) >= 3:
                    w_cm = round(8.5 / len(headers), 1)
                    cols_fmt = "".join([f"p{{{w_cm}cm}}"] * len(headers))
                else:
                    cols_fmt = "l" * len(headers)

                tex_lines.extend([
                    "\\begin{table}[!t]",
                    f"\\caption{{{sanitize_latex(caption)}}}",
                    "\\begin{center}",
                    f"\\begin{{tabular}}{{{cols_fmt}}}",
                    "\\toprule",
                    " & ".join([f"\\textbf{{{sanitize_latex(h)}}}" for h in headers]) + " \\\\",
                    "\\midrule",
                ])
                for r in rows:
                    row_cells = [sanitize_latex(str(c)) for c in r]
                    tex_lines.append(" & ".join(row_cells) + " \\\\")
                tex_lines.extend([
                    "\\bottomrule",
                    "\\end{tabular}",
                    f"\\label{{tab:{table_counter}}}",
                    "\\end{center}",
                    "\\end{table}",
                    "",
                ])
                table_counter += 1

        # Figures (Images)
        figs = sec.get("images") or sec.get("figures") or ([sec["image"]] if sec.get("image") else [])
        for fig in figs:
            img_path = fig.get("path") if isinstance(fig, dict) else fig
            caption = fig.get("caption") if isinstance(fig, dict) else f"Illustration for {clean_h}"
            if img_path and Path(img_path).is_file():
                tex_lines.extend([
                    "\\begin{figure}[htbp]",
                    "\\begin{center}",
                    f"\\includegraphics[width=0.48\\textwidth]{{{img_path}}}",
                    f"\\caption{{{sanitize_latex(caption)}}}",
                    f"\\label{{fig:{figure_counter}}}",
                    "\\end{center}",
                    "\\end{figure}",
                    "",
                ])
                figure_counter += 1

    # Bibliography
    if bib_items:
        tex_lines.extend([
            "\\begin{thebibliography}{00}",
        ])
        for idx, item in enumerate(bib_items, start=1):
            clean_item = re.sub(r'^\[\d+\]\s*', '', item).strip()
            tex_lines.append(f"\\bibitem{{ref{idx}}} {sanitize_latex(clean_item)}")
        tex_lines.append("\\end{thebibliography}")

    tex_lines.append("")
    tex_lines.append("\\end{document}")

    out_file.write_text("\n".join(tex_lines), encoding="utf-8")
    return out_file


def find_pdflatex_binary() -> str | None:
    """Locate pdflatex compiler on the host system, including Nix store locations."""
    # 1. System PATH
    found = shutil.which("pdflatex")
    if found:
        return found

    # 2. Search common Nix store paths
    nix_candidates = sorted(glob.glob("/nix/store/*texlive*/bin/pdflatex"), reverse=True)
    for cand in nix_candidates:
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand

    return None


def compile_latex_to_pdf(tex_path: str | Path, timeout: int = 60) -> Path | None:
    """
    Compiles an IEEEtran LaTeX (.tex) document into PDF format using pdflatex.
    Runs pdflatex in nonstopmode to guarantee non-hanging execution.
    """
    tex_file = Path(tex_path).resolve()
    if not tex_file.is_file():
        logger.error("LaTeX file not found: %s", tex_file)
        return None

    compiler = find_pdflatex_binary()
    if not compiler:
        logger.warning("pdflatex compiler not available on system.")
        return None

    # Run pdflatex twice in the document directory to resolve all citations and cross-references
    cmd = [compiler, "-interaction=nonstopmode", "-halt-on-error", tex_file.name]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(tex_file.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
        if proc.returncode == 0:
            # Second pass for bibtex/references
            subprocess.run(
                cmd,
                cwd=str(tex_file.parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout,
            )
            pdf_path = tex_file.with_suffix(".pdf")
            if pdf_path.is_file():
                return pdf_path
        else:
            logger.error("pdflatex failed with return code %d: %s", proc.returncode, proc.stdout[-500:])
    except subprocess.TimeoutExpired:
        logger.error("pdflatex timed out after %ds", timeout)
    except Exception as exc:
        logger.error("Unexpected error compiling LaTeX: %s", exc)

    return None

