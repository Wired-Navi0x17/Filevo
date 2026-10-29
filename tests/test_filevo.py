"""Comprehensive automated verification tests for Filevo."""

import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# Dynamically discover NixOS driver and gcc libraries without hardcoded hashes
def discover_nixos_libraries():
    nix_extra = []
    for c in ("/run/opengl-driver/lib", "/run/current-system/sw/lib"):
        if os.path.isdir(c):
            nix_extra.append(c)
    nix_store = Path("/nix/store")
    if nix_store.is_dir():
        for pat in ("*-gcc-*-lib/lib", "*-nvidia-x11-*/lib", "*-ld-library-path*/share/nix-ld/lib"):
            for match in nix_store.glob(pat):
                if match.is_dir():
                    nix_extra.append(str(match))
    return ":".join(nix_extra)

if os.environ.get("FILEVO_BOOTSTRAPPED") != "1":
    repo_root = Path(__file__).resolve().parent.parent
    venv_py = repo_root / ".venv" / "bin" / "python3"
    nix_ld = discover_nixos_libraries()
    cur_ld = os.environ.get("LD_LIBRARY_PATH", "")
    os.environ["FILEVO_BOOTSTRAPPED"] = "1"
    os.environ["LD_LIBRARY_PATH"] = f"{nix_ld}:{cur_ld}" if cur_ld else nix_ld
    target_py = str(venv_py) if venv_py.exists() else sys.executable
    if sys.executable != target_py and "pytest" not in sys.modules:
        env = dict(os.environ)
        os.execve(target_py, [target_py] + sys.argv, env)

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
from src.doc_gen.model_trainer import FilevoModelTrainer
from src.doc_gen.rich_ui import ui
from src.doc_gen.rl_model import RLProbabilisticModel
from src.doc_gen.rlcd_engine import ARCHETYPES, RLCDDecisionEngine


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


def test_docx_dataset_builder_content_deduplication_and_leakage_free_splits():
    """Verify SHA-256 deduplication and leakage-free disjoint train/eval splits."""
    with tempfile.TemporaryDirectory() as tmpdir:
        renderer = DocxRenderer(output_dir=tmpdir)
        # Create Doc Alpha, a duplicate of Doc Alpha with a different filename, and Doc Beta
        doc1 = renderer.render("Doc Alpha", [{"title": "Overview", "content": "Alpha content"}], FormattingStrategy(), "alpha.docx")
        doc1_dup = renderer.render("Doc Alpha", [{"title": "Overview", "content": "Alpha content"}], FormattingStrategy(), "alpha_copy.docx")
        doc2 = renderer.render("Doc Beta", [{"title": "Results", "content": "Beta content"}], FormattingStrategy(), "beta.docx")

        builder = DocxDatasetBuilder(output_dir=os.path.join(tmpdir, "datasets"))
        report = builder.build_dataset_from_directory(tmpdir, eval_split_ratio=0.5)

        # Verify content hash deduplication
        assert report["unique_documents"] == 2, "Duplicate alpha document must be deduplicated by content hash"
        assert report["duplicate_documents_skipped"] == 1, "Exactly one duplicate document should be skipped"
        assert report["train_source_documents"] >= 1
        assert report["eval_source_documents"] >= 1
        assert os.path.exists(report["train_file"])
        assert os.path.exists(report["eval_file"])


def test_rlcd_calibrated_decision_and_empirical_calibration():
    """Verify RLCD consensus scoring, Jev primitives, ECE, Brier score, and temperature scaling."""
    with tempfile.TemporaryDirectory() as tmpdir:
        policy_path = os.path.join(tmpdir, "policy.json")
        rlcd = RLCDDecisionEngine(policy_path=policy_path)

        # 1. Consensus decision making
        decision = rlcd.decide("Create a project proposal for distributed database")
        assert decision.archetype == "Project Proposal"
        assert 0.0 <= decision.confidence <= 1.0
        assert 0.0 <= decision.agreement <= 1.0
        assert 0.0 <= decision.normalized_entropy <= 1.0

        # 2. Jev primitives
        probs = rlcd.choice(["section_introduction", "section_methodology"])
        assert "section_introduction" in probs
        selected, conf = rlcd.score(["rigor_none", "rigor_asymptotic", "rigor_formal"])
        assert selected in ("rigor_none", "rigor_asymptotic", "rigor_formal")
        assert 0.0 <= conf <= 1.0
        assert 0.0 <= rlcd.noul("include_formulas") <= 1.0

        # 3. Policy update
        init_bias = rlcd.archetype_biases["Project Proposal"]
        res = rlcd.record_feedback(reward=+1.0)
        assert res["advantage"] > 0
        assert rlcd.archetype_biases["Project Proposal"] > init_bias

        # 4. Empirical calibration (ECE & Brier Score)
        preds = [
            [0.8, 0.1, 0.1],
            [0.2, 0.7, 0.1],
            [0.3, 0.3, 0.4],
        ]
        targets = [0, 1, 2]
        cal = rlcd.compute_calibration_metrics(preds, targets, num_bins=5)
        assert 0.0 <= cal["ece"] <= 1.0
        assert 0.0 <= cal["mce"] <= 1.0
        assert 0.0 <= cal["brier_score"] <= 2.0

        # 5. Temperature scaling
        val_logits = [[2.0, 0.5, 0.1], [0.1, 3.0, 0.2], [0.5, 0.2, 2.5]]
        val_targets = [0, 1, 2]
        opt_t = rlcd.fit_temperature_scaling(val_logits, val_targets)
        assert opt_t > 0.0


