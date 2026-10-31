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
        if target_pages and target_pages >= 30 and genre in ("Technical Report", "Comprehensive Guide") and not directive:
            genre = "Academic Monograph" if any(w in clean_req.lower() for w in ("monograph", "academic", "research", "study")) else genre

        # Step 3: Semantic Title Synthesis (guaranteed non-placeholder)
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
                subject, genre, topic, hardware_items, workflows, target_pages=target_pages, directive=directive
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


def extract_semantic_subject(clean_req: str) -> str:
    """Extract core semantic topic/subject from arbitrary user requests without brittle keyword lists."""
    _, req = extract_page_budget(clean_req.strip())
    _, req = extract_per_page_directive(req)

    # 1. Remove explicit section constraints clause
    req = re.sub(
        r"(?:specifying|with sections?|including sections?|sections?:|covering sections?)\s+.*$",
        "",
        req,
        flags=re.IGNORECASE,
    ).strip()

    # 2. Strip conversational prefixes & operational verbs
    cleaned = re.sub(
        r"^(?:please\s+)?(?:can\s+you\s+)?(?:i\s+want\s+(?:to\s+)?|i\s+need\s+(?:a\s+)?)?"
        r"(?:create|generate|write|draft|build|make|prepare|produce|compile|synthesize)?\s*"
        r"(?:a\s+|an\s+|the\s+)?"
        r"(?:technical\s+report|formal\s+letter|project\s+proposal|project\s+pitch|pitch|academic\s+monograph|executive\s+summary|comprehensive\s+guide|detailed\s+guide|overview|guide|docx|document|report|paper|brief|study|essay)?"
        r"(?:\s+(?:on|about|for|regarding|covering|of|with))?\s*",
        "",
        req,
        flags=re.IGNORECASE,
    ).strip()

    # 3. Strip file extension if appended
    cleaned = re.sub(r"\.(docx|pdf|txt)$", "", cleaned, flags=re.IGNORECASE).strip()

    # 4. Strip leftover prepositions
    cleaned = re.sub(r"^(?:on|about|for|regarding|covering|of|with)\s+", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s+(?:on|about|for|regarding|covering|of|with)$", "", cleaned, flags=re.IGNORECASE).strip()

    if not cleaned or len(cleaned) < 2:
        cleaned = req

    return cleaned


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


def infer_genre_and_audience(clean_req: str, subject: str, fallback_archetype: str = "Technical Report", directive: dict[str, Any] | None = None) -> tuple[str, str, str]:
    """Determine genre, tone, and audience from request, extracted subject, and optional directive."""
    req_lower = clean_req.lower()
    sub_lower = subject.lower()

    if directive and directive.get("is_per_page"):
        entity = directive.get("entity_type", "entity")
        return f"{entity.title()} Dossier Compendium", "authoritative, biographical, and descriptive", "Domain researchers, enthusiasts, and general readership"
    elif any(w in req_lower for w in ("letter", "application", "permission", "formal request")):
        return "Formal Letter", "formal and respectful", "Administrative review board and institutional authorities"
    elif any(w in req_lower for w in ("proposal", "business case", "project pitch", "grant", "funding")):
        return "Project Proposal", "persuasive and analytical", "Executive leadership, evaluators, and project sponsors"
    elif any(w in req_lower for w in ("academic", "monograph", "thesis", "research paper", "scholarly", "mathematical")):
        return "Academic Monograph", "scholarly and rigorous", "Academic researchers, faculty, and peer reviewers"
    elif any(w in req_lower for w in ("spec", "specification", "telemetry", "iot", "sensor", "hardware", "engineering", "microcontroller", "embedded")):
        return "Engineering Report", "authoritative and analytical", "Engineering students, system architects, and technical reviewers"
    elif any(w in req_lower for w in ("guide", "manual", "handbook", "encyclopedia", "overview")) or any(w in sub_lower for w in ("animal", "marine", "sea", "ocean", "nature", "biology", "history", "geology", "forest", "wildlife", "fauna", "flora")):
        return "Comprehensive Guide", "informative and structured", "General readers, domain educators, and research specialists"
    elif fallback_archetype and fallback_archetype not in ("Technical Report", "Executive Summary", "Executive Briefing"):
        return fallback_archetype, "professional and analytical", "Domain practitioners, engineers, and technical evaluators"
    else:
        return "Technical Report", "professional and analytical", "Domain practitioners, engineers, and technical evaluators"


def synthesize_title(subject: str, genre: str, directive: dict[str, Any] | None = None, target_pages: int | None = None) -> str:
    """Synthesize an accurate, professional representation title strictly grounded in the subject."""
    clean_sub = subject.strip()

    if directive and directive.get("entity_type"):
        entity_name = directive["entity_type"].title()
        if target_pages:
            return f"{clean_sub.title()}: {target_pages}-{entity_name} Compendium"
        return f"{clean_sub.title()}: {entity_name} Compendium"

    words = clean_sub.split()
    # If the user already provided a multi-word descriptive title, preserve it if clean
    if len(words) >= 4 and not any(w in clean_sub.lower() for w in ("create", "write", "docx", "document", "each page", "differe")):
        return clean_sub.title()

    sub_title = clean_sub.title()
    if genre.endswith("Compendium") or "Dossier" in genre:
        return f"{sub_title}: Comprehensive Reference Compendium"
    elif genre == "Comprehensive Guide":
        return f"{sub_title}: A Comprehensive Guide and Overview"
    elif genre == "Engineering Report":
        return f"Technical Report on {sub_title}"
    elif genre == "Project Proposal":
        return f"Project Proposal: {sub_title}"
    elif genre == "Academic Monograph":
        return f"Academic Monograph: Theoretical and Empirical Analysis of {sub_title}"
    elif genre == "Formal Letter":
        return f"Formal Application Concerning {sub_title}"
    elif genre == "Executive Summary":
        return f"Executive Briefing: {sub_title}"
    else:
        return f"Technical Report on {sub_title}"


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
    clean_topic = topic.strip().title()
    planned_sections: list[PlannedSection] = []
    visual_elements = ["taxonomic_matrix", "system_architecture_diagram", "comparative_evaluation", "workflow_sequence", "testing_matrix"]

    count = max(target_count, 1)
    num_facets = len(UNIVERSAL_ANALYTICAL_FACETS)

    for i in range(count):
        r = to_roman(i + 1)
        facet_name, facet_purpose = UNIVERSAL_ANALYTICAL_FACETS[i % num_facets]
        cycle = (i // num_facets) + 1
        part_suffix = f" (Part {cycle})" if cycle > 1 else ""

        heading = f"Chapter {r}: {facet_name} of {clean_topic}{part_suffix}"
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
) -> tuple[list[PlannedSection], list[str]]:
    """Architect domain-coherent sections based on the semantic nature of the subject, genre, and page budget."""
    clean_topic = topic.strip().title() if topic else subject.strip().title()

    # 1. Page-budgeted multi-chapter monograph / treatise (for ANY topic when target_pages >= 8)
    if target_pages is not None and target_pages >= 8:
        return generate_universal_monograph_sections(clean_topic, target_pages, genre=genre, directive=directive)

    # 2. Formal Letter
    if genre == "Formal Letter":
        planned_sections = [
            PlannedSection("sec_1", "Formal Salutation and Recipient", "Establish formal greeting, date, and recipient identification.", representation="prose"),
            PlannedSection("sec_2", "Statement of Purpose", f"Declare formal objective and request concerning {clean_topic}.", representation="prose", detail_level="standard"),
            PlannedSection("sec_3", "Background and Justification", f"Provide operational rationale and institutional merit for {clean_topic}.", representation="prose", detail_level="standard"),
            PlannedSection("sec_4", "Terms and Requirements", "Specify concrete parameters, compliance commitments, and timelines.", representation="procedural_steps", detail_level="standard"),
            PlannedSection("sec_5", "Closing and Authorization Signatures", "Conclude respectfully with designated signatory blocks.", representation="prose"),
        ]
        return planned_sections, []

    # 3. Project Proposal
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

    # 4. Academic Monograph / In-Depth Study
    if genre == "Academic Monograph":
        visual_elements = ["methodology_flowchart", "comparative_evaluation", "system_architecture_diagram"]
        planned_sections = [
            PlannedSection("sec_1", "Abstract and Executive Summary", f"Rigorous scholarly synopsis of {clean_topic}.", detail_level="standard"),
            PlannedSection("sec_2", "Introduction and Theoretical Foundations", f"Problem formulation and research scope for {clean_topic}.", detail_level="standard"),
            PlannedSection("sec_3", "Related Work and Literature Analysis", "Critical review of existing paradigms and prior findings.", detail_level="deep"),
            PlannedSection("sec_4", "Formal System Design and Methodology", "Mathematical formulation and analytical framework.", representation="procedural_steps", detail_level="deep", visual_element="methodology_flowchart"),
            PlannedSection("sec_5", "Experimental Validation and Protocol", "Empirical testing procedures and comparative analysis.", representation="table", detail_level="deep", visual_element="comparative_evaluation"),
            PlannedSection("sec_6", "Discussion and Critical Limitations", "Boundary analysis, failure modes, and theoretical implications.", detail_level="standard"),
            PlannedSection("sec_7", "Conclusion and Future Research Directions", "Summary of contributions and open questions.", detail_level="standard"),
        ]
        return planned_sections, visual_elements

    # 5. Comprehensive Guide / Natural Sciences / Biological Compendium
    if genre == "Comprehensive Guide" or any(w in clean_topic.lower() for w in ("animal", "marine", "plant", "nature", "biology", "wildlife", "species", "fauna", "flora")):
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

    # 6. Engineering Report (Hardware / Embedded / IoT / Telemetry)
    if genre == "Engineering Report":
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

    # 6. General Technical Report Architecture (Default Fallback)
    visual_elements = ["system_architecture_diagram", "evaluation_matrix"]
    planned_sections = [
        PlannedSection("sec_1", "Executive Summary", f"Executive synthesis of {clean_topic}.", detail_level="standard"),
        PlannedSection("sec_2", "Problem Formulation and System Scope", f"Operational background, problem statement, and goals for {clean_topic}.", detail_level="standard"),
        PlannedSection("sec_3", "Technical Architecture and Core Components", "Component decomposition, interfaces, and architectural patterns.", detail_level="deep", visual_element="system_architecture_diagram"),
        PlannedSection("sec_4", "Implementation Methodology and Workflows", "Core algorithms, data flow, and procedural execution.", representation="procedural_steps", detail_level="deep"),
        PlannedSection("sec_5", "Verification, Benchmarking and Quality Assurance", "Validation protocols, testing strategies, and performance criteria.", representation="procedural_steps", detail_level="deep", visual_element="evaluation_matrix"),
        PlannedSection("sec_6", "Operational Constraints and Strategic Recommendations", "Failure modes, edge cases, scalability bottlenecks, and mitigations.", detail_level="standard"),
        PlannedSection("sec_7", "Conclusion", "Final architectural summary and strategic roadmap.", detail_level="standard"),
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

