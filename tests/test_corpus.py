#!/usr/bin/env python3
"""Corpus store tests: chunking, retrieval, provenance and citation safety.

Run with: python3 tests/test_corpus.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.doc_gen.corpus_store import (  # noqa: E402
    CorpusStore,
    build_context_block,
    chunk_text,
    license_for_url,
    normalize_whitespace,
    sanitize_citation_markers,
)
from src.doc_gen.filevo_cli import _split_ingest_targets  # noqa: E402

PASSED = 0
FAILED = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"✓ {name} passed")
    else:
        FAILED += 1
        print(f"✗ {name} FAILED {detail}")


SAMPLE_ROOT = """Roots are the underground organs of vascular plants that absorb water and minerals while providing mechanical stability.
== Types of roots ==
Taproots are a single dominant root from which smaller lateral roots branch deeply into subterranean soils. Fibrous roots form a dense mat of similarly sized roots, typical of monocot grasses and shallow vegetation. Adventitious roots arise from non-root tissues such as stems or leaves rather than from embryonic radicles, providing specialized structural support and vegetative propagation capabilities across diverse soil environments.
== Anatomy ==
Root morphology is systematically divided into four distinct developmental zones: the protective root cap, the active apical meristem, the rapid elongation zone, and the specialized maturation zone. Water and dissolved mineral nutrients enter through microscopic root hairs, which greatly increase the absorptive surface area of the epidermal cellular layer while facilitating mycorrhizal fungal associations with beneficial soil microbiota.
== External links ==
Index Nominum Algarum. A searchable database of algal names.
Some unrelated directory listing that must never be retrieved.
== Primary functions ==
Anchorage and mechanical support represent primary ecological functions of underground root systems. Roots firmly fix the vegetative plant body in the substrate and resist the physical leverage of wind and surface precipitation acting on the aerial shoot system above ground, while storing vital biochemical reserves and synthesizing essential growth regulators.
"""

SAMPLE_DISAMBIGUATION = """Solar may refer to:

