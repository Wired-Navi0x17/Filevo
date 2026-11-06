"""Structured Autonomous Document Plan and Brief representation for Filevo.

Transforms Filevo from a template filler into an autonomous document author.
Determines document genre, audience, heading hierarchy, section contracts,
depth, visual elements (diagrams, tables), and constraints.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MediaRequirements:
    """Explicit media and illustration requirements extracted from request."""

    has_images: bool = False
    count: int = 0
    kinds: list[str] = field(default_factory=list)
    captions_requested: bool = True
    raw_clause: str = ""


@dataclass
class PlannedSection:
    """Internal contract for an individual document section."""

    id: str
    heading: str
    purpose: str
    required_concepts: list[str] = field(default_factory=list)
    evidence_required: str = ""
    detail_level: str = "standard"  # "concise", "standard", "deep"
    representation: str = "prose"  # "prose", "procedural_steps", "table", "analysis"
    visual_element: str | None = None  # "comparison_table", "workflow_sequence", "testing_matrix", None
    expected_paragraphs: int = 2
    page_break_before: bool = False
    image: Any | None = None


@dataclass
class DocumentPlan:
    """Complete autonomous specification of a document authoring task."""

    original_request: str
    title: str
    topic: str
    genre: str  # "Engineering Report", "Technical Report", "Research Paper", "Project Proposal", "Formal Letter", etc.
    purpose: str
    audience: str
    tone: str  # "professional", "academic", "persuasive", "operational"
    writing_depth: str  # "standard", "comprehensive", "in-depth"
    sections: list[PlannedSection] = field(default_factory=list)
    required_technical_concepts: list[str] = field(default_factory=list)
    explicit_hardware_specifications: list[str] = field(default_factory=list)
    functional_workflows: list[str] = field(default_factory=list)
    visual_elements: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    sources_and_evidence: list[dict[str, Any]] = field(default_factory=list)
    needs_external_research: bool = False
    is_offline_fallback: bool = False
    target_pages: int | None = None
    document_subject: str = ""
    document_type: str = ""
    document_purpose: str = ""
    intended_audience: str = ""
    presentation_profile: str = ""
    explicit_requirements: list[str] = field(default_factory=list)
    media_requirements: MediaRequirements = field(default_factory=MediaRequirements)
    acquired_images: list[Any] = field(default_factory=list)

    def __post_init__(self):
        if not self.document_subject:
            self.document_subject = self.topic
        if not self.document_type:
            self.document_type = self.genre
        if not self.document_purpose:
            self.document_purpose = self.purpose
        if not self.intended_audience:
            self.intended_audience = self.audience
        if not self.presentation_profile:
            self.presentation_profile = self.genre

    @property
    def required_sections(self) -> list[str]:
        """List of section heading titles for backwards compatibility."""
        return [s.heading for s in self.sections]

    @property
    def archetype(self) -> str:
        """Alias for genre to preserve compatibility with RLCDDecisionEngine."""
        return self.genre

    @property
    def objective(self) -> str:
        """Alias for purpose to preserve compatibility with existing callers."""
        return self.purpose

    @classmethod
    def from_request(
        cls,
        user_request: str,
        archetype: str = "Technical Report",
        explicit_sections: list[str] | None = None,
        web_sources: list[dict[str, Any]] | None = None,
        attachments: list[dict[str, Any]] | None = None,
        title: str | None = None,
        client: Any | None = None,
    ) -> DocumentPlan:
        """Autonomously architect a complete DocumentPlan from user objective with self-healing validation."""
        clean_req = user_request.strip()

        # Step 0: Extract target page budget and per-page directive if specified
        target_pages, req_without_pages = extract_page_budget(clean_req)
        clean_req_semantic = req_without_pages if target_pages else clean_req
        directive, clean_req_semantic = extract_per_page_directive(clean_req_semantic)

        # Step 1: Semantic Subject & Entity Extraction
        subject = extract_semantic_subject(clean_req_semantic)
        hardware_items = extract_domain_hardware(clean_req_semantic)
        workflows = extract_domain_workflows(clean_req_semantic)

        # Step 2: Genre, Tone, and Audience Determination
        genre, tone, audience = infer_genre_and_audience(clean_req_semantic, subject, fallback_archetype=archetype, directive=directive)
        if target_pages and target_pages >= 30 and genre == "Technical Report" and not directive:
            genre = "Academic Monograph" if any(w in clean_req.lower() for w in ("monograph", "academic", "research", "study")) else genre

        # Step 3: Semantic Title Synthesis (guaranteed non-placeholder)
        if not title or any(p in title.lower() for p in PLACEHOLDER_BLACKLIST):
            title = synthesize_title(subject, genre, directive=directive, target_pages=target_pages)
        topic = subject

        if explicit_sections is None:
            sec_match = re.search(
                r"(?:specifying|with sections?|including sections?|sections?:|covering sections?)\s+([^.\n]+)",
                clean_req,
                flags=re.IGNORECASE,
            )
            if sec_match:
                raw_sec_str = sec_match.group(1).strip()
                raw_parts = re.split(r"[,;]|\band\b", raw_sec_str)
                explicit_sections = []
                for part in raw_parts:
                    cleaned_part = re.sub(r"^(?:and|sections?|including|covering)\s+", "", part.strip(), flags=re.IGNORECASE).strip()
                    cleaned_part = re.sub(r"[\"']+$", "", cleaned_part).strip()
                    if cleaned_part and len(cleaned_part) >= 2:
                        explicit_sections.append(cleaned_part.title() if not cleaned_part.isupper() else cleaned_part)

        # Step 4: Autonomous Section Architecture & Contracts
        planned_sections: list[PlannedSection] = []
        visual_elements: list[str] = []

        if explicit_sections:
            for idx, sec_title in enumerate(explicit_sections):
                s_lower = sec_title.lower()
                rep = "procedural_steps" if any(k in s_lower for k in ("method", "workflow", "process", "procedure", "test", "protocol")) else "prose"
                vis = "testing_matrix" if "test" in s_lower else ("comparison_table" if ("hardware" in s_lower or "component" in s_lower) else None)
                depth = "deep" if any(k in s_lower for k in ("method", "hardware", "architecture", "design", "test", "analysis")) else "standard"
                planned_sections.append(
                    PlannedSection(
                        id=f"sec_{idx + 1}",
                        heading=sec_title,
                        purpose=f"Examine {sec_title} comprehensively in relation to {topic}.",
                        required_concepts=hardware_items if ("hardware" in s_lower or "method" in s_lower) else [topic],
                        detail_level=depth,
                        representation=rep,
                        visual_element=vis,
                        expected_paragraphs=3 if depth == "deep" else 2,
                    )
                )
                if vis and vis not in visual_elements:
                    visual_elements.append(vis)
        else:
            planned_sections, visual_elements = plan_domain_sections(
                subject, genre, topic, hardware_items, workflows, target_pages=target_pages, directive=directive, client=client
            )

        # Step 5: Technical Concepts & Context Invariants
        stopwords = {
            "create", "generate", "write", "draft", "make", "report", "document", "technical",
            "formal", "paper", "about", "using", "with", "sections", "please", "system", "study",
            "specifying", "covering", "including", "and", "the", "for", "from", "that", "this",
            "detailed", "an", "a", "in", "on", "to", "of", "docx",
        }
        words = re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", clean_req.lower())
        concepts = [w for w in words if w not in stopwords]

        purpose = f"Provide an authoritative, publication-quality {genre.lower()} for {topic}, establishing foundational concepts, operational workflows, and rigorous analysis."
        constraints = [
            "Strict zero C-dependency Microsoft Word OpenXML generation",
            "No fabricated empirical numbers (do not invent unverified trial counts or precision percentages)",
            "Ground explanations in user-specified entities, verified design principles, and functional workflows",
            "Complete sentences with proper terminal punctuation",
            "Non-destructive versioning without overwriting previous artifacts",
        ]

        # Step 4b: Extract Media Requirements and Acquire Images
        media_req, _ = extract_media_requirements(clean_req)
        acquired_images = []
        image_acquisition_diagnostic = None
        if media_req.has_images:
            try:
                from src.doc_gen.image_fetcher import get_image_fetcher
                fetcher = get_image_fetcher()
                req_count = media_req.count if media_req.count > 0 else 3
                acquired_images = fetcher.acquire_images(
                    subject=topic,
                    count=req_count,
                )
            except Exception as e:
                image_acquisition_diagnostic = str(e)
                acquired_images = []

        # Distribute acquired images across planned sections (1 per section where appropriate)
        if acquired_images and planned_sections:
            img_idx = 0
            for sec in planned_sections:
                if img_idx < len(acquired_images):
                    sec.image = acquired_images[img_idx]
                    img_idx += 1

        evidence: list[dict[str, Any]] = []
        if web_sources:
            evidence.extend(web_sources)
        if attachments:
            for a in attachments:
                evidence.append({
                    "title": a.get("name", "attachment"),
                    "snippet": a.get("content", "")[:600],
                })

        candidate_plan = cls(
            original_request=clean_req,
            title=title,
            topic=topic,
            genre=genre,
            purpose=purpose,
            audience=audience,
            tone=tone,
            writing_depth="comprehensive",
            sections=planned_sections,
            required_technical_concepts=concepts,
            explicit_hardware_specifications=hardware_items,
            functional_workflows=workflows,
            visual_elements=visual_elements,
            constraints=constraints,
            sources_and_evidence=evidence,
            needs_external_research=bool(web_sources),
            is_offline_fallback=False,
            target_pages=target_pages,
            document_subject=topic,
            document_type=genre,
            document_purpose=purpose,
            intended_audience=audience,
            presentation_profile=genre,
            explicit_requirements=[],
            media_requirements=media_req,
            acquired_images=acquired_images,
        )

        # Step 6: Deterministic Validation Gate & Autonomous Recovery
        defects = validate_plan(candidate_plan, clean_req)
        if defects:
            candidate_plan = repair_plan(candidate_plan, clean_req, defects)
            recheck = validate_plan(candidate_plan, clean_req)
            if recheck:
                raise DocumentPlanningError(f"Autonomous planning recovery failed: {'; '.join(recheck)}")

        return candidate_plan

    def to_grounding_prompt(self) -> str:
        """Format the entire plan as authoritative grounding context for LLM generation."""
        lines = [
            f"Original Request: {self.original_request}",
            f"Document Title: {self.title}",
            f"Document Genre: {self.genre} (Tone: {self.tone})",
            f"Document Purpose: {self.purpose}",
            f"Target Audience: {self.audience}",
        ]
        if self.explicit_hardware_specifications:
            lines.append(f"Required Hardware Stack: {', '.join(self.explicit_hardware_specifications)}")
        if self.functional_workflows:
            lines.append("Required Operational Workflows:")
            for wf in self.functional_workflows:
                lines.append(f"  • {wf}")
        if self.visual_elements:
            lines.append(f"Planned Visual & Structural Elements: {', '.join(self.visual_elements)}")
        if self.constraints:
            lines.append("Engineering Constraints:")
            for c in self.constraints:
                lines.append(f"  • {c}")
        if self.sources_and_evidence:
            lines.append("Supporting Evidence & References:")
            for ev in self.sources_and_evidence[:4]:
                lines.append(f"  • {ev.get('title', 'Ref')}: {ev.get('snippet', ev.get('url', ''))[:150]}")
        return "\n".join(lines)


# Backwards compatibility alias
DocumentBrief = DocumentPlan


# ------------------------------------------------------------------ #
# Autonomous Semantic Planning & Self-Healing Validation Primitives
# ------------------------------------------------------------------ #

PLACEHOLDER_BLACKLIST = {
    "clean formal title",
    "primary subject",
    "document title",
    "formal title",
    "untitled",
    "sample title",
    "technical report document",
    "clean title",
    "template title",
    "formal document",
    "placeholder title",
    "test title",
}


class DocumentPlanningError(Exception):
    """Raised when document planning fails all autonomous recovery attempts."""
    pass


def extract_page_budget(raw_request: str) -> tuple[int | None, str]:
    """Extract requested target page count from request and return (target_pages, cleaned_request)."""
    pattern = re.compile(
        r"(?:(?:about|approx(?:imately)?|around|at least|minimum|target(?:ing)?|up to)?\s*)"
        r"\b(\d{1,4})\s*(?:-|to\s*\d{1,4}\s*)?(?:pages?|page|pgs?|pg)\b",
        flags=re.IGNORECASE,
    )
    m = pattern.search(raw_request)
    if m:
        try:
            pages = int(m.group(1))
            cleaned = pattern.sub("", raw_request).strip()
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            cleaned = re.sub(r"\s*,\s*$", "", cleaned).strip()
            return pages, cleaned
        except ValueError:
            pass
    return None, raw_request


def extract_per_page_directive(raw_request: str) -> tuple[dict[str, Any] | None, str]:
    """
    Extract per-page / per-section entity instructions such as:
    - 'each page must be unique about differect character'
    - 'each page must be unique about different character'
    - 'each page for a different planet'
    - 'one page per battle'
    - 'each section focusing on a different concept'
    Returns (directive_dict, cleaned_request).
    """
    pattern = re.compile(
        r"(?:,\s*)?(?:\b(?:and\s+)?(?:with\s+)?)?"
        r"\b(?:each|every|one)\s+(?:page|section)\s+"
        r"(?:must\s+be\s+|should\s+be\s+|is\s+|to\s+be\s+)?"
        r"(?:unique(?:ly)?\s+|distinct\s+)?"
        r"(?:about|covering|for|on|focusing\s+on|dedicated\s+to|per)\s+"
        r"(?:a\s+|an\s+|differe[nc]t\s+|unique\s+)?"
        r"(?P<entity>[a-zA-Z0-9_\-]+(?:\s+[a-zA-Z0-9_\-]+)?)"
        r"(?:\s+(?:in|of|from)\s+[a-zA-Z0-9_\-]+)?"
        r"(?:$|\.|\band\b|,\s*)",
        flags=re.IGNORECASE,
    )
    m = pattern.search(raw_request)
    if m:
        entity = m.group("entity").strip().lower()
        if entity.endswith("s") and not entity.endswith("ss") and len(entity) > 3:
            entity = entity[:-1]
        directive = {
            "entity_type": entity,
            "is_per_page": True,
            "raw_match": m.group(0).strip(),
        }
        cleaned = pattern.sub("", raw_request).strip()
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = re.sub(r"\s*,\s*$", "", cleaned).strip()
        return directive, cleaned

    p2 = re.compile(r"\b(?:one|a)\s+page\s+per\s+(?P<entity>[a-zA-Z0-9_\-]+)", flags=re.IGNORECASE)
    m2 = p2.search(raw_request)
    if m2:
        entity = m2.group("entity").strip().lower()
        if entity.endswith("s") and not entity.endswith("ss") and len(entity) > 3:
            entity = entity[:-1]
        directive = {"entity_type": entity, "is_per_page": True, "raw_match": m2.group(0).strip()}
        cleaned = p2.sub("", raw_request).strip()
        return directive, cleaned

    return None, raw_request


def extract_media_requirements(raw_request: str) -> tuple[MediaRequirements, str]:
    """
    Extract explicit media and illustration requirements from request.
    Handles patterns like:
    - 'with images'
    - 'with at least 4 relevant images'
    - 'with figures and references'
    - 'including 3 photos'
    - 'with illustrations'
    Returns (MediaRequirements, cleaned_request).
    """
    media_req = MediaRequirements()
    text = raw_request

    # Check for quantitative image clauses: 'with at least 4 relevant images', 'with 3 photos'
    num_pattern = re.compile(
        r"(?:,\s*)?(?:\b(?:and\s+)?(?:with\s+|including\s+|having\s+)?)?"
        r"(?:at\s+least\s+|up\s+to\s+|approx(?:\.|imately)?\s+)?(?P<count>\d+)\s+"
        r"(?:relevant\s+|high-quality\s+|authentic\s+)?"
        r"(?P<kind>images?|pictures?|photos?|figures?|illustrations?|diagrams?)"
        r"(?:\s+(?:and|with)\s+(?P<extra>references?|citations?|sources?))?",
        flags=re.IGNORECASE,
    )
    m = num_pattern.search(text)
    if m:
        media_req.has_images = True
        try:
            media_req.count = int(m.group("count"))
        except (ValueError, TypeError):
            media_req.count = 2
        kind = m.group("kind").lower()
        media_req.kinds = [kind]
        media_req.raw_clause = m.group(0).strip()
        text = num_pattern.sub("", text).strip()
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"\s*,\s*$", "", text).strip()
        return media_req, text

    # Check for qualitative image clauses: 'with images', 'with relevant figures and references', 'with photos'
    qual_pattern = re.compile(
        r"(?:,\s*)?(?:\b(?:and\s+)?(?:with\s+|including\s+|containing\s+))"
        r"(?:relevant\s+|high-quality\s+|authentic\s+)?"
        r"\b(?P<kind>images?|pictures?|photos?|figures?|illustrations?)\b"
        r"(?:\s+(?:and|with)\s+(?P<extra>references?|citations?|sources?))?",
        flags=re.IGNORECASE,
    )
    m2 = qual_pattern.search(text)
    if m2:
        media_req.has_images = True
        media_req.count = 3  # default reasonable figure allocation
        kind = m2.group("kind").lower()
        media_req.kinds = [kind]
        media_req.raw_clause = m2.group(0).strip()
        text = qual_pattern.sub("", text).strip()
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"\s*,\s*$", "", text).strip()
        return media_req, text

    return media_req, text


def extract_semantic_subject(clean_req: str) -> str:
    """Extract core semantic topic/subject from arbitrary user requests without brittle keyword lists."""
    _, req = extract_page_budget(clean_req.strip())
    _, req = extract_per_page_directive(req)
    _, req = extract_media_requirements(req)

    # 1. Remove explicit section constraints clause
    req = re.sub(
        r"(?:specifying|with sections?|including sections?|sections?:|covering sections?)\s+.*$",
        "",
        req,
        flags=re.IGNORECASE,
    ).strip()

    # 1b. Remove stylistic suffix constraints like 'as a minimalist editorial document', 'in corporate format'
    req = re.sub(
        r"(?:,\s*)?\bas\s+(?:a\s+|an\s+)?(?:minimalist\s+editorial|minimalist|editorial|formal|academic|corporate|technical)\s+(?:document|report|brief|style|format)\b.*$",
        "",
        req,
        flags=re.IGNORECASE,
    ).strip()

    # 2. Strip conversational prefixes & operational verbs
    cleaned = re.sub(
        r"^(?:please\s+)?(?:can\s+you\s+)?(?:i\s+want\s+(?:to\s+)?|i\s+need\s+(?:a\s+)?)?"
        r"(?:create|generate|write|draft|build|make|prepare|produce|compile|synthesize)?\s*"
        r"(?:a\s+|an\s+|the\s+)?"
        r"(?:technical\s+report|formal\s+letter|project\s+proposal|project\s+pitch|pitch|academic\s+monograph|academic\s+report|executive\s+summary|executive\s+briefing|comprehensive\s+guide|detailed\s+guide|overview|guide|docx|document|report|paper|brief|study|essay)?"
        r"(?:\s+(?:on|about|for|regarding|covering|of|with))?\s*",
        "",
        req,
        flags=re.IGNORECASE,
    ).strip()

    # 3. Strip file extension if appended
    cleaned = re.sub(r"\.(docx|pdf|txt)$", "", cleaned, flags=re.IGNORECASE).strip()

    # 4. Strip leftover prepositions & trailing media references
    cleaned = re.sub(r"^(?:on|about|for|regarding|covering|of|with)\s+", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s+(?:on|about|for|regarding|covering|of|with)$", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s+(?:with\s+images?|with\s+figures?|with\s+photos?)$", "", cleaned, flags=re.IGNORECASE).strip()

    if not cleaned or len(cleaned) < 2:
        cleaned = req

    return clean_subject(cleaned)


def extract_domain_hardware(clean_req: str) -> list[str]:
    """Extract explicit hardware and technical devices from request text."""
    hardware_items: list[str] = []
    req_lower = clean_req.lower()

    # Match hardware acronyms (e.g. ESP32, STM32, FPGA, MCU, GPU, BLE)
    acronym_matches = re.findall(r"\b[A-Z0-9]{2,}\b", clean_req)
    for acr in acronym_matches:
        if acr.lower() not in ("the", "and", "for", "with", "iot", "docx", "api", "can", "out"):
            if acr not in hardware_items:
                hardware_items.append(acr)

    if "esp32" in req_lower and "ESP32 microcontroller" not in hardware_items:
        hardware_items.append("ESP32 microcontroller")
    if ("ir" in req_lower or "infrared" in req_lower or "beam" in req_lower) and "IR sensors (infrared beam-break)" not in hardware_items:
        hardware_items.append("IR sensors (infrared beam-break)")
    if ("camera" in req_lower or "ball detection" in req_lower or "optical tracking" in req_lower) and "camera-based ball detection" not in hardware_items:
        hardware_items.append("camera-based ball detection")
    if "raspberry" in req_lower and "Raspberry Pi" not in hardware_items:
        hardware_items.append("Raspberry Pi")
    if "arduino" in req_lower and "Arduino" not in hardware_items:
        hardware_items.append("Arduino")
    if "ultrasonic" in req_lower and "ultrasonic distance sensors" not in hardware_items:
        hardware_items.append("ultrasonic distance sensors")

    return hardware_items


def extract_domain_workflows(clean_req: str) -> list[str]:
    """Extract operational workflows if present in request."""
    workflows: list[str] = []
    req_lower = clean_req.lower()
    if "ir" in req_lower or "sensor" in req_lower or "beam" in req_lower:
        workflows.append("optical beam-break gate triggering with sub-millisecond interrupt handling")
    if "camera" in req_lower or "ball" in req_lower or "detection" in req_lower or "tracking" in req_lower:
        workflows.append("optical trajectory capture and crease crossing verification")
    if "score" in req_lower or "scoring" in req_lower or "cricket" in req_lower:
        workflows.append("cross-sensor event validation and score arbitration")
        workflows.append("low-latency telemetry transmission to centralized scoreboard")
    return workflows


CANONICAL_ARCHETYPES = {
    "Technical Report": ("professional and analytical", "Domain practitioners, engineers, and technical evaluators"),
    "Academic Monograph": ("scholarly and rigorous", "Academic researchers, faculty, and peer reviewers"),
    "Project Proposal": ("persuasive and analytical", "Executive leadership, evaluators, and project sponsors"),
    "Executive Summary": ("concise, strategic, and decision-oriented", "C-suite executives, senior leadership, and board members"),
    "Formal Letter": ("formal and respectful", "Administrative review board and institutional authorities"),
    "Informative Editorial": ("engaging, authoritative, and educational", "General educated readership, domain enthusiasts, and students"),
    "Minimalist Editorial": ("understated, elegant, and focused", "Discerning readership and design-conscious audiences"),
}

LEGACY_ARCHETYPE_ALIASES = {
    "Engineering Report": "Technical Report",
    "Comprehensive Guide": "Informative Editorial",
    "Executive Briefing": "Executive Summary",
    "Technical Briefing": "Technical Report",
}


def infer_genre_and_audience(clean_req: str, subject: str, fallback_archetype: str = "Technical Report", directive: dict[str, Any] | None = None) -> tuple[str, str, str]:
    """Determine genre, tone, and audience from request, extracted subject, and optional directive.

    Enforces intent fidelity: Never chooses Executive Summary unless explicit executive signals exist.
    """
    req_lower = clean_req.lower()

    if directive and directive.get("is_per_page"):
        entity = directive.get("entity_type", "entity")
        return f"{entity.title()} Dossier Compendium", "authoritative, biographical, and descriptive", "Domain researchers, enthusiasts, and general readership"

    # Explicit user request takes absolute priority
    has_exec_intent = any(w in req_lower for w in ("executive", "exec summary", "briefing", "c-suite", "board", "commercial use", "business case"))
    has_academic_intent = any(w in req_lower for w in ("academic", "monograph", "thesis", "research paper", "scholarly", "mathematical", "history of"))
    has_minimalist_intent = any(w in req_lower for w in ("minimalist", "minimalist editorial"))
    has_editorial_intent = any(w in req_lower for w in ("editorial", "magazine", "essay", "informative"))

    if has_minimalist_intent:
        genre = "Minimalist Editorial"
        tone, audience = CANONICAL_ARCHETYPES[genre]
        return genre, tone, audience

    if has_academic_intent:
        genre = "Academic Monograph"
        tone, audience = CANONICAL_ARCHETYPES[genre]
        return genre, tone, audience

    if has_exec_intent:
        genre = "Executive Summary"
        tone, audience = CANONICAL_ARCHETYPES[genre]
        return genre, tone, audience

    # If fallback_archetype was supplied (e.g. from RLCD decision):
    # Guard against unprompted Executive Summary bias
    if fallback_archetype:
        resolved = LEGACY_ARCHETYPE_ALIASES.get(fallback_archetype, fallback_archetype)
        if resolved == "Executive Summary" and not has_exec_intent:
            # Overruled: Executive summary requested by policy without prompt justification
            # For general informative / nature / humanities / science subjects, default to Informative Editorial
            if any(w in subject.lower() for w in ("animal", "biology", "nature", "history", "guide", "art", "humanities", "philosophy", "culture", "literature", "editorial", "overview")):
                resolved = "Informative Editorial"
            else:
                resolved = "Technical Report"
        if resolved in CANONICAL_ARCHETYPES:
            tone, audience = CANONICAL_ARCHETYPES[resolved]
            return resolved, tone, audience

    # Heuristic inference when no archetype is supplied
    if any(w in req_lower for w in ("letter", "application", "permission", "formal request")):
        genre = "Formal Letter"
    elif any(w in req_lower for w in ("proposal", "business case", "project pitch", "grant", "funding")):
        genre = "Project Proposal"
    elif any(w in subject.lower() for w in ("animal", "biology", "wildlife", "plant", "nature", "history", "art", "humanities", "culture", "overview", "editorial", "guide")):
        genre = "Informative Editorial"
    else:
        genre = "Technical Report"

    tone, audience = CANONICAL_ARCHETYPES[genre]
    return genre, tone, audience


def clean_subject(text: str) -> str:
    """Collapse punctuation debris left behind by request parsing.

    Stripping a page budget ("..., 60 pages, ...") can leave doubled commas and
    trailing separators, which then leak into document titles and section
    headings (``... of Encyclopedia Of Plants,``).
    """
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"(?:,\s*)+", ", ", text)
    text = re.sub(r"\s*([.;:])\s*$", "", text)
    text = re.sub(r"[,;:\-\s]+$", "", text)
    return text.strip()


def synthesize_title(subject: str, genre: str, directive: dict[str, Any] | None = None, target_pages: int | None = None) -> str:
    """Synthesize an accurate, professional representation title strictly grounded in the subject."""
    clean_sub = clean_subject(subject)

    if directive and directive.get("entity_type"):
        entity_name = directive["entity_type"].title()
        if target_pages:
            return f"{clean_sub.title()}: {target_pages}-{entity_name} Compendium"
        return f"{clean_sub.title()}: {entity_name} Compendium"

    words = clean_sub.split()
    # If the user already provided a multi-word descriptive title, preserve it if clean
    if len(words) >= 3 and not any(w in clean_sub.lower() for w in ("create", "write", "docx", "document", "each page", "differe")):
        return clean_sub.title()

    sub_title = clean_sub.title()
    if genre.endswith("Compendium") or "Dossier" in genre:
        return f"{sub_title}: Comprehensive Reference Compendium"
    elif genre in ("Comprehensive Guide", "Informative Editorial"):
        return f"{sub_title}: Overview and Reference Guide"
    elif genre == "Minimalist Editorial":
        return f"{sub_title}"
    elif genre == "Engineering Report":
        return f"{sub_title}: Engineering and Technical Analysis"
    elif genre == "Project Proposal":
        return f"Project Proposal: {sub_title}"
    elif genre == "Academic Monograph":
        return f"{sub_title}: Principles, Analysis, and Foundations"
    elif genre == "Formal Letter":
        return f"Formal Application Concerning {sub_title}"
    elif genre == "Executive Summary":
        return f"Executive Briefing: {sub_title}"
    else:
        return f"{sub_title}: Technical Analysis and Specifications"


def to_roman(n: int) -> str:
    """Convert integer to Roman numeral."""
    val = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
    syb = ["M", "CM", "D", "CD", "C", "XC", "L", "XL", "X", "IX", "V", "IV", "I"]
    res = ""
    for v, s in zip(val, syb):
        while n >= v:
            res += s
            n -= v
    return res or "I"


UNIVERSAL_ANALYTICAL_FACETS = [
    ("Foundations, Historical Evolution, and Epistemological Scope", "Establish foundational scope, historical origins, theoretical definitions, and core terminology."),
    ("Theoretical Invariants, Governing Axioms, and Analytical Baselines", "Detail underlying theoretical invariants, mathematical/conceptual models, and baseline assumptions."),
    ("Taxonomic Classification, Core Typologies, and Morphological Divergence", "Analyze systematic taxonomy, classification frameworks, categorization criteria, and structural divergence."),
    ("Structural Hierarchy, Primary Architecture, and Component Decomposition", "Examine overall organizational hierarchy, primary architectural tiers, and essential component relationships."),
    ("Substrate Dynamics, Material Properties, and Resource Allocations", "Investigate physical/logical substrates, resource bounds, energy/material requirements, and structural characteristics."),
    ("Modular Interfaces, Inter-System Boundaries, and Topological Linkages", "Detail modular boundaries, interaction interfaces, communication/flow channels, and structural couplings."),
    ("Functional Mechanics, Internal Signaling, and Dynamic Flux Pathways", "Analyze operational mechanisms, signal/data propagation, transfer dynamics, and continuous internal workflows."),
    ("Operational Protocols, Execution States, and Process Sequences", "Detail procedural execution, operational stages, state transitions, and standardized runtime workflows."),
    ("Adaptive Responses, Environmental Interactions, and Dynamic Resilience", "Examine interaction with external environments, adaptive modifications, stress resilience, and behavioral dynamics."),
    ("Equilibrium Regulation, Feedback Control, and Systemic Stability", "Investigate homeostasis/stability mechanisms, negative/positive feedback loops, and regulation dynamics."),
    ("Empirical Measurement, Quantitative Field Observations, and Instrumentation", "Detail measurement methodologies, observational data collection, diagnostic telemetry, and sensing tools."),
    ("Comparative Benchmarks, Performance Metrics, and Efficiency Profiles", "Provide comparative analysis across operational conditions, performance benchmarks, and quantitative efficiency indices."),
    ("Boundary Conditions, Stress Vulnerabilities, and Failure Mode Analysis", "Examine operational limits, critical boundary thresholds, degradation modes, and vulnerability mitigations."),
    ("Specialized Niches, Case Studies, and Empirical Contexts", "Review distinctive operational cases, specialized environmental niches, field manifestations, and real-world deployments."),
    ("Operational Constraints, Risk Management, and Safety Standards", "Detail compliance frameworks, operational safety guidelines, risk mitigation matrices, and preventive protocols."),
    ("Systemic Trade-Offs, Capacity Planning, and Resource Optimization", "Analyze fundamental operational trade-offs, resource constraints, scaling dynamics, and efficiency trade-offs."),
    ("Lifecycle Management, Degradation Dynamics, and Preservation Protocols", "Examine temporal degradation, maintenance schedules, conservation/preservation protocols, and longevity factors."),
    ("Technological Augmentation, Modern Tooling, and Diagnostic Systems", "Review cutting-edge diagnostic technologies, computational tools, and observational platforms enhancing analysis."),
    ("Cross-Disciplinary Integration, Paradigm Convergence, and Systemic Synthesis", "Synthesize cross-cutting principles, interdisciplinary correlations, and unified theoretical models."),
    ("Forward Research Horizons, Open Challenges, and Emerging Paradigms", "Synthesize unaddressed inquiries, future technological/scientific frontiers, and forward-looking research trajectories."),
]


def generate_universal_monograph_sections(
    topic: str,
    target_count: int,
    genre: str = "Academic Monograph",
    directive: dict[str, Any] | None = None,
) -> tuple[list[PlannedSection], list[str]]:
    """Generates exactly target_count structured sections for any topic, guaranteeing exact page budgeting."""
    clean_topic = clean_subject(topic).title()
    planned_sections: list[PlannedSection] = []
    visual_elements = ["taxonomic_matrix", "system_architecture_diagram", "comparative_evaluation", "workflow_sequence", "testing_matrix"]

    count = max(target_count, 1)
    num_facets = len(UNIVERSAL_ANALYTICAL_FACETS)

    for i in range(count):
        r = to_roman(i + 1)
        facet_name, facet_purpose = UNIVERSAL_ANALYTICAL_FACETS[i % num_facets]
        cycle = (i // num_facets) + 1
        part_suffix = f" (Part {cycle})" if cycle > 1 else ""

        # Keep the heading to the analytical facet only. Repeating the document
        # title in all 60 headings makes the artifact unreadable and dilutes the
        # retrieval signal; the topic still reaches both `purpose` and
        # `required_concepts`, which are what retrieval queries are built from.
        heading = f"Chapter {r}: {facet_name}{part_suffix}"
        purpose = f"{facet_purpose} Specifically contextualized for {clean_topic}."
        vis = visual_elements[i % len(visual_elements)]

        planned_sections.append(
            PlannedSection(
                id=f"sec_{i + 1}",
                heading=heading,
                purpose=purpose,
                required_concepts=[clean_topic, facet_name],
                detail_level="deep",
                representation="prose",
                visual_element=None,
                expected_paragraphs=2,
                page_break_before=True if i > 0 else False,
            )
        )

    return planned_sections, visual_elements


def plan_domain_sections(
    subject: str,
    genre: str,
    topic: str,
    hardware_items: list[str],
    workflows: list[str],
    target_pages: int | None = None,
    directive: dict[str, Any] | None = None,
    client: Any | None = None,
) -> tuple[list[PlannedSection], list[str]]:
    """Architect domain-coherent sections based on the semantic nature of the subject, genre, and page budget."""
    clean_topic = clean_subject(topic).title() if topic else clean_subject(subject).title()

    # 1. Page-budgeted multi-chapter monograph / treatise (for ANY topic when target_pages >= 8)
    if target_pages is not None and target_pages >= 8:
        return generate_universal_monograph_sections(clean_topic, target_pages, genre=genre, directive=directive)

    # 2. Formal Letter (Strict contractual structure)
    if genre == "Formal Letter":
        planned_sections = [
            PlannedSection("sec_1", "Formal Salutation and Recipient", "Establish formal greeting, date, and recipient identification.", representation="prose"),
            PlannedSection("sec_2", "Statement of Purpose", f"Declare formal objective and request concerning {clean_topic}.", representation="prose", detail_level="standard"),
            PlannedSection("sec_3", "Background and Justification", f"Provide operational rationale and institutional merit for {clean_topic}.", representation="prose", detail_level="standard"),
            PlannedSection("sec_4", "Terms and Requirements", "Specify concrete parameters, compliance commitments, and timelines.", representation="procedural_steps", detail_level="standard"),
            PlannedSection("sec_5", "Closing and Authorization Signatures", "Conclude respectfully with designated signatory blocks.", representation="prose"),
        ]
        return planned_sections, []

    # 3. Executive Summary (Strict contractual structure)
    if genre == "Executive Summary":
        visual_elements = ["executive_kpi_dashboard", "risk_matrix"]
        planned_sections = [
            PlannedSection("sec_1", "Strategic Context", f"Strategic drivers, background, and business context for {clean_topic}.", detail_level="standard"),
            PlannedSection("sec_2", "Key Findings", f"Core operational outcomes, empirical observations, and performance metrics for {clean_topic}.", representation="table", detail_level="deep", visual_element="executive_kpi_dashboard"),
            PlannedSection("sec_3", "Risk Exposure", f"Critical risk vectors, operational vulnerabilities, and regulatory exposure for {clean_topic}.", representation="table", detail_level="standard", visual_element="risk_matrix"),
            PlannedSection("sec_4", "Strategic Recommendations", f"Actionable recommendations, immediate decisions, and forward roadmap for {clean_topic}.", representation="procedural_steps", detail_level="standard"),
        ]
        return planned_sections, visual_elements

    # 4. Project Proposal (Strict contractual structure)
    if genre == "Project Proposal":
        visual_elements = ["implementation_timeline", "resource_matrix"]
        planned_sections = [
            PlannedSection("sec_1", "Executive Summary", f"High-level synthesis of proposed initiative for {clean_topic}.", detail_level="standard"),
            PlannedSection("sec_2", "Problem Statement and Strategic Opportunity", f"Define operational deficiency and proposed impact for {clean_topic}.", detail_level="standard"),
            PlannedSection("sec_3", "Proposed Technical Architecture and Scope", "Architectural blueprint and technical innovations.", detail_level="deep", visual_element="architecture_diagram"),
            PlannedSection("sec_4", "Implementation Methodology and Phased Milestones", "Sequential execution plan and phased delivery.", representation="procedural_steps", detail_level="deep"),
            PlannedSection("sec_5", "Resource Allocation and Risk Management", "Budget, operational requirements, and mitigation matrices.", representation="table", visual_element="resource_matrix"),
            PlannedSection("sec_6", "Conclusion and Approval Request", "Call to action and strategic alignment summary.", detail_level="standard"),
        ]
        return planned_sections, visual_elements

    # 5. Dynamic LLM-driven Section Planning (Tier 1: Bespoke domain outline)
    if client and getattr(client, "_is_loaded", False):
        dynamic_secs = client.plan_topic_sections(
            topic=clean_topic,
            archetype=genre,
            target_pages=target_pages or 1,
            directive=directive,
        )
        if dynamic_secs and len(dynamic_secs) >= 3:
            planned = []
            for idx, s in enumerate(dynamic_secs):
                h = s["heading"]
                p = s["purpose"]
                s_low = h.lower()
                vis = "evaluation_matrix" if any(k in s_low for k in ("evaluat", "metric", "matrix", "benchmark")) else None
                rep = "procedural_steps" if any(k in s_low for k in ("method", "workflow", "process", "protocol", "step", "phase")) else "prose"
                depth = "deep" if idx in (1, 2) or any(k in s_low for k in ("architect", "mechanic", "analys", "principle")) else "standard"
                planned.append(
                    PlannedSection(
                        id=f"sec_{idx + 1}",
                        heading=h,
                        purpose=p,
                        detail_level=depth,
                        representation=rep,
                        visual_element=vis,
                        page_break_before=(target_pages is not None and target_pages > 3 and idx > 0 and idx % 2 == 0),
                    )
                )
            vis_list = ["system_architecture_diagram", "evaluation_matrix"] if genre == "Technical Report" else ["taxonomic_matrix", "comparative_evaluation"]
            return planned, vis_list

    # 6. Domain-Adaptive Universal Fallback Architectures (Tier 2: Offline / Fallback)

    # 6a. Natural Sciences, Biology, Ecology, and Organisms
    if any(w in clean_topic.lower() for w in ("animal", "marine", "plant", "nature", "biology", "wildlife", "species", "fauna", "flora", "ecolog", "organism", "zoology", "botany", "feline", "canine", "cat", "dog", "forest")):
        visual_elements = ["taxonomic_matrix", "comparative_evaluation"]
        planned_sections = [
            PlannedSection("sec_1", f"Introduction and Evolutionary Overview of {clean_topic}", f"Foundations, evolutionary history, and general characteristics of {clean_topic}.", detail_level="standard"),
            PlannedSection("sec_2", f"Taxonomic Classification and Biodiversity", f"Systematic taxonomy, morphological divergence, and clade classification across {clean_topic}.", detail_level="deep", visual_element="taxonomic_matrix"),
            PlannedSection("sec_3", f"Anatomical Structure and Physiological Adaptations", f"Internal organ systems, anatomical adaptations, metabolic functions, and physiological mechanisms.", detail_level="deep"),
            PlannedSection("sec_4", f"Ecological Niche, Habitat Distribution, and Biomes", f"Geographic distribution, ecological roles, environmental interactions, and habitat preservation.", detail_level="deep"),
            PlannedSection("sec_5", f"Behavioral Dynamics, Lifecycle, and Reproduction", f"Reproductive strategies, developmental lifecycles, and behavioral patterns.", detail_level="standard"),
            PlannedSection("sec_6", f"Conservation Status, Environmental Threats, and Protection", f"Ecological threats, extinction risk, and modern conservation frameworks.", detail_level="standard"),
            PlannedSection("sec_7", f"Conclusion and Summary", f"Concluding synthesis and significance of {clean_topic}.", detail_level="standard"),
        ]
        return planned_sections, visual_elements

    # 6b. Hardware / Embedded / IoT / Telemetry Engineering Specialization
    if hardware_items or workflows or any(w in clean_topic.lower() for w in ("iot", "esp32", "sensor", "telemetry", "embedded", "hardware", "firmware", "circuit")):
        visual_elements = ["system_architecture_diagram", "evaluation_matrix"]
        planned_sections = [
            PlannedSection("sec_1", "Executive Summary", f"Executive synthesis of {clean_topic}.", detail_level="standard"),
            PlannedSection("sec_2", "Problem Formulation and System Scope", f"Operational background, problem statement, and goals for {clean_topic}.", detail_level="standard"),
            PlannedSection(
                "sec_3",
                "Technical Architecture and Core Components",
                f"Component decomposition, interfaces, and architectural patterns for {clean_topic}.",
                required_concepts=hardware_items or [clean_topic],
                detail_level="deep",
                visual_element="system_architecture_diagram",
            ),
        ]
        sec_idx = 4
        if any("sensor" in w.lower() or "beam" in w.lower() or "gate" in w.lower() for w in workflows):
            planned_sections.append(
                PlannedSection(
                    f"sec_{sec_idx}",
                    "Sensor Acquisition and Optical Gate Pipeline",
                    "Interrupt-driven signal conditioning, debouncing, and sub-millisecond event detection.",
                    representation="procedural_steps",
                    detail_level="deep",
                )
            )
            sec_idx += 1
        if any("crease" in w.lower() or "trajectory" in w.lower() or "camera" in w.lower() for w in workflows):
            planned_sections.append(
                PlannedSection(
                    f"sec_{sec_idx}",
                    "Crease Verification and Ball Trajectory Tracking",
                    "Computer vision processing, frame synchronization, and geometric boundary validation.",
                    representation="procedural_steps",
                    detail_level="deep",
                )
            )
            sec_idx += 1
        if any("score" in w.lower() or "arbitration" in w.lower() or "telemetry" in w.lower() for w in workflows):
            planned_sections.append(
                PlannedSection(
                    f"sec_{sec_idx}",
                    "Score Arbitration and Real-Time Telemetry Transmission",
                    "Cross-sensor state machine reconciliation, tally verification, and network telemetry dispatch.",
                    representation="procedural_steps",
                    detail_level="deep",
                )
            )
            sec_idx += 1

        if sec_idx == 4:
            planned_sections.append(
                PlannedSection(f"sec_{sec_idx}", "Implementation Methodology and Workflows", "Core algorithms, data flow, and procedural execution.", representation="procedural_steps", detail_level="deep")
            )
            sec_idx += 1

        planned_sections.append(
            PlannedSection(f"sec_{sec_idx}", "System Testing, Verification, and Experimental Validation", "Validation protocols, testing strategies, and performance criteria.", representation="procedural_steps", detail_level="deep", visual_element="evaluation_matrix")
        )
        sec_idx += 1
        planned_sections.append(
            PlannedSection(f"sec_{sec_idx}", "Operational Constraints and Strategic Recommendations", "Failure modes, edge cases, scalability bottlenecks, and mitigations.", detail_level="standard")
        )
        sec_idx += 1
        planned_sections.append(
            PlannedSection(f"sec_{sec_idx}", "Conclusion", "Final architectural summary and strategic roadmap.", detail_level="standard")
        )
        return planned_sections, visual_elements

    # 6c. Humanities, History, Arts, Architecture, and Social Sciences
    if any(w in clean_topic.lower() for w in ("art", "history", "roman", "renaissance", "gothic", "architecture", "literature", "philosophy", "culture", "music", "humanities", "cinema", "society", "civilization", "archaeolog", "monograph")):
        visual_elements = ["taxonomic_matrix", "comparative_evaluation"]
        planned_sections = [
            PlannedSection("sec_1", f"Historical Context and Cultural Foundations of {clean_topic}", f"Foundational origins, intellectual movements, and historical context of {clean_topic}.", detail_level="standard"),
            PlannedSection("sec_2", f"Core Principles, Stylistic Movements, and Structural Innovations", f"Theoretical principles, aesthetic and structural innovations, and defining characteristics.", detail_level="deep", visual_element="taxonomic_matrix"),
            PlannedSection("sec_3", f"Seminal Works, Regional Centers, and Influential Figures", f"Prominent masterpieces, regional divergence, and influential practitioners shaping {clean_topic}.", detail_level="deep"),
            PlannedSection("sec_4", f"Critical Perspectives, Techniques, and Analytical Methodologies", f"Analytical paradigms, craftsmanship techniques, and contemporary critical evaluations.", detail_level="deep"),
            PlannedSection("sec_5", f"Cultural Dispersal, Modern Significance, and Enduring Legacy", f"Long-term cultural impact, preservation, and contemporary resonance of {clean_topic}.", detail_level="standard"),
        ]
        return planned_sections, visual_elements

    # 6d. Physical, Chemical, Quantum, and Material Sciences
    if any(w in clean_topic.lower() for w in ("quantum", "physics", "chemical", "chemistry", "nanotech", "solar cell", "material", "semiconductor", "thermodynamic")):
        visual_elements = ["system_architecture_diagram", "evaluation_matrix"]
        planned_sections = [
            PlannedSection("sec_1", f"Theoretical Foundations and Physical Principles of {clean_topic}", f"Fundamental physics, governing laws, and theoretical baselines for {clean_topic}.", detail_level="standard"),
            PlannedSection("sec_2", f"Mechanisms of Action and Phenomenological Dynamics", f"Core mathematical/physical models, state evolutions, and interactions.", detail_level="deep", visual_element="system_architecture_diagram"),
            PlannedSection("sec_3", f"Experimental Methodologies and Experimental Implementations", f"Apparatus design, measurement protocols, and fabrication/synthesis techniques.", detail_level="deep", representation="procedural_steps"),
            PlannedSection("sec_4", f"Empirical Benchmarks, Efficiency Limits, and Error Thresholds", f"Quantitative performance metrics, experimental validation, and loss/error thresholds.", detail_level="deep", visual_element="evaluation_matrix"),
            PlannedSection("sec_5", f"Technological Applications, Challenges, and Future Trajectories", f"Practical scalability, integration constraints, and forward research directions.", detail_level="standard"),
        ]
        return planned_sections, visual_elements

    # 6e. Universal Domain Fallback (Scholarly, Domain-Neutral, Clean)
    visual_elements = ["comparative_evaluation", "evaluation_matrix"]
    planned_sections = [
        PlannedSection("sec_1", f"Foundations and Overview of {clean_topic}", f"Core scope, foundational concepts, and operational context of {clean_topic}.", detail_level="standard"),
        PlannedSection("sec_2", f"Theoretical Frameworks and Governing Principles", f"Fundamental principles, conceptual models, and structural baselines.", detail_level="deep"),
        PlannedSection("sec_3", f"Systematic Methodologies and Practical Applications", f"Implementation approaches, typologies, and comparative workflows.", detail_level="deep", visual_element="comparative_evaluation"),
        PlannedSection("sec_4", f"Empirical Evaluation and Critical Analysis", f"Performance metrics, experimental or observational evidence, and comparative trade-offs.", detail_level="deep", visual_element="evaluation_matrix"),
        PlannedSection("sec_5", f"Strategic Challenges, Future Trajectories, and Synthesis", f"Forward roadmap, boundary conditions, and concluding synthesis for {clean_topic}.", detail_level="standard"),
    ]
    return planned_sections, visual_elements


def validate_plan(plan: DocumentPlan, original_request: str | None = None) -> list[str]:
    """Deterministic validation gate rejecting placeholder leakage, generic titles, or defective sections."""
    defects = []
    req_text = original_request if original_request is not None else getattr(plan, "original_request", "")

    # 1. Title placeholder check
    t_lower = plan.title.lower()
    for p in PLACEHOLDER_BLACKLIST:
        if p in t_lower:
            defects.append(f"Title contains blacklisted placeholder: '{p}'")
            break
    if len(plan.title.strip()) < 3:
        defects.append("Title is too short or empty")

    # 2. Topic placeholder check
    top_lower = plan.topic.lower()
    for p in PLACEHOLDER_BLACKLIST:
        if p in top_lower:
            defects.append(f"Topic contains blacklisted placeholder: '{p}'")
            break
    if len(plan.topic.strip()) < 2:
        defects.append("Topic is too short or empty")

    # 3. Semantic relevance check: core subject tokens from request must reflect in plan title or topic
    subject = extract_semantic_subject(req_text).lower() if req_text else ""
    sub_words = [w for w in re.findall(r"\w+", subject) if len(w) > 2]
    plan_words = set(re.findall(r"\w+", f"{t_lower} {top_lower}"))
    if sub_words and not any(w in plan_words for w in sub_words):
        defects.append(f"Plan title/topic has zero semantic overlap with request subject: '{subject}'")

    # 4. Section sufficiency and contract validation
    if len(plan.sections) < 3:
        defects.append(f"Plan has insufficient sections: {len(plan.sections)} (minimum 3 required)")
    for s in plan.sections:
        if not s.heading.strip() or len(s.heading.strip()) < 2:
            defects.append("Section has empty or invalid heading")
            break
        if not s.purpose.strip():
            defects.append(f"Section '{s.heading}' has missing purpose contract")
            break

    return defects


def repair_plan(plan: DocumentPlan, original_request: str | None = None, defects: list[str] | None = None) -> DocumentPlan:
    """Self-healing autonomous recovery: reconstructs defective plan fields directly from original request."""
    req_text = original_request if original_request is not None else getattr(plan, "original_request", "")
    t_pages = getattr(plan, "target_pages", None)
    if not t_pages:
        t_pages, _ = extract_page_budget(req_text)
    plan.target_pages = t_pages

    directive, _ = extract_per_page_directive(req_text)
    clean_sub = extract_semantic_subject(req_text)
    genre, tone, audience = infer_genre_and_audience(req_text, clean_sub, fallback_archetype=plan.genre, directive=directive)
    title = synthesize_title(clean_sub, genre, directive=directive, target_pages=t_pages)
    topic = clean_sub

    hw = extract_domain_hardware(req_text)
    wf = extract_domain_workflows(req_text)
    sections, visuals = plan_domain_sections(clean_sub, genre, topic, hw, wf, target_pages=t_pages, directive=directive)

    plan.title = title
    plan.topic = topic
    plan.genre = genre
    plan.tone = tone
    plan.audience = audience
    plan.sections = sections
    plan.visual_elements = visuals
    plan.purpose = f"Provide an authoritative, publication-quality {genre.lower()} for {topic}, establishing foundational concepts, operational workflows, and rigorous analysis."
    return plan

