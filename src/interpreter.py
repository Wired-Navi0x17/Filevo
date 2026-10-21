"""
Universal Request Interpretation Layer
Translates natural language user requests into structured TaskSpecifications
using classical linguistic analysis and local dense semantic embeddings.
Replaces brittle regex keyword matching with capability-aligned semantic matching.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import numpy as np

from src.capabilities import (
    CapabilityRegistry,
    TaskSpecification,
    get_capability_registry,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Linguistic Tokenization & Stop-Phrase Stripping
# --------------------------------------------------------------------------- #

_POLITE_PREFIXES = [
    r"^(?:could|can|would|will)\s+you\s+(?:please\s+)?(?:kindly\s+)?",
    r"^(?:please\s+)?(?:i\s+(?:would\s+like|want|need)\s+(?:you\s+to\s+)?(?:a\s+)?)?",
    r"^(?:help\s+me\s+)?(?:to\s+)?",
]

_CREATION_VERBS = {
    "create", "make", "generate", "build", "write", "draft", "prepare",
    "produce", "compile", "compose", "synthesize", "author", "develop",
}

_DOCUMENT_NOUNS = {
    "report", "paper", "document", "docx", "word", "study", "monograph",
    "article", "review", "thesis", "dissertation", "overview", "monograph",
}

_CLASSIFICATION_VERBS = {
    "organize", "sort", "classify", "categorize", "route", "group", "arrange", "file", "tidy",
}

_BROWSER_VERBS = {
    "open", "launch", "visit", "navigate", "browse", "automate", "play", "run",
}

_IMAGE_DIRECTIVES = re.compile(
    r"\b(?:with|having|including|containing|plus)\s+(?:images?|photos?|pictures?|figures?|diagrams?|visuals?)\b",
    re.IGNORECASE,
)

_FORMAT_DIRECTIVES = re.compile(
    r"\b(?:in\s+)?(?:word|docx?|document|docs?|latex|tex|ieee|pdf)\s+(?:format|type|style)?\b",
    re.IGNORECASE,
)

_PAGE_DIRECTIVES = re.compile(
    r"\b(?:number\s+of\s+pages|page\s+count|pages?)\s*(?:being|is|:|=|of)?\s*(\d+)\b|\b(\d+)\s*pages?\b",
    re.IGNORECASE,
)


class RequestInterpreter:
    """Interprets free-form requests against registered tool capabilities."""

    def __init__(self, registry: CapabilityRegistry | None = None) -> None:
        self.registry = registry or get_capability_registry()
        self._model = None

    def _get_embedding_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception as exc:
                logger.warning("Could not load sentence transformer: %s", exc)
                self._model = None
        return self._model

    def extract_subject(self, prompt: str) -> str:
        """
        Extract the core subject, entity, or search topic from natural language,
        stripping polite prefixes, creation verbs, and formatting modifiers.
        """
        text = prompt.strip()

        # 1. Quoted subject takes highest priority
        quote_match = re.search(r'["\']([^"\']+)["\']', text)
        if quote_match:
            cand = quote_match.group(1).strip()
            if cand and not any(cand.lower() == k for k in ("report", "paper", "document", "docx")):
                return cand

        # 2. Strip polite request prefixes
        clean = text
        for pat in _POLITE_PREFIXES:
            clean = re.sub(pat, "", clean, flags=re.IGNORECASE).strip()

        # 3. Strip formatting, image, and page directives
        clean = _IMAGE_DIRECTIVES.sub("", clean).strip()
        clean = _PAGE_DIRECTIVES.sub("", clean).strip()
        clean = re.sub(r"\b(?:using|with)\s+credible\s+sources\b", "", clean, flags=re.IGNORECASE).strip()

        # 4. Pattern: <Verb> [a/an] [Adjectives...] <DocumentNoun> [of/on/about/explaining/regarding] <Subject>
        verb_noun_pattern = re.search(
            r"^(?:" + "|".join(_CREATION_VERBS) + r")\s+(?:(?:a|an|the|me|us)\s+)?(?:[a-zA-Z_\-]+\s+){0,3}(?:"
            + "|".join(_DOCUMENT_NOUNS)
            + r")\s+(?:of|on|about|explaining|regarding|for|into)\s+(.+)$",
            clean,
            re.IGNORECASE,
        )
        if verb_noun_pattern:
            cand = verb_noun_pattern.group(1).strip()
            cand = _FORMAT_DIRECTIVES.sub("", cand).strip()
            if cand:
                return cand

        # 5. Pattern: "Research this subject ... : <Subject>" or "Subject being <Subject>"
        colon_pattern = re.search(r"[:\-–]\s*([a-zA-Z0-9_\- ]+)$", clean)
        if colon_pattern:
            cand = colon_pattern.group(1).strip()
            if len(cand.split()) <= 8:
                return cand

        # 6. Fallback: Strip leading verbs and document nouns
        words = clean.split()
        idx = 0
        while idx < len(words) and words[idx].lower() in (
            _CREATION_VERBS | _DOCUMENT_NOUNS | {"a", "an", "the", "on", "of", "about", "for", "explaining", "regarding", "formal", "visual", "professional", "custom", "new"}
        ):
            idx += 1
        rem = " ".join(words[idx:]).strip()
        rem = _FORMAT_DIRECTIVES.sub("", rem).strip()

        result = rem if rem else clean
        return result.rstrip(".?!,;: ").strip()

    def interpret(self, prompt: str) -> TaskSpecification:
        """
        Convert raw natural language prompt into a typed TaskSpecification
        mapped to the best matching capability.
        """
        raw = prompt.strip()
        lower = raw.lower()

        # Extract page count
        page_count = 1
        pm = _PAGE_DIRECTIVES.search(raw)
        if pm:
            try:
                page_count = int(pm.group(1) or pm.group(2))
            except (ValueError, TypeError):
                page_count = 1

        wants_images = bool(_IMAGE_DIRECTIVES.search(raw))

        # Detect deliverable type
        is_research = any(
            k in lower for k in (
                "research paper", "academic paper", "ieee", "scholarly", "scientific paper",
                "journal paper", "literature review", "formal report", "study", "monograph",
                "biology", "physics", "taxonomy", "evolution",
            )
        )
        deliverable_type = "research_paper" if is_research else "standard_document"
        if "literature review" in lower:
            deliverable_type = "literature_review"
        elif "report" in lower:
            deliverable_type = "technical_report"

        # 1. Classical rule-informed lexical signals with strict word boundaries
        words_set = set(re.findall(r"\b[a-zA-Z0-9_\-]+\b", lower))
        has_create_verb = bool(words_set & _CREATION_VERBS) or any(
            v in lower for v in ("create a", "write a", "prepare a", "produce a", "make a", "draft a", "compile a")
        )
        has_doc_noun = bool(words_set & _DOCUMENT_NOUNS)
        has_classify_verb = bool(words_set & _CLASSIFICATION_VERBS) or any(
            v in lower for v in ("sort my", "organize my", "classify this", "route this", "categorize files")
        )
        has_browser_verb = any(v in lower for v in ("go to", "visit", "navigate to", "open google", "slides.new", "docs.new", "take control of browser", "take me to", "browse to"))

        subject = self.extract_subject(raw)

        # 2. Semantic matching against ToolCapability registry
        model = self._get_embedding_model()
        action = "answer_query"
        confidence = 0.5
        rationale = "Lexical fallback"

        if model is not None:
            prompt_emb = model.encode([raw])[0]
            best_cap = None
            best_sim = -1.0
            second_sim = -1.0

            for cap in self.registry.list_capabilities():
                # Compare prompt against capability description and anchors
                texts = [cap.description] + cap.semantic_anchors
                embs = model.encode(texts)
                sims = np.dot(embs, prompt_emb) / (np.linalg.norm(embs, axis=1) * np.linalg.norm(prompt_emb) + 1e-9)
                max_sim = float(np.max(sims))

                if max_sim > best_sim:
                    second_sim = best_sim
                    best_sim = max_sim
                    best_cap = cap
                elif max_sim > second_sim:
                    second_sim = max_sim

            if best_cap:
                action = best_cap.action_type
                confidence = float(max(0.0, min(1.0, best_sim)))
                rationale = f"Matched capability '{best_cap.name}' (semantic similarity: {best_sim:.2f}, margin: {best_sim - second_sim:.2f})"

        # 3. Disambiguation & Guardrails: Document Creation vs File Classification
        # A document creation request must NEVER fall through to classification!
        if (has_create_verb and has_doc_noun) or (has_doc_noun and any(p in lower for p in ("on ", "about ", "explaining ", "regarding "))):
            action = "create_document"
            confidence = max(confidence, 0.85)
            rationale = "Explicit document creation intent detected"
        elif has_classify_verb and any(w in lower for w in ("file", "files", "download", "downloads", "folder", "directory", "pdf")):
            action = "classify_files"
            confidence = max(confidence, 0.85)
            rationale = "Explicit file classification intent detected"
        elif has_browser_verb and not (has_create_verb and has_doc_noun):
            action = "browse_web"
            confidence = max(confidence, 0.85)
            rationale = "Web browser navigation intent detected"
        elif any(lower.startswith(q) for q in ("can you explain", "could you explain", "what is ", "what are ", "how does ", "why is ", "why do ", "explain how ")) and not has_doc_noun:
            action = "answer_query"
            confidence = max(confidence, 0.85)
            rationale = "Direct conversational inquiry detected"

        # Format detection
        doc_format = "both" if (is_research or "latex" in lower or "ieee" in lower) else "docx"
        if "word" in lower and not ("latex" in lower or "ieee" in lower):
            doc_format = "docx"

        effective_pages = page_count if pm else (10 if is_research else 1)

        return TaskSpecification(
            action=action,
            subject=subject,
            deliverable_type=deliverable_type,
            format=doc_format,
            wants_images=wants_images,
            page_count=effective_pages,
            raw_prompt=raw,
            confidence=round(confidence, 3),
            rationale=rationale,
            parameters={
                "is_research": is_research,
                "target_format": doc_format,
            },
        )


# Global singleton
_INTERPRETER: RequestInterpreter | None = None


def get_request_interpreter() -> RequestInterpreter:
    global _INTERPRETER
    if _INTERPRETER is None:
        _INTERPRETER = RequestInterpreter()
    return _INTERPRETER
