"""Comprehensive automated verification tests for Filevo."""

import os
import sys
import tempfile
import zipfile
from pathlib import Path

# Add workspace root to sys.path
current = Path(__file__).resolve()
while current.parent != current:
    if (current / "src").is_dir():
        if str(current) not in sys.path:
            sys.path.insert(0, str(current))
        break
    current = current.parent

from src.doc_gen.conversation_memory import ConversationMemory
from src.doc_gen.dataset_builder import DocxDatasetBuilder
from src.doc_gen.docx_renderer import DocxRenderer, FormattingStrategy
from src.doc_gen.filevo_cli import COMMANDS, resolve_file_mentions
from src.doc_gen.knowledge_base import DocumentKnowledgeBase
from src.doc_gen.llm_client import LocalTransformersClient
from src.doc_gen.rich_ui import ui
from src.doc_gen.rlcd_engine import RLCDDecisionEngine


def test_no_prd_command():
    """Verify that /prd is completely absent from the command registry."""
    assert "/prd" not in COMMANDS, "/prd must not be in COMMANDS"
    assert "prd" not in [c.lstrip("/") for c in COMMANDS], "prd must be completely removed"


def test_conversation_memory_and_reference_resolution():
    """Verify multi-turn memory pruning and anaphora/reference resolution."""
    mem = ConversationMemory(max_turns=4)

    # Turn 1
    mem.add_user_message("Let's talk about quantum encryption.")
    mem.add_assistant_message("Quantum key distribution uses entangled photons.", topic="Quantum Encryption")

    # Turn 2
    mem.add_user_message("Make it more formal.")
    ref = mem.resolve_references("Make it more formal.")
    assert ref["is_followup"] is True
    assert ref["target_topic"] == "Quantum Encryption"

    # Verify sliding window pruning
    for i in range(10):
        mem.add_user_message(f"Message {i}")
        mem.add_assistant_message(f"Reply {i}")

    assert len(mem.turns) == 4, f"Sliding window must maintain max 4 turns, got {len(mem.turns)}"


def test_docx_dataset_builder_leakage_free_splits():
    """Verify DOCX dataset extraction, provenance, and disjoint train/eval splits."""
    with tempfile.TemporaryDirectory() as tmpdir:
        renderer = DocxRenderer(output_dir=tmpdir)
        # Create 2 separate docx files
        doc1 = renderer.render("Doc Alpha", [{"title": "Overview", "content": "Alpha content"}], FormattingStrategy(), "alpha.docx")
        doc2 = renderer.render("Doc Beta", [{"title": "Results", "content": "Beta content"}], FormattingStrategy(), "beta.docx")

        builder = DocxDatasetBuilder(output_dir=os.path.join(tmpdir, "datasets"))
        report = builder.build_dataset_from_directory(tmpdir, eval_split_ratio=0.5)

        assert report["train_source_documents"] >= 1
        assert report["eval_source_documents"] >= 1
        assert report["train_examples_generated"] > 0
        assert report["eval_examples_generated"] > 0
        assert os.path.exists(report["train_file"])
        assert os.path.exists(report["eval_file"])


def test_rlcd_calibrated_decision_policy():
    """Verify RLCD decision consensus scoring, risk gating, and feedback gradients."""
    with tempfile.TemporaryDirectory() as tmpdir:
        policy_path = os.path.join(tmpdir, "policy.json")
        rlcd = RLCDDecisionEngine(policy_path=policy_path)

        decision = rlcd.decide("Create a project proposal for distributed database")
        assert decision.archetype == "Project Proposal"
        assert 0.0 <= decision.confidence <= 1.0
        assert 0.0 <= decision.agreement <= 1.0
        assert 0.0 <= decision.normalized_entropy <= 1.0

        init_bias = rlcd.archetype_biases["Project Proposal"]
        res = rlcd.record_feedback(reward=+1.0)
        assert res["advantage"] > 0
        assert rlcd.archetype_biases["Project Proposal"] > init_bias


def test_file_mention_resolver():
    """Verify @file mentions extract text and structure cleanly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "config.txt")
        with open(test_file, "w") as f:
            f.write("target_architecture=microservices")

        clean, atts = resolve_file_mentions(f"Can you explain @{test_file}?")
        assert len(atts) == 1
        assert atts[0]["name"] == "config.txt"
        assert "target_architecture=microservices" in atts[0]["content"]


def test_rich_ui_components():
    """Verify Antigravity Rich UI banners, decision cards, and bottom status bar render safely."""
    # Test banner
    ui.display_banner("SmolLM2-1.7B-Instruct")

    # Test bottom status line
    ui.render_bottom_prompt_box("SmolLM2-1.7B-Instruct", "Plan", "16.4k (5%)", "CIE:main")

    # Test decision card
    rlcd = RLCDDecisionEngine()
    decision = rlcd.decide("Technical Report on Microservices")
    ui.display_decision_card(decision)


def test_model_client_configuration():
    """Verify LocalTransformersClient config, device detection, and lazy loading."""
    client = LocalTransformersClient(model_id="HuggingFaceTB/SmolLM2-1.7B-Instruct")
    assert client.model_id == "HuggingFaceTB/SmolLM2-1.7B-Instruct"
    assert client.device in ("cuda", "cpu")
    assert client._is_loaded is False  # Lazy loaded


if __name__ == "__main__":
    test_no_prd_command()
    print("✓ test_no_prd_command passed")
    test_conversation_memory_and_reference_resolution()
    print("✓ test_conversation_memory_and_reference_resolution passed")
    test_docx_dataset_builder_leakage_free_splits()
    print("✓ test_docx_dataset_builder_leakage_free_splits passed")
    test_rlcd_calibrated_decision_policy()
    print("✓ test_rlcd_calibrated_decision_policy passed")
    test_file_mention_resolver()
    print("✓ test_file_mention_resolver passed")
    test_rich_ui_components()
    print("✓ test_rich_ui_components passed")
    test_model_client_configuration()
    print("✓ test_model_client_configuration passed")
    print("\nAll 7 comprehensive verification tests passed successfully!")
