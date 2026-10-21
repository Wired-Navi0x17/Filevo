"""
Tool Capabilities & Task Specification Contracts
Provides the foundational schemas for universal request interpretation,
capability discovery, execution planning, and action dispatching.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable


@dataclass
class TaskSpecification:
    """Structured, validated specification of an interpreted user request."""

    action: str  # e.g., 'create_document', 'classify_files', 'browse_web', 'answer_query'
    subject: str  # Core extracted topic, entity, query, or file target
    deliverable_type: str = "standard_document"  # 'research_paper', 'literature_review', 'technical_report', 'web_navigation', 'file_routing'
    format: str = "docx"  # 'docx', 'ieee_latex', 'both'
    wants_images: bool = False
    page_count: int = 1
    parameters: dict[str, Any] = field(default_factory=dict)
    raw_prompt: str = ""
    confidence: float = 1.0
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ToolCapability:
    """Self-describing capability registered with the application engine."""

    name: str
    description: str
    action_type: str
    parameters_schema: dict[str, Any]
    safety_level: str = "read_only"  # 'read_only', 'file_create', 'system_action'
    semantic_anchors: list[str] = field(default_factory=list)
    handler: Callable[[TaskSpecification], Any] | None = None

    def matches_action(self, action: str) -> bool:
        return self.action_type == action or self.name == action


class CapabilityRegistry:
    """Central registry of executable application capabilities."""

    def __init__(self) -> None:
        self._capabilities: dict[str, ToolCapability] = {}
        self._anchor_embeddings: dict[str, Any] = {}
        self._model = None

    def register(self, capability: ToolCapability) -> None:
        self._capabilities[capability.name] = capability
        self._anchor_embeddings.clear()

    def get(self, name: str) -> ToolCapability | None:
        return self._capabilities.get(name)

    def list_capabilities(self) -> list[ToolCapability]:
        return list(self._capabilities.values())

    def get_by_action(self, action: str) -> ToolCapability | None:
        for cap in self._capabilities.values():
            if cap.matches_action(action):
                return cap
        return None


# Global singleton registry
_GLOBAL_REGISTRY: CapabilityRegistry | None = None


def get_capability_registry() -> CapabilityRegistry:
    """Retrieve or initialize the global capability registry."""
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        reg = CapabilityRegistry()

        # 1. Document Creation & Academic Research Monograph
        reg.register(
            ToolCapability(
                name="create_academic_document",
                action_type="create_document",
                description="Researches any subject, gathers credible source evidence, and synthesizes a professional Microsoft Word (.docx) document or IEEE LaTeX (.tex) research paper with verified citations, equations, figures, and tables.",
                parameters_schema={
                    "subject": {"type": "string", "required": True, "description": "The research subject or document topic"},
                    "deliverable_type": {"type": "string", "enum": ["research_paper", "literature_review", "technical_report", "standard_document"]},
                    "format": {"type": "string", "enum": ["docx", "ieee_latex", "both"]},
                    "wants_images": {"type": "boolean", "default": False},
                    "page_count": {"type": "integer", "default": 10},
                },
                safety_level="file_create",
                semantic_anchors=[
                    "create a report on kangaroo with images",
                    "write a research paper on quantum computing",
                    "prepare a professional report explaining kangaroo biology",
                    "write a visual report about kangaroos",
                    "make a formal report using credible sources on ancient roman aqueducts",
                    "generate word document and ieee latex paper",
                    "research this subject and produce a document with pictures",
                    "compile a comprehensive study on honeybee communication",
                    "draft an academic literature review with citations",
                ],
            )
        )

        # 2. Workspace File Organization & Classification
        reg.register(
            ToolCapability(
                name="organize_and_classify_files",
                action_type="classify_files",
                description="Scans, categorizes, routes, and organizes local files and directories into academic or topic-based folder hierarchies using RLCD active learning decisions.",
                parameters_schema={
                    "target_path": {"type": "string", "description": "Directory or file to organize"},
                    "destination_category": {"type": "string", "description": "Target folder or category"},
                },
                safety_level="system_action",
                semantic_anchors=[
                    "organize these downloaded files into proper folders",
                    "sort my downloads directory into course subjects",
                    "classify this pdf document into calculus or computer science",
                    "move these files to their respective category directories",
                    "route scanned documents to matching folders",
                    "clean up and categorize my workspace folder",
                ],
            )
        )

        # 3. Web & PC Task Automation
        reg.register(
            ToolCapability(
                name="automate_browser",
                action_type="browse_web",
                description="Controls and automates web browser tasks, navigates to URLs, opens cloud productivity suites like Google Docs or Sheets, and interacts with web applications.",
                parameters_schema={
                    "target_url": {"type": "string", "description": "The website or destination URL"},
                    "subtask": {"type": "string", "description": "Action to perform on the page"},
                },
                safety_level="system_action",
                semantic_anchors=[
                    "go to google docs and open a new blank document",
                    "open slides.new in my default browser",
                    "navigate to github and search for repository",
                    "take control of my browser and visit website",
                    "launch firefox and browse to url",
                    "take me to the website and look up articles",
                    "browse to url and search for papers",
                    "open the web browser and visit repository",
                ],
            )
        )

        # 4. Direct Q&A and Conversational Chat
        reg.register(
            ToolCapability(
                name="answer_conversational",
                action_type="answer_query",
                description="Answers factual, conceptual, or analytical questions directly in chat without creating a file or navigating the browser.",
                parameters_schema={
                    "query": {"type": "string", "required": True},
                },
                safety_level="read_only",
                semantic_anchors=[
                    "what is the difference between supervised and unsupervised learning",
                    "explain how policy gradient ascent works in reinforcement learning",
                    "tell me about the history of the printing press",
                    "how does entropy regularization prevent premature convergence",
                    "what are the key symptoms of marsupial embryonic diapause",
                    "can you explain how photosynthesis converts solar energy into glucose",
                    "what are the primary differences between common law and civil law systems",
                    "how does quantum entanglement work",
                    "why do leaves change color in autumn",
                    "explain the difference between process and thread",
                ],
            )
        )

        _GLOBAL_REGISTRY = reg

    return _GLOBAL_REGISTRY