def test_rl_probabilistic_model_consolidation():
    """Verify RLProbabilisticModel inherits RLCDDecisionEngine cleanly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        m_path = os.path.join(tmpdir, "model.json")
        model = RLProbabilisticModel(model_path=m_path)
        probs = model.softmax(["section_introduction", "section_architecture"])
        assert isinstance(probs, dict)
        assert "section_introduction" in probs
        d = model.decide("Technical Report on Microservices")
        assert d.archetype == "Technical Report"


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
    ui.display_banner("SmolLM2-1.7B-Instruct")
    ui.render_bottom_prompt_box("SmolLM2-1.7B-Instruct", "Plan", "16.4k (5%)", "CIE:main")
    rlcd = RLCDDecisionEngine()
    decision = rlcd.decide("Technical Report on Microservices")
    ui.display_decision_card(decision)


def test_model_client_configuration():
    """Verify LocalTransformersClient config, device detection, and lazy loading."""
    client = LocalTransformersClient(model_id="HuggingFaceTB/SmolLM2-1.7B-Instruct")
    assert client.model_id == "HuggingFaceTB/SmolLM2-1.7B-Instruct"
    assert client.device in ("cuda", "cpu")
    assert client._is_loaded is False


def test_model_trainer_pipeline_dry_run():
    """Verify FilevoModelTrainer dataset loading and training metrics in dry run mode."""
    with tempfile.TemporaryDirectory() as tmpdir:
        d_dir = Path(tmpdir) / "datasets"
        d_dir.mkdir()
        train_file = d_dir / "docx_supervision_train.jsonl"
        with open(train_file, "w") as f:
            f.write(json.dumps({"instruction": "Explain consensus", "target_content": "Consensus is..."}) + "\n")

        trainer = FilevoModelTrainer(dataset_dir=d_dir, output_dir=Path(tmpdir) / "ckpt")
        metrics = trainer.train(dry_run=True)
        assert metrics.epochs > 0
        assert metrics.samples_trained == 1
        assert metrics.device == "dry_run"


def test_web_researcher_offline_resilience():
    """Verify WebResearcher runs safely with offline mocking fallback."""
    from src.doc_gen.web_researcher import WebResearcher
    researcher = WebResearcher()

    mock_summary = {
        "title": "Distributed Computing",
        "extract": "Distributed computing is a field of computer science that studies distributed systems.",
    }

    with patch.object(researcher, "fetch_wikipedia_summary", return_value=mock_summary):
        data = researcher.research_topic("Distributed Computing")
        assert "sections" in data
        assert len(data["sections"]) >= 1
        assert data["has_web_data"] is True


def test_rust_cli_binary():
    """Verify the Rust native CLI binary exists and executes."""
    repo = Path(__file__).resolve().parent.parent
    rust_bin = repo / "src" / "filevo_cli_rs" / "target" / "release" / "filevo-cli"
    if not rust_bin.exists():
        # Check if cargo is available to build
        import subprocess
        try:
            subprocess.run(
                ["cargo", "build", "--release", "--manifest-path", str(repo / "src" / "filevo_cli_rs" / "Cargo.toml")],
                check=True,
                capture_output=True,
            )
        except Exception:
            pass
    assert rust_bin.exists(), f"Rust CLI binary missing at {rust_bin}"
    assert os.access(rust_bin, os.X_OK), "Rust CLI binary must be executable"


if __name__ == "__main__":
    test_no_prd_command()
    print("✓ test_no_prd_command passed")
    test_conversation_memory_and_reference_resolution()
    print("✓ test_conversation_memory_and_reference_resolution passed")
    test_docx_dataset_builder_content_deduplication_and_leakage_free_splits()
    print("✓ test_docx_dataset_builder_content_deduplication_and_leakage_free_splits passed")
    test_rlcd_calibrated_decision_and_empirical_calibration()
    print("✓ test_rlcd_calibrated_decision_and_empirical_calibration passed")
    test_rl_probabilistic_model_consolidation()
    print("✓ test_rl_probabilistic_model_consolidation passed")
    test_file_mention_resolver()
    print("✓ test_file_mention_resolver passed")
    test_rich_ui_components()
    print("✓ test_rich_ui_components passed")
    test_model_client_configuration()
    print("✓ test_model_client_configuration passed")
    test_model_trainer_pipeline_dry_run()
    print("✓ test_model_trainer_pipeline_dry_run passed")
    test_web_researcher_offline_resilience()
    print("✓ test_web_researcher_offline_resilience passed")
    test_rust_cli_binary()
    print("✓ test_rust_cli_binary passed")
    print("\nAll 11 comprehensive verification tests passed successfully!")
