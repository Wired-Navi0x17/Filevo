"""Golden set baseline and regression evaluation harness for Filevo.

Generates a fixed set of documents under reproducible conditions, measures
key document quality metrics (word count, sections, pages, grounding coverage,
8-gram repetition, citation coverage, banned terms, latency), saves the raw
text of each document to /tmp/opencode/eval/<slug>_r<repeat>.txt, and exports a JSON summary.
Supports multi-repeat execution (3 repeats default), separate scoring for
grounded vs ungrounded documents, and redirects docx artifacts to a dedicated output dir.
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

# Ensure NixOS environment is bootstrapped and in testing mode
os.environ["FILEVO_BOOTSTRAPPED"] = "1"
os.environ["FILEVO_TESTING"] = "1"

# Add repository root to Python path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Early native libs preload via package root
import src.doc_gen  # noqa: F401
import src.doc_gen.filevo_cli as cli
from src.doc_gen.docx_renderer import DocxRenderer
from src.doc_gen.wordcraft_engine import WordCraftEngine
from src.doc_gen.filevo_cli import cmd_create, get_corpus, get_llm

BANNED_TERMS = [
    "benthic",
    "pelagic",
    "littoral",
    "marine ecology",
    "furthermore",
    "moreover",
    "in today's fast-paced world",
    "seamless",
    "leverage",
]

GOLDEN_DOCUMENTS = [
    {
        "slug": "plant_root_systems",
        "prompt": "Technical report on plant root systems, 10 pages",
        "target_pages": 10,
        "grounded": True,
    },
    {
        "slug": "plant_classification_history",
        "prompt": "Academic monograph on the history of plant classification, 12 pages",
        "target_pages": 12,
        "grounded": True,
    },
    {
        "slug": "solar_cell_efficiency",
        "prompt": "Engineering guide to solar cell efficiency, 8 pages",
        "target_pages": 8,
        "grounded": False,
    },
]

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def set_reproducible_seed(seed: int = 42) -> None:
    """Set random seeds across standard library, numpy, and torch."""
    import random
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except ImportError:
        pass
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


def extract_text_from_docx(docx_path: str | Path) -> str:
    """Extract plain text from OpenXML docx archive."""
    p = Path(docx_path)
    if not p.exists():
        return ""
    try:
        with zipfile.ZipFile(p, "r") as z:
            if "word/document.xml" not in z.namelist():
                return ""
            xml_content = z.read("word/document.xml")
            tree = ET.fromstring(xml_content)
            paragraphs = []
            for p_elem in tree.findall(f".//{{{W_NS}}}p"):
                texts = [
                    t_elem.text
                    for t_elem in p_elem.findall(f".//{{{W_NS}}}t")
                    if t_elem.text
                ]
                para_text = "".join(texts).strip()
                if para_text:
                    paragraphs.append(para_text)
            return "\n\n".join(paragraphs)
    except Exception as e:
        print(f"Warning: could not parse docx text from {docx_path}: {e}", file=sys.stderr)
        return ""


def compute_metrics(
    doc_text: str,
    result: dict[str, Any],
    duration: float,
    target_pages: int = 10,
) -> dict[str, Any]:
    """Compute all evaluation metrics on generated document text and metadata."""
    # 1. Word Count
    words = doc_text.split()
    word_count = len(words)

    # 2. Section Count
    sections = result.get("sections") or []
    section_count = len(sections)

    # 3. Pages & Budget Adherence
    wc_result = result.get("wc_result")
    if wc_result and getattr(wc_result, "pages", 0) > 0:
        pages = int(wc_result.pages)
    else:
        pages = max(1, math.ceil(word_count / 350))
    budget_adherence = round(pages / target_pages, 3) if target_pages > 0 else 1.0

    # 4. Grounding Coverage
    section_quality = result.get("section_quality") or []
    grounded_sections = [q for q in section_quality if q.get("sources", 0) > 0]
    if grounded_sections:
        mean_grounding_coverage = round(
            sum(q["coverage"] for q in grounded_sections) / len(grounded_sections), 4
        )
    else:
        mean_grounding_coverage = 0.0

    if section_quality:
        coverage_all_sections = round(
            sum(q.get("coverage", 0.0) for q in section_quality) / len(section_quality), 4
        )
    else:
        coverage_all_sections = 0.0

    # 5. 8-Gram Repetition
    tokens = re.findall(r"[a-zA-Z0-9'\-]+", doc_text.lower())
    total_8grams = max(0, len(tokens) - 7)
    if total_8grams > 0:
        ngrams = [tuple(tokens[i : i + 8]) for i in range(total_8grams)]
        unique_8grams = len(set(ngrams))
        repetition_8gram = round(1.0 - (unique_8grams / total_8grams), 4)
    else:
        repetition_8gram = 0.0

    # 6. Citation Coverage
    sentence_candidates = [
        s.strip() for s in re.split(r"(?<=[.!?])\s+", doc_text) if len(s.strip().split()) >= 4
    ]
    total_sentences = len(sentence_candidates)
    cited_sentences = [s for s in sentence_candidates if re.search(r"\[\d+\]", s)]
    citation_coverage = (
        round(len(cited_sentences) / total_sentences, 4) if total_sentences > 0 else 0.0
    )

    # 7. Banned Terms Occurrences
    banned_occurrences: dict[str, int] = {}
    for term in BANNED_TERMS:
        cnt = len(re.findall(rf"{re.escape(term)}", doc_text, re.IGNORECASE))
        banned_occurrences[term] = cnt
    total_banned = sum(banned_occurrences.values())
    banned_occurrences["_total"] = total_banned

    return {
        "word_count": word_count,
        "section_count": section_count,
        "pages": pages,
        "target_pages": target_pages,
        "page_budget_adherence": budget_adherence,
        "mean_grounding_coverage": mean_grounding_coverage,
        "coverage_all_sections": coverage_all_sections,
        "repetition_8gram": repetition_8gram,
        "citation_coverage": citation_coverage,
        "banned_terms": banned_occurrences,
        "generation_seconds": round(duration, 2),
    }


def compute_stats(values: list[float]) -> dict[str, float]:
    """Compute mean, min, max, and range for a list of numeric values."""
    if not values:
        return {"mean": 0.0, "min": 0.0, "max": 0.0, "range": 0.0}
    mean_val = sum(values) / len(values)
    min_val = min(values)
    max_val = max(values)
    return {
        "mean": round(mean_val, 4),
        "min": round(min_val, 4),
        "max": round(max_val, 4),
        "range": round(max_val - min_val, 4),
    }


def run_evaluation(
    model_id: str | None = None,
    save_path: str | Path | None = None,
    eval_dir: str | Path = "/tmp/opencode/eval",
    output_dir: str | Path = "/tmp/opencode/eval/docx",
    repeats: int = 3,
    docs_to_run: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute evaluation over the golden set with multi-repeat statistical tracking."""
    eval_path = Path(eval_dir)
    eval_path.mkdir(parents=True, exist_ok=True)
    out_docx_path = Path(output_dir)
    out_docx_path.mkdir(parents=True, exist_ok=True)

    # Redirect docx output out of ~/.filevo/output to requested clean output dir
    cli._docx_renderer = DocxRenderer(output_dir=str(out_docx_path))
    cli._wordcraft_engine = WordCraftEngine(output_dir=out_docx_path)

    if model_id:
        os.environ["FILEVO_MODEL_ID"] = model_id
        llm = get_llm()
        llm.model_id = model_id
        llm.model = None
        llm.tokenizer = None
        llm._is_loaded = False
    else:
        llm = get_llm()

    # Preload LLM to record baseline model info
    llm.load()
    telemetry = llm.report_model() if hasattr(llm, "report_model") else {}
    device = getattr(llm, "device", "unknown")
    current_model = getattr(llm, "model_id", "unknown")

    docs = docs_to_run or GOLDEN_DOCUMENTS
    doc_results: list[dict[str, Any]] = []
    blind_samples: list[dict[str, Any]] = []

    print(f"\n=======================================================")
    print(f"Filevo Golden Evaluation Harness ({repeats} Repeats)")
    print(f"Model: {current_model} | Device: {device} | Params: {telemetry.get('params', 'N/A')}")
    print(f"VRAM Allocated: {telemetry.get('vram_allocated_mb', 0):.1f} MB | Output Dir: {out_docx_path}")
    print(f"Documents: {len(docs)} | Total Invocations: {len(docs) * repeats}")
    print(f"=======================================================\n")

    for d_idx, doc in enumerate(docs, start=1):
        slug = doc["slug"]
        prompt = doc["prompt"]
        target_pages = doc.get("target_pages", 10)
        is_grounded = doc.get("grounded", True)

        runs: list[dict[str, Any]] = []
        print(f"\n[{d_idx}/{len(docs)}] Document: '{slug}' ({'Grounded' if is_grounded else 'Ungrounded'})")
        print(f"      Prompt: '{prompt}' (Target: {target_pages} pages)")

        for r_idx in range(1, repeats + 1):
            seed = 42 + d_idx * 100 + r_idx * 7
            set_reproducible_seed(seed)

            t0 = time.time()
            res = cmd_create(f"{prompt} --headless")
            duration = time.time() - t0

            docx_path = res.get("doc_path", "") if res else ""
            extracted_text = extract_text_from_docx(docx_path) if docx_path else ""
            if not extracted_text and res and res.get("sections"):
                extracted_text = "\n\n".join(
                    s.get("title", "") + "\n" + s.get("content", "")
                    for s in res["sections"]
                )

            # Save raw text output for each run
            run_file = eval_path / f"{slug}_r{r_idx}.txt"
            with open(run_file, "w", encoding="utf-8") as f:
                f.write(extracted_text)

            run_metrics = compute_metrics(extracted_text, res or {}, duration, target_pages=target_pages)
            run_metrics["repeat"] = r_idx
            run_metrics["seed"] = seed
            run_metrics["docx_path"] = str(docx_path)
            run_metrics["raw_text_path"] = str(run_file)
            runs.append(run_metrics)

            print(
                f"   [r{r_idx}] -> Words: {run_metrics['word_count']} | Pages: {run_metrics['pages']} (adherence: {run_metrics['page_budget_adherence']:.2f}) | "
                f"Cov: {run_metrics['mean_grounding_coverage']:.2f} | "
                f"Rep 8g: {run_metrics['repetition_8gram']:.4f} | "
                f"Time: {run_metrics['generation_seconds']}s"
            )

            # On repeat 1, capture candidate sections for blind reading
            if r_idx == 1 and res and res.get("sections"):
                secs = res["sections"]
                # Grab section 2 (or 1 if short)
                pick_sec = secs[1] if len(secs) > 1 else secs[0]
                blind_samples.append({
                    "model": current_model,
                    "slug": slug,
                    "section_title": pick_sec.get("title", ""),
                    "content": pick_sec.get("content", "")[:1800],
                })

        # Aggregate across repeats for this document
        doc_stats = {
            "slug": slug,
            "prompt": prompt,
            "grounded": is_grounded,
            "target_pages": target_pages,
            "repeats": repeats,
            "word_count": compute_stats([r["word_count"] for r in runs]),
            "pages": compute_stats([r["pages"] for r in runs]),
            "page_budget_adherence": compute_stats([r["page_budget_adherence"] for r in runs]),
            "mean_grounding_coverage": compute_stats([r["mean_grounding_coverage"] for r in runs]),
            "coverage_all_sections": compute_stats([r["coverage_all_sections"] for r in runs]),
            "repetition_8gram": compute_stats([r["repetition_8gram"] for r in runs]),
            "citation_coverage": compute_stats([r["citation_coverage"] for r in runs]),
            "generation_seconds": compute_stats([r["generation_seconds"] for r in runs]),
            "banned_terms_total": sum(r["banned_terms"]["_total"] for r in runs),
            "runs": runs,
        }
        doc_results.append(doc_stats)

    # Separate grounded vs ungrounded aggregates
    grounded_docs = [d for d in doc_results if d["grounded"]]
    ungrounded_docs = [d for d in doc_results if not d["grounded"]]

    def summarize_group(group: list[dict[str, Any]]) -> dict[str, Any]:
        if not group:
            return {}
        n = len(group)
        return {
            "count": n,
            "mean_words": round(sum(d["word_count"]["mean"] for d in group) / n, 1),
            "mean_pages": round(sum(d["pages"]["mean"] for d in group) / n, 2),
            "mean_page_adherence": round(sum(d["page_budget_adherence"]["mean"] for d in group) / n, 3),
            "mean_coverage": round(sum(d["mean_grounding_coverage"]["mean"] for d in group) / n, 4),
            "mean_repetition_8gram": round(sum(d["repetition_8gram"]["mean"] for d in group) / n, 4),
            "mean_seconds_per_doc": round(sum(d["generation_seconds"]["mean"] for d in group) / n, 1),
            "total_seconds": round(sum(sum(r["generation_seconds"] for r in d["runs"]) for d in group), 1),
        }

    grounded_summary = summarize_group(grounded_docs)
    ungrounded_summary = summarize_group(ungrounded_docs)
    overall_summary = summarize_group(doc_results)

    final_report = {
        "timestamp": datetime.datetime.now().isoformat(),
        "model_id": current_model,
        "device": device,
        "telemetry": telemetry,
        "repeats": repeats,
        "grounded_aggregate": grounded_summary,
        "ungrounded_aggregate": ungrounded_summary,
        "overall_aggregate": overall_summary,
        "documents": doc_results,
        "blind_samples": blind_samples,
    }

    # Save blind sample sections for human inspection
    sample_file = eval_path / f"blind_samples_{current_model.replace('/', '_')}.json"
    with open(sample_file, "w", encoding="utf-8") as f:
        json.dump(blind_samples, f, indent=2)

    # Print Formatted Report Table
    print("\n" + "=" * 105)
    print(f"EVALUATION SUMMARY ({current_model}) | {repeats}-Repeat Mean ± Range")
    print("=" * 105)
    print(
        f"{'Document Slug':<28} | {'Type':<9} | {'Words':<13} | {'Pages':<10} | "
        f"{'Adhere':<7} | {'Coverage':<13} | {'Rep 8g':<13} | {'Time (s)':<11}"
    )
    print("-" * 105)
    for d in doc_results:
        g_label = "Grounded" if d["grounded"] else "Unground"
        w_str = f"{d['word_count']['mean']:.0f} ± {d['word_count']['range']:.0f}"
        p_str = f"{d['pages']['mean']:.1f} ± {d['pages']['range']:.0f}"
        adh_str = f"{d['page_budget_adherence']['mean']:.2f}"
        cov_str = f"{d['mean_grounding_coverage']['mean']:.2f} ± {d['mean_grounding_coverage']['range']:.2f}"
        rep_str = f"{d['repetition_8gram']['mean']:.4f} ± {d['repetition_8gram']['range']:.4f}"
        t_str = f"{d['generation_seconds']['mean']:.1f} ± {d['generation_seconds']['range']:.1f}"

        print(
            f"{d['slug']:<28} | {g_label:<9} | {w_str:<13} | {p_str:<10} | "
            f"{adh_str:<7} | {cov_str:<13} | {rep_str:<13} | {t_str:<11}"
        )
    print("-" * 105)
    print(
        f"Grounded Aggregate (n={len(grounded_docs)}):    "
        f"Coverage: {grounded_summary.get('mean_coverage', 0):.4f} | "
        f"Repetition: {grounded_summary.get('mean_repetition_8gram', 0):.4f} | "
        f"Page Adherence: {grounded_summary.get('mean_page_adherence', 0):.2f} | "
        f"Latency: {grounded_summary.get('mean_seconds_per_doc', 0):.1f}s/doc"
    )
    print(
        f"Ungrounded Aggregate (n={len(ungrounded_docs)}):  "
        f"Coverage: {ungrounded_summary.get('mean_coverage', 0):.4f} | "
        f"Repetition: {ungrounded_summary.get('mean_repetition_8gram', 0):.4f} | "
        f"Page Adherence: {ungrounded_summary.get('mean_page_adherence', 0):.2f} | "
        f"Latency: {ungrounded_summary.get('mean_seconds_per_doc', 0):.1f}s/doc"
    )
    print(
        f"Overall Total (n={len(doc_results)}):         "
        f"Total Words: {overall_summary.get('mean_words', 0) * len(doc_results):.0f} | "
        f"Mean Repetition: {overall_summary.get('mean_repetition_8gram', 0):.4f} | "
        f"Total Time: {overall_summary.get('total_seconds', 0):.1f}s"
    )
    print("=" * 105 + "\n")

    if save_path:
        out_file = Path(save_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(final_report, f, indent=2)
        print(f"Full evaluation results saved to: {out_file.resolve()}")

    return final_report


def main():
    parser = argparse.ArgumentParser(description="Filevo Golden Evaluation Harness")
    parser.add_argument("--save", type=str, default=None, help="Path to save output JSON summary")
    parser.add_argument("--model", type=str, default=None, help="Override model ID")
    parser.add_argument("--repeats", type=int, default=3, help="Number of evaluation repeats (default: 3)")
    parser.add_argument("--eval-dir", type=str, default="/tmp/opencode/eval", help="Directory for raw text and samples")
    parser.add_argument("--output-dir", type=str, default="/tmp/opencode/eval/docx", help="Directory for generated docx")
    args = parser.parse_args()

    run_evaluation(
        model_id=args.model,
        save_path=args.save,
        eval_dir=args.eval_dir,
        output_dir=args.output_dir,
        repeats=args.repeats,
    )


if __name__ == "__main__":
    main()