== Astronomy ==
Of or relating to the Sun.
Solar telescope, a special purpose telescope used to observe the Sun.
A device that utilizes solar energy (e.g. "solar panels").
Solar calendar, a calendar whose dates indicate the position of the Earth.
Solar eclipse, an eclipse of a sun in which it is obstructed by the moon.
Solar System, the planetary system made up by the Sun and the objects orbiting it.
"""


def test_chunking():
    chunks = chunk_text(SAMPLE_ROOT, target_words=40)
    check("chunking produces chunks", len(chunks) >= 3, f"got {len(chunks)}")
    headings = {h for h, _ in chunks}
    check("headings attach to chunks", "Types of roots" in headings, str(headings))
    joined = " ".join(text for _, text in chunks)
    check(
        "boilerplate sections excluded",
        "Index Nominum Algarum" not in joined and "directory listing" not in joined,
    )
    orphan = "Short isolated paragraph that has only twenty five words in total and must therefore be excluded from becoming an independent chunk in our system. Right."
    orphan_chunks = chunk_text(orphan)
    check("short orphan paragraph omitted", len(orphan_chunks) == 0, f"got {len(orphan_chunks)}")


def test_normalize():
    from src.doc_gen.document_brief import clean_subject

    check(
        "double commas collapsed",
        normalize_whitespace("Encyclopedia Of Plants,, Every Group,") == "Encyclopedia Of Plants, Every Group",
        normalize_whitespace("Encyclopedia Of Plants,, Every Group,"),
    )
    check(
        "trailing separator removed",
        not normalize_whitespace("Root Systems,").endswith(","),
    )
    check(
        "clean_subject trailing comma removed",
        clean_subject("Root Systems, ") == "Root Systems",
        clean_subject("Root Systems, "),
    )
    check(
        "clean_subject double commas collapsed",
        clean_subject("Encyclopedia of Plants,, Every Group,") == "Encyclopedia of Plants, Every Group",
        clean_subject("Encyclopedia of Plants,, Every Group,"),
    )


def test_topic_splitting():
    check(
        "solar cells kept as single target",
        _split_ingest_targets("solar cells") == ["solar cells"],
        str(_split_ingest_targets("solar cells")),
    )
    check(
        "comma separated topics split",
        _split_ingest_targets("Plant, Root, Flower") == ["Plant", "Root", "Flower"],
        str(_split_ingest_targets("Plant, Root, Flower")),
    )
    check(
        "space separated URLs split",
        _split_ingest_targets("https://en.wikipedia.org/wiki/A https://en.wikipedia.org/wiki/B")
        == ["https://en.wikipedia.org/wiki/A", "https://en.wikipedia.org/wiki/B"],
    )


def test_licenses():
    check(
        "wikipedia licence detected",
        "CC BY-SA" in license_for_url("https://en.wikipedia.org/wiki/Plant"),
    )
    check(
        "arxiv flagged as per-paper",
        "per-paper" in license_for_url("https://arxiv.org/abs/2301.00001"),
    )
    check("unknown domain reported honestly", license_for_url("https://example.org/x") == "unknown")


def test_citations():
    text = "Taproots are dominant [1]. This is unsupported [7]. Also see [2]."
    cleaned, used = sanitize_citation_markers(text, valid=2)
    check("invented citation stripped", "[7]" not in cleaned, cleaned)
    check("valid citations retained", "[1]" in cleaned and "[2]" in cleaned)
    check("used list reports only valid", used == [1, 2], str(used))
    check("out-of-range marker cannot leak", "[9]" not in sanitize_citation_markers("x [9]", 3)[0])


def test_disambiguation():
    with tempfile.TemporaryDirectory() as tmp:
        store = CorpusStore(storage_dir=tmp)
        res_disambig = store.ingest_document(
            url="https://en.wikipedia.org/wiki/Solar",
            text=SAMPLE_DISAMBIGUATION,
            title="Solar",
        )
        check("disambiguation page skipped", res_disambig.status == "skipped", res_disambig.status)
        check("disambiguation message noted", "disambiguation" in res_disambig.message, res_disambig.message)

        res_legit = store.ingest_document(
            url="https://en.wikipedia.org/wiki/Root",
            text=SAMPLE_ROOT,
            title="Root",
        )
        check("legitimate article ingested", res_legit.status == "ingested", res_legit.status)
        store.close()


def test_store_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        store = CorpusStore(storage_dir=tmp)
        result = store.ingest_document(
            url="https://en.wikipedia.org/wiki/Root",
            text=SAMPLE_ROOT * 3,
            title="Root",
        )
        check("ingest reports success", result.status == "ingested", result.message)
        check("chunks stored", result.chunks > 0, str(result.chunks))

        again = store.ingest_document(
            url="https://en.wikipedia.org/wiki/Root",
            text=SAMPLE_ROOT * 3,
            title="Root",
        )
        check("unchanged source skipped by hash", again.status == "skipped", again.status)

        hits = store.retrieve("taproots and fibrous root systems", k=3)
        check("retrieval returns hits", len(hits) > 0)
        check(
            "retrieval finds the relevant heading",
            any("Types of roots" in h["heading_path"] for h in hits),
            str([h["heading_path"] for h in hits]),
        )
        check(
            "hits carry provenance",
            all(h["url"] and h["license"] and h["fetched_at"] for h in hits),
        )
        check(
            "boilerplate never retrieved",
            all("Index Nominum" not in h["text"] for h in hits),
        )

        block = build_context_block(hits[:2])
        check("context block numbers sources", "[1]" in block and "[2]" in block)

        coverage = store.grounding_coverage(
            "Taproots are a single dominant root. Fibrous roots form a dense mat.", hits
        )
        check("coverage is a fraction", 0.0 <= coverage["coverage"] <= 1.0, str(coverage))
        check("coverage method reported", coverage["method"] in ("embedding", "lexical"))

        stats = store.profile()
        check("profile counts sources", stats["sources"] == 1, str(stats["sources"]))
        check("manifest written", (Path(tmp) / "sources.json").exists())
        store.close()


def test_empty_store():
    with tempfile.TemporaryDirectory() as tmp:
        store = CorpusStore(storage_dir=tmp)
        check("empty store returns no hits", store.retrieve("anything") == [])
        check("empty profile reports zero sources", store.profile()["sources"] == 0)
        check(
            "coverage is zero without sources",
            store.grounding_coverage("Some sentence here.", [])["coverage"] == 0.0,
        )
        store.close()


def main() -> int:
    test_chunking()
    test_normalize()
    test_topic_splitting()
    test_licenses()
    test_citations()
    test_disambiguation()
    test_store_roundtrip()
    test_empty_store()
    print(f"\n{PASSED} passed, {FAILED} failed")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
