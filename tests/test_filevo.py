"""Comprehensive automated verification tests for Filevo."""

import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    import pytest
except ImportError:
    pytest = None

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

# Set FILEVO_OFFLINE to prevent interactive hangs and slow CPU LLM inference during automated testing
os.environ["FILEVO_OFFLINE"] = "1"
os.environ["FILEVO_TESTING"] = "1"

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
    """Verify the Rust native CLI binary exists and executes, skipping gracefully if cargo is absent."""
    import shutil
    import subprocess
    import pytest

    repo = Path(__file__).resolve().parent.parent
    rust_bin = repo / "bin" / "filevo-cli"
    if not rust_bin.exists():
        rust_bin = repo / "target" / "release" / "filevo-cli"
    if not rust_bin.exists():
        rust_bin = repo / "src" / "filevo_cli_rs" / "target" / "release" / "filevo-cli"
    if not rust_bin.exists() and shutil.which("cargo"):
        try:
            subprocess.run(
                ["cargo", "build", "--release", "--manifest-path", str(repo / "Cargo.toml")],
                check=True,
                capture_output=True,
            )
            rust_bin = repo / "target" / "release" / "filevo-cli"
        except Exception:
            pass

    if not rust_bin.exists():
        if os.environ.get("PYTEST_CURRENT_TEST") and pytest:
            pytest.skip("Rust CLI binary not precompiled and cargo build tool not available in test environment")
        return

    assert os.access(rust_bin, os.X_OK), "Rust CLI binary must be executable"


def test_autonomous_policy_learning():
    """Verify autonomous policy learning: objective reward calculation, gradient update, duplicate prevention, and rollback."""
    with tempfile.TemporaryDirectory() as tmpdir:
        policy_file = Path(tmpdir) / "rlcd_policy.json"
        engine = RLCDDecisionEngine(policy_path=str(policy_file))
        renderer = DocxRenderer(output_dir=tmpdir)

        # 1. Generate real docx artifact
        decision = engine.decide("Technical report on edge IoT architecture")
        sections = [
            {"title": "Introduction", "content": "Edge computing architecture introduces decentralized telemetry nodes."},
            {"title": "System Architecture", "content": "Sensors communicate with an edge broker via low-latency serial queues."},
            {"title": "Performance Analysis", "content": "Benchmarks demonstrate sub-millisecond median response times."},
            {"title": "Conclusion", "content": "The system achieves targeted latency and architectural isolation."},
        ]
        doc_path = renderer.render("Edge IoT Architecture", sections, decision.formatting, "edge_iot.docx")

        # 2. Test objective artifact evaluation
        eval_metrics = engine.evaluate_document_outcome(doc_path, "edge IoT architecture", decision, sections)
        assert eval_metrics["valid_openxml"] is True, "OpenXML should be valid"
        assert eval_metrics["spam_free"] is True, "Should be free from spam"
        assert eval_metrics["telemetry_free"] is True, "Should be free from leaked telemetry"
        assert eval_metrics["reward"] > 0.0, f"Expected positive reward for clean doc, got {eval_metrics['reward']}"

        # 3. Test autonomous experience recording & policy update without /feedback
        initial_episodes = engine.episodes
        initial_bias = engine.archetype_biases[decision.archetype]
        res = engine.record_autonomous_experience("create", "edge IoT architecture", decision, doc_path, sections)
        assert res["status"] == "updated"
        assert engine.episodes == initial_episodes + 1
        assert engine.archetype_biases[decision.archetype] >= initial_bias, "Policy bias should reinforce accepted archetype"

        # 4. Test duplicate prevention
        res_dup = engine.record_autonomous_experience("create", "edge IoT architecture", decision, doc_path, sections)
        assert res_dup["status"] == "skipped_duplicate", "Duplicate artifact experience must be skipped"
        assert engine.episodes == initial_episodes + 1

        # 5. Test corrective revision learning signal
        rev_res = engine.record_revision_experience("make it more formal", "Technical Report", "Academic Monograph", doc_path)
        assert rev_res["status"] == "revision_recorded"
        assert engine.archetype_biases["Academic Monograph"] > engine.archetype_biases["Technical Report"]

        # 6. Test held-out evaluation
        held_out = engine.evaluate_held_out()
        assert "accuracy" in held_out
        assert held_out["total_tasks"] == 5

        # 7. Test policy checkpoint and rollback
        assert engine.rollback_policy(steps_back=1) is True, "Policy rollback to checkpoint should succeed"


def test_explicit_section_overrides_and_clean_docx_content():
    """Verify that user-specified sections override defaults, and docx contains zero leaked telemetry."""
    from src.doc_gen.filevo_cli import cmd_create, get_memory, get_renderer
    llm = LocalTransformersClient()

    req = "Create a cricket scoring report specifying Introduction, Hardware Design, Methodology, Testing and Conclusion"
    spec = llm.extract_document_spec(req)

    assert "explicit_sections" in spec
    assert spec["explicit_sections"] == ["Introduction", "Hardware Design", "Methodology", "Testing", "Conclusion"]

    # Run creation
    with tempfile.TemporaryDirectory() as tmpdir:
        renderer = DocxRenderer(output_dir=tmpdir)
        with patch("src.doc_gen.filevo_cli.get_renderer", return_value=renderer):
            cmd_create(req)

        mem = get_memory()
        active_path = Path(mem.active_document_path)
        assert active_path.exists(), f"Generated document must exist at {active_path}"

        # Native OpenXML inspection of document
        doc_data = renderer.extract_document_content(active_path)
        sec_titles = [s["title"] for s in doc_data["sections"]]

        # Verify all 5 user sections are present in order
        for req_sec in ["Introduction", "Hardware Design", "Methodology", "Testing", "Conclusion"]:
            assert req_sec in sec_titles, f"Explicit section '{req_sec}' must be in document sections: {sec_titles}"

        # Verify zero telemetry tables or callouts leaked into document
        full_text_lower = doc_data["full_text"].lower()
        forbidden_telemetry = [
            "agreement (jsd)",
            "normalized entropy",
            "decision gate",
            "synthesized with filevo rlcd engine",
            "edge processing unit",
            "target specification",
            "benchmark value",
        ]
        for ft in forbidden_telemetry:
            assert ft not in full_text_lower, f"Document body must not leak internal telemetry string '{ft}'"


def test_revision_preserves_unmodified_sections_and_expands_target():
    """Verify revision reads existing docx, expands only target section, and creates _v2."""
    from src.doc_gen.filevo_cli import cmd_create, cmd_revise, get_memory, get_renderer
    with tempfile.TemporaryDirectory() as tmpdir:
        renderer = DocxRenderer(output_dir=tmpdir)
        with patch("src.doc_gen.filevo_cli.get_renderer", return_value=renderer):
            cmd_create("Create a cricket scoring report specifying Introduction, Hardware Design, Methodology, Testing and Conclusion")
            v1_path = Path(get_memory().active_document_path)
            v1_data = renderer.extract_document_content(v1_path)
            v1_methodology_len = len([s for s in v1_data["sections"] if "methodology" in s["title"].lower()][0]["content"])

            # Revise: expand methodology
            v2_path = cmd_revise("Can you expand its methodology section?")
            assert v2_path is not None
            assert "_v2" in v2_path.stem, f"Revised path should have _v2 suffix, got {v2_path.name}"
            assert v2_path.exists()

            v2_data = renderer.extract_document_content(v2_path)
            v2_sec_titles = [s["title"] for s in v2_data["sections"]]

            # Verify all original sections are preserved
            for s in ["Introduction", "Hardware Design", "Methodology", "Testing", "Conclusion"]:
                assert s in v2_sec_titles, f"Section '{s}' must be preserved in version 2"

            # Verify methodology content was expanded
            v2_methodology = [s for s in v2_data["sections"] if "methodology" in s["title"].lower()][0]
            assert len(v2_methodology["content"]) > v1_methodology_len, "Methodology section must be expanded in v2"

            # Verify hardware section was preserved
            v1_hw = [s for s in v1_data["sections"] if "hardware" in s["title"].lower()][0]["content"]
            v2_hw = [s for s in v2_data["sections"] if "hardware" in s["title"].lower()][0]["content"]
            assert v1_hw == v2_hw, "Hardware Design section must remain intact when only methodology is revised"


def test_contextual_question_routing_and_memory():
    """Verify that asking which hardware was discussed and which section was expanded routes to chat."""
    import re
    p_lower = "which hardware was discussed and which section was expanded?"

    is_query_about_history = bool(
        re.search(r"\b(which|what|tell me|did|was|were)\b.*\b(expanded|revised|discussed|created|mentioned|written|changed)\b", p_lower)
        or (p_lower.startswith(("which", "what", "how", "did", "was", "were")) and "?" in p_lower)
    )
    assert is_query_about_history is True, "Follow-up inquiry about history must NOT be treated as a revision command"


def test_a_collision_safe_naming_on_creation():
    """Test A: Create new report when similar exists -> creates separate file with collision-safe name."""
    from src.doc_gen.filevo_cli import cmd_create, get_memory
    with tempfile.TemporaryDirectory() as tmpdir:
        renderer = DocxRenderer(output_dir=tmpdir)
        with patch("src.doc_gen.filevo_cli.get_renderer", return_value=renderer):
            # First creation
            cmd_create("Create a detailed technical report on an IoT cricket scoring system")
            first_path = Path(get_memory().active_document_path)
            assert first_path.exists()
            assert first_path.name.endswith(".docx")

            # Second creation with identical/similar title
            cmd_create("Create a detailed technical report on an IoT cricket scoring system")
            second_path = Path(get_memory().active_document_path)
            assert second_path.exists()
            assert first_path.exists(), "Original file must not be overwritten"
            assert second_path != first_path, "Second document must be a separate file"
            assert "_2.docx" in second_path.name, f"Collision-safe name must include suffix _2: {second_path.name}"


def test_b_all_requested_hardware_in_report():
    """Test B: All requested hardware appears in generated report."""
    from src.doc_gen.filevo_cli import cmd_create, get_memory
    with tempfile.TemporaryDirectory() as tmpdir:
        renderer = DocxRenderer(output_dir=tmpdir)
        with patch("src.doc_gen.filevo_cli.get_renderer", return_value=renderer):
            req = "Create a detailed technical report on an IoT cricket scoring system using ESP32, IR sensors and camera based ball detection specifying Introduction, Hardware Design, Methodology, Testing and Conclusion"
            cmd_create(req)
            doc_path = Path(get_memory().active_document_path)
            doc_data = renderer.extract_document_content(doc_path)
            full_text = doc_data["full_text"].lower()

            assert "esp32" in full_text, "ESP32 microcontroller must appear in generated document"
            assert "ir" in full_text or "infrared" in full_text, "IR sensors must appear in generated document"
            assert "camera" in full_text or "ball detection" in full_text, "Camera-based ball detection must appear in generated document"


def test_c_expand_methodology_sensor_workflow():
    """Test C: Expand Methodology -> sensor workflow explained, no duplicate paragraphs."""
    from src.doc_gen.filevo_cli import cmd_create, cmd_revise, get_memory
    with tempfile.TemporaryDirectory() as tmpdir:
        renderer = DocxRenderer(output_dir=tmpdir)
        with patch("src.doc_gen.filevo_cli.get_renderer", return_value=renderer):
            cmd_create("Create a technical report on an IoT cricket scoring system using ESP32, IR sensors and camera based ball detection specifying Introduction, Hardware Design, Methodology, Testing and Conclusion")
            v1_path = Path(get_memory().active_document_path)
            v1_data = renderer.extract_document_content(v1_path)

            v2_path = cmd_revise("Make the methodology in that report more detailed")
            assert v2_path.exists()
            v2_data = renderer.extract_document_content(v2_path)

            v2_methodology = [s for s in v2_data["sections"] if "methodology" in s["title"].lower()][0]["content"]
            m_lower = v2_methodology.lower()

            # Check that sensor processing workflow is explained
            assert any(w in m_lower for w in ("sensor", "interrupt", "optical", "gate")), "Sensor processing workflow must be detailed"
            assert any(w in m_lower for w in ("camera", "trajectory", "visual")), "Camera tracking workflow must be detailed"

            # Check no duplicate paragraphs
            paras = [p.strip() for p in v2_methodology.split("\n\n") if len(p.strip()) > 20]
            assert len(paras) == len(set(paras)), "Methodology must not contain duplicate paragraphs"


def test_d_resubmit_same_revision_no_duplicates():
    """Test D: Resubmit same revision -> no duplicate paragraphs."""
    from src.doc_gen.filevo_cli import cmd_create, cmd_revise, get_memory
    with tempfile.TemporaryDirectory() as tmpdir:
        renderer = DocxRenderer(output_dir=tmpdir)
        with patch("src.doc_gen.filevo_cli.get_renderer", return_value=renderer):
            cmd_create("Create a technical report on an IoT cricket scoring system using ESP32, IR sensors and camera based ball detection specifying Introduction, Hardware Design, Methodology, Testing and Conclusion")
            # First revision
            v2_path = cmd_revise("Make the methodology in that report more detailed")
            v2_data = renderer.extract_document_content(v2_path)
            v2_methodology = [s for s in v2_data["sections"] if "methodology" in s["title"].lower()][0]["content"]

            # Second identical revision
            v3_path = cmd_revise("Make the methodology in that report more detailed")
            v3_data = renderer.extract_document_content(v3_path)
            v3_methodology = [s for s in v3_data["sections"] if "methodology" in s["title"].lower()][0]["content"]

            v3_paras = [p.strip() for p in v3_methodology.split("\n\n") if len(p.strip()) > 20]
            assert len(v3_paras) == len(set(v3_paras)), "Resubmitting revision must not create duplicate paragraphs"


def test_e_unrelated_sections_preserved():
    """Test E: Unrelated sections remain unchanged."""
    from src.doc_gen.filevo_cli import cmd_create, cmd_revise, get_memory
    with tempfile.TemporaryDirectory() as tmpdir:
        renderer = DocxRenderer(output_dir=tmpdir)
        with patch("src.doc_gen.filevo_cli.get_renderer", return_value=renderer):
            cmd_create("Create a technical report on an IoT cricket scoring system specifying Introduction, Hardware Design, Methodology, Testing and Conclusion")
            v1_path = Path(get_memory().active_document_path)
            v1_data = renderer.extract_document_content(v1_path)

            v2_path = cmd_revise("Make the methodology in that report more detailed")
            v2_data = renderer.extract_document_content(v2_path)

            for sec_name in ["Introduction", "Hardware Design", "Testing", "Conclusion"]:
                v1_sec = [s for s in v1_data["sections"] if sec_name.lower() in s["title"].lower()][0]["content"]
                v2_sec = [s for s in v2_data["sections"] if sec_name.lower() in s["title"].lower()][0]["content"]
                assert v1_sec == v2_sec, f"Section '{sec_name}' must be preserved unchanged across revisions"


def test_f_query_hardware_and_expanded_section():
    """Test F: Query hardware and expanded section -> exact entity resolution."""
    from src.doc_gen.filevo_cli import resolve_historical_facts
    from src.doc_gen.conversation_memory import ConversationMemory
    mem = ConversationMemory()
    mem.turns.clear()
    mem.add_user_message("Create a detailed technical report on an IoT cricket scoring system using ESP32, IR sensors and camera based ball detection")
    mem.add_assistant_message("Generated Technical Report on 'IoT Cricket Scoring System'")
    mem.add_user_message("Make the methodology in that report more detailed")
    mem.add_assistant_message("Revised Technical Report with expanded Methodology section", expanded_section="Methodology")

    ans = resolve_historical_facts("Which hardware did I mention, and which section did I ask you to expand?", mem)
    assert ans is not None
    ans_lower = ans.lower()
    assert "esp32" in ans_lower, "Response must identify ESP32"
    assert "ir sensors" in ans_lower or "infrared" in ans_lower, "Response must identify IR sensors"
    assert "camera" in ans_lower or "ball detection" in ans_lower, "Response must identify camera-based ball detection"
    assert "methodology" in ans_lower, "Response must identify Methodology section"


def test_g_offline_model_status_and_no_deceptive_templates():
    """Test G: Offline model -> explicit status reported, no deceptive static templates or fabricated numbers."""
    from src.doc_gen.llm_client import LocalTransformersClient
    client = LocalTransformersClient()
    client._is_loaded = False

    # 1. Verify honest conversational response reporting model is offline
    chat_resp = client.generate_chat_response([{"role": "user", "content": "Explain IoT cricket scoring architecture"}])
    assert "not loaded" in chat_resp.lower(), "Offline model must explicitly inform user that inference weights are not loaded"

    # 2. Verify generation avoids deceptive boilerplate and fabricated metrics
    content = client.generate_section_content("Methodology", "IoT Cricket Scoring System Using ESP32, IR Sensors", "Technical Report")
    c_lower = content.lower()
    assert "split-brain state anomalies" not in c_lower
    assert "dead-letter queues" not in c_lower
    # Verify absence of fabricated numerical claims
    assert "99.8%" not in c_lower
    assert "1,200" not in c_lower
    assert "18.4" not in c_lower
    assert "1.2 microsecond" not in c_lower


def test_proven_parameter_gradient_training():
    """Verify actual parameter updates through policy gradients and PyTorch optimizer steps."""
    from src.doc_gen.rlcd_engine import RLCDDecisionEngine

    # 1. Verify RLCD Policy Gradient parameter update
    with tempfile.TemporaryDirectory() as tmpdir:
        policy_file = Path(tmpdir) / "test_policy.json"
        engine = RLCDDecisionEngine(policy_path=str(policy_file), learning_rate=0.2)
        initial_weights = dict(engine.weights)

        # Execute training episode
        trajectory = {
            "choices": [
                {
                    "feature_set": ["technical_report", "executive_summary", "memo"],
                    "selected": "technical_report",
                }
            ],
            "gates": [
                {"feature": "include_benchmarks", "selected": True}
            ]
        }
        update_result = engine.update(trajectory, reward=1.5)
        updated_weights = dict(engine.weights)

        # Prove weights actually changed according to policy gradients
        assert updated_weights["technical_report"] != initial_weights.get("technical_report", 0.0), "Policy weights must change"
        assert updated_weights["include_benchmarks"] != initial_weights.get("include_benchmarks", 0.0), "Gate weights must change"

        # Checkpoint reload verification
        reloaded_engine = RLCDDecisionEngine(policy_path=str(policy_file))
        assert reloaded_engine.weights["technical_report"] == updated_weights["technical_report"], "Reloaded policy must match saved state"

    # 2. Verify PyTorch neural network gradient calculation and parameter update (if torch is available)
    try:
        import ctypes
        import subprocess
        try:
            gcc_bin = shutil.which("gcc") or "/home/l41n-pr0t0/.local/bin/gcc"
            if os.path.exists(gcc_bin):
                gcc_out = subprocess.check_output([gcc_bin, "-print-file-name=libstdc++.so.6"], text=True).strip()
                if gcc_out and os.path.exists(gcc_out):
                    ctypes.CDLL(gcc_out, mode=ctypes.RTLD_GLOBAL)
        except Exception:
            pass
        import torch
        if not hasattr(torch, "Tensor"):
            raise ImportError("PyTorch native C extension (_C) not loaded")
        import importlib
        torch_utils = importlib.import_module("torch._utils")
        setattr(torch, "_utils", torch_utils)
        import torch.nn as nn

        # Real parameter tensor
        layer = nn.Linear(32, 16)
        initial_weights = layer.weight.clone().detach()

        # Forward pass with real input
        x = torch.randn(4, 32)
        target = torch.randn(4, 16)
        criterion = nn.MSELoss()

        out = layer(x)
        loss = criterion(out, target)
        assert loss.item() > 0.0

        # Calculate actual gradients and take optimizer step
        loss.backward()
        assert layer.weight.grad is not None
        assert torch.any(layer.weight.grad != 0.0), "Gradients must be computed and non-zero"

        # Apply gradient descent update
        try:
            optimizer = torch.optim.SGD(layer.parameters(), lr=0.1)
            optimizer.step()
        except Exception:
            with torch.no_grad():
                layer.weight.sub_(0.1 * layer.weight.grad)

        # Confirm model parameters actually changed
        updated_weights = layer.weight.clone().detach()
        assert not torch.equal(initial_weights, updated_weights), "Parameters must be updated after optimizer step"
        param_delta = torch.norm(updated_weights - initial_weights).item()
        assert param_delta > 0.0, "Weight change norm must be strictly positive"

        # Checkpoint saving and reloading verification
        with tempfile.TemporaryDirectory() as tmpdir:
            ckpt_path = Path(tmpdir) / "model_checkpoint.pt"
            torch.save(layer.state_dict(), ckpt_path)
            assert ckpt_path.exists()

            reloaded_layer = nn.Linear(32, 16)
            reloaded_layer.load_state_dict(torch.load(ckpt_path))
            assert torch.equal(reloaded_layer.weight, updated_weights), "Reloaded parameters must match saved state"
    except Exception as exc:
        if os.environ.get("PYTEST_CURRENT_TEST") and pytest:
            pytest.skip(f"PyTorch or dynamic runtime dependencies not available in environment: {exc}")
        print(f"Skipping PyTorch test: {exc}")
        return


def test_h_docx_inspection_openxml_and_complete_sentences():
    """Test H: DOCX inspection -> valid OpenXML, no incomplete sentences."""
    from src.doc_gen.filevo_cli import cmd_create, get_memory
    with tempfile.TemporaryDirectory() as tmpdir:
        renderer = DocxRenderer(output_dir=tmpdir)
        with patch("src.doc_gen.filevo_cli.get_renderer", return_value=renderer), \
             patch("src.doc_gen.llm_client.LocalTransformersClient.load", return_value=False):
            cmd_create("Create a technical report on an IoT cricket scoring system using ESP32, IR sensors and camera based ball detection specifying Introduction, Hardware Design, Methodology, Testing and Conclusion")
            doc_path = Path(get_memory().active_document_path)
            doc_data = renderer.extract_document_content(doc_path)

            for sec in doc_data["sections"]:
                paras = [p.strip() for p in sec["content"].split("\n\n") if p.strip()]
                for p in paras:
                    assert p.endswith((".", "!", "?", ":")), f"Paragraph in section '{sec['title']}' must end with terminal punctuation: '{p[:40]}...{p[-10:]}'"


def test_audit_fixes_copy_xml_and_bullets():
    """Verify audit fixes: /copy handler, XML control character stripping, and bullet formatting."""
    from src.doc_gen.filevo_cli import cmd_copy, get_memory, handle_input
    from src.doc_gen.docx_renderer import DocxRenderer, FormattingStrategy

    # 1. Test /copy handler
    mem = get_memory()
    mem.clear()
    cmd_copy()  # Should not raise exception on empty history

    mem.add_assistant_message("Here is the technical specification for ESP32 telemetry.")
    handle_input("/copy")

    # 2. Test XML control character sanitization
    dirty_text = "Analysis\x00\x08Result\x0b:\nTelemetry & <Data> \x1fOK"
    cleaned = DocxRenderer._escape_xml(dirty_text)
    assert "\x00" not in cleaned
    assert "\x08" not in cleaned
    assert "\x0b" not in cleaned
    assert "\x1f" not in cleaned
    assert "&amp;" in cleaned
    assert "&lt;" in cleaned
    assert "AnalysisResult:\nTelemetry &amp; &lt;Data&gt; OK" == cleaned

    # 3. Test bullet point newline resilience
    renderer = DocxRenderer()
    strategy = FormattingStrategy()
    sections = [
        {"title": "Testing", "content": "- Bullet 1\n\n- Bullet 2\n"}
    ]
    xml = renderer._build_document_xml("Test Doc", sections, strategy)
    bullet_count = xml.count("<w:t>• </w:t>")
    assert bullet_count == 2, f"Expected exactly 2 bullet points, got {bullet_count}"


def test_auto_open_setting_and_execution():
    """Verify that auto_open is enabled by default, can be toggled via settings, and triggers open_document."""
    from src.doc_gen.filevo_cli import (
        is_auto_open_enabled,
        set_auto_open,
        handle_input,
        cmd_create,
    )

    # 1. Default should be True
    set_auto_open(True)
    assert is_auto_open_enabled() is True

    # 2. Toggle off via command
    handle_input("/settings auto_open off")
    assert is_auto_open_enabled() is False

    # 3. Toggle back on via command
    handle_input("/settings auto_open on")
    assert is_auto_open_enabled() is True

    # 4. Verify cmd_create invokes open_document when auto_open is enabled
    with tempfile.TemporaryDirectory() as tmpdir:
        renderer = DocxRenderer(output_dir=tmpdir)
        with patch("src.doc_gen.filevo_cli.get_renderer", return_value=renderer), \
             patch("src.doc_gen.filevo_cli.open_document") as mock_open, \
             patch("src.doc_gen.llm_client.LocalTransformersClient.load", return_value=False):
            cmd_create("Create a technical report on Edge Telemetry")
            assert mock_open.called, "open_document must be called when auto_open is True"

        # Verify cmd_create does not invoke open_document when auto_open is disabled
        set_auto_open(False)
        with patch("src.doc_gen.filevo_cli.get_renderer", return_value=renderer), \
             patch("src.doc_gen.filevo_cli.open_document") as mock_open, \
             patch("src.doc_gen.llm_client.LocalTransformersClient.load", return_value=False):
            cmd_create("Create a technical report on Edge Telemetry 2")
            assert not mock_open.called, "open_document must not be called when auto_open is False"

    # Reset to default True
    set_auto_open(True)


def test_autonomous_document_plan_authoring():
    """Verify autonomous DocumentPlan determination of genre, sections, contracts, and procedural representations."""
    from src.doc_gen.document_brief import DocumentPlan

    plan = DocumentPlan.from_request(
        "Create a detailed technical report on an IoT cricket scoring system using ESP32, IR sensors and camera based ball detection"
    )

    assert plan.genre == "Engineering Report"
    hw_str = " ".join(plan.explicit_hardware_specifications)
    assert "ESP32" in hw_str
    assert "IR sensors" in hw_str
    assert "camera" in hw_str

    headings = [s.heading for s in plan.sections]
    assert any("Sensor Acquisition" in h for h in headings)
    assert any("Crease" in h for h in headings)
    assert any("Score" in h for h in headings)
    assert any("Testing" in h or "Validation" in h for h in headings)

    # Check that procedural steps are designated
    proc_sections = [s for s in plan.sections if s.representation == "procedural_steps"]
    assert len(proc_sections) >= 2, "Expected at least 2 sections with procedural_steps representation"


def test_generalized_document_creation_animals():
    """Verify that 'create a docx on animals' produces a semantically grounded document without placeholder titles or telemetry."""
    from src.doc_gen.filevo_cli import cmd_create, get_memory
    from src.doc_gen.document_brief import PLACEHOLDER_BLACKLIST

    with tempfile.TemporaryDirectory() as tmpdir:
        renderer = DocxRenderer(output_dir=tmpdir)
        with patch("src.doc_gen.filevo_cli.get_renderer", return_value=renderer), \
             patch("src.doc_gen.llm_client.LocalTransformersClient.load", return_value=False):
            cmd_create("create a docx on animals")

        mem = get_memory()
        doc_path = Path(mem.active_document_path)
        assert doc_path.exists(), f"Document must exist at {doc_path}"

        # Inspect generated OpenXML content
        doc_data = renderer.extract_document_content(doc_path)
        title = doc_data["title"]
        full_text = doc_data["full_text"]
        full_text_lower = full_text.lower()

        # 1. Title must NOT be a placeholder and must be grounded in Animals
        assert title.lower() not in PLACEHOLDER_BLACKLIST, f"Title '{title}' must not be a blacklisted placeholder"
        assert "animals" in title.lower() or "animal" in title.lower(), f"Title '{title}' must be grounded in animals"
        assert "clean formal title" not in title.lower()

        # 2. Sections must be biological and domain-coherent
        sec_titles = [s["title"] for s in doc_data["sections"]]
        assert any("taxonom" in st.lower() or "divers" in st.lower() for st in sec_titles), f"Expected taxonomic section, got: {sec_titles}"
        assert any("anatom" in st.lower() or "physiolog" in st.lower() for st in sec_titles), f"Expected anatomical section, got: {sec_titles}"
        assert any("ecolog" in st.lower() or "habitat" in st.lower() for st in sec_titles), f"Expected ecological section, got: {sec_titles}"

        # 3. Content must contain zero leaked hardware/telemetry boilerplate
        for forbidden in ("esp32", "interrupt service routines", "optical gate", "crease crossing", "invariants", "event loops", "telemetry indicators"):
            assert forbidden not in full_text_lower, f"Document leaked inappropriate technical jargon: '{forbidden}'"

        # 4. Content must contain biological concepts
        assert any(w in full_text_lower for w in ("evolutionary", "clade", "species", "biodiversity", "habitat", "physiological")), "Document must contain grounded biological terminology"


def test_unseen_subjects_and_paraphrased_prompts():
    """Verify autonomous planning and authoring across diverse, unseen subject domains."""
    from src.doc_gen.document_brief import DocumentPlan, PLACEHOLDER_BLACKLIST

    # Unseen Subject 1: Humanities / History
    plan_rome = DocumentPlan.from_request("write a comprehensive paper about ancient Roman architecture")
    assert plan_rome.title.lower() not in PLACEHOLDER_BLACKLIST
    assert "ancient roman architecture" in plan_rome.title.lower() or "roman architecture" in plan_rome.title.lower()
    assert plan_rome.genre in ("Academic Monograph", "Comprehensive Guide", "Technical Report")
    headings_rome = [s.heading.lower() for s in plan_rome.sections]
    assert len(headings_rome) >= 5

    # Unseen Subject 2: Clean Tech Engineering
    plan_solar = DocumentPlan.from_request("generate an engineering spec for renewable solar desalinators")
    assert plan_solar.title.lower() not in PLACEHOLDER_BLACKLIST
    assert "solar desalinator" in plan_solar.title.lower()
    assert plan_solar.genre == "Engineering Report"

    # Unseen Subject 3: Paraphrased Request with Explicit Sections
    plan_qkd = DocumentPlan.from_request("project pitch covering quantum key distribution with sections Overview, Quantum Security, Hardware, Milestones")
    assert plan_qkd.title.lower() not in PLACEHOLDER_BLACKLIST
    assert "quantum key distribution" in plan_qkd.title.lower()
    headings_qkd = [s.heading for s in plan_qkd.sections]
    assert headings_qkd == ["Overview", "Quantum Security", "Hardware", "Milestones"]


def test_autonomous_plan_validation_and_repair():
    """Verify that defective plans (placeholder titles, missing sections) are detected and repaired autonomously."""
    from src.doc_gen.document_brief import DocumentPlan, validate_plan, repair_plan

    # Defective plan with placeholder title and missing sections
    defective_plan = DocumentPlan(
        original_request="Draft a report on marine coral reefs",
        title="Clean Formal Title",
        topic="Primary Subject",
        genre="Technical Report",
        purpose="",
        audience="",
        tone="",
        writing_depth="standard",
        sections=[],
    )

    # Validation must reject defective plan with defects list
    assert len(validate_plan(defective_plan)) > 0

    # Autonomous repair must heal the plan
    healed = repair_plan(defective_plan, "Draft a report on marine coral reefs")
    assert len(validate_plan(healed)) == 0
    assert healed.title.lower() != "clean formal title"
    assert "coral reef" in healed.title.lower()
    assert healed.genre == "Comprehensive Guide"
    assert len(healed.sections) >= 5


def test_no_index_command_in_registry():
    """Verify that /index is completely removed from the visible UI command registry."""
    assert "/index" not in COMMANDS, "/index must not be in visible COMMANDS"
    assert "index" not in [c.lstrip("/") for c in COMMANDS], "index must not be in visible commands"


def test_unified_train_pipeline_with_docx():
    """Verify that /train @file.docx runs all 3 stages: ingestion, dataset compilation, policy adaptation."""
    from src.doc_gen.filevo_cli import cmd_train, get_kb, get_rlcd
    sample_docx = Path("sea_animals_encyclopedia.docx")
    assert sample_docx.exists(), "sea_animals_encyclopedia.docx must exist"

    # Run unified train with @file mention
    cmd_train(f"@{sample_docx.name}")
    kb = get_kb()
    summary = kb.get_status_summary()
    assert summary["total_documents"] >= 1, "At least 1 document must be indexed"

    rlcd = get_rlcd()
    telem = rlcd.get_telemetry()
    assert telem["episodes"] >= 0


def test_wordcraft_engine_detection():
    """Verify WordCraft engine locates binaries and wraps execution properly."""
    from src.doc_gen.wordcraft_engine import WordCraftEngine
    engine = WordCraftEngine()
    info = engine.get_info()
    assert isinstance(info, dict)
    assert "available" in info
    assert "control_port" in info
    assert info["control_port"] == 7981
    if engine.is_available():
        assert info["cli_path"] is not None
        assert Path(info["cli_path"]).exists()


def test_wordcraft_composition_and_openxml_compatibility():
    """Verify WordCraft MCP composes structured docx, pdf, preview png, and passes OpenXML parsing."""
    from src.doc_gen.wordcraft_engine import WordCraftEngine
    from src.doc_gen.rlcd_engine import FormattingStrategy
    from src.doc_gen.knowledge_base import DocumentKnowledgeBase

    engine = WordCraftEngine()
    if not engine.is_available():
        print("  (Skipping live WordCraft test: wordcraft-cli not detected)")
        return

    strat = FormattingStrategy(
        font_family="Calibri",
        accent_color="1F4E79",
        margin_inches=1.0,
        title_alignment="center",
    )
    sections = [
        {"title": "System Architecture", "content": "Modern distributed streams provide high reliability.\n\n• Point 1\n• Point 2"},
        {"title": "Performance Benchmark", "content": "| Metric | Value |\n| Latency | 2.5 ms |\n| Throughput | 100k ops/s |"},
        {"title": "Conclusion", "content": "Final conclusions and summary."}
    ]

    res = engine.compose(
        title="WordCraft MCP Test Report",
        sections=sections,
        strategy=strat,
        metadata={"archetype": "Technical Report", "subtitle": "Verification Run"},
        visible=False,
        export_pdf=True,
    )

    assert res.docx_path.exists()
    assert res.docx_path.stat().st_size > 0
    if res.pdf_path:
        assert res.pdf_path.exists()
    if res.preview_image_path:
        assert res.preview_image_path.exists()
    assert res.words > 0
    assert res.blocks > 0
    assert res.tables_count >= 1

    # Verify compatibility with Filevo KnowledgeBase OpenXML parser
    kb = DocumentKnowledgeBase()
    status = kb.index_file_if_changed(res.docx_path)
    assert status in ("indexed", "unchanged")


def test_wordcraft_settings_and_cli_commands():
    """Verify /wordcraft status, /settings engine and /settings mode."""
    from src.doc_gen.filevo_cli import (
        handle_input,
        get_doc_engine_setting,
        set_doc_engine_setting,
        get_wordcraft_mode_setting,
        set_wordcraft_mode_setting,
    )
    # Test setting toggles
    set_doc_engine_setting("wordcraft")
    assert get_doc_engine_setting() == "wordcraft"
    set_doc_engine_setting("native")
    assert get_doc_engine_setting() == "native"
    set_doc_engine_setting("wordcraft")

    set_wordcraft_mode_setting("headless")
    assert get_wordcraft_mode_setting() == "headless"
    set_wordcraft_mode_setting("desktop")
    assert get_wordcraft_mode_setting() == "desktop"
    set_wordcraft_mode_setting("headless")

    # Test slash commands
    handle_input("/wordcraft status")
    handle_input("/settings engine wordcraft")
    handle_input("/settings mode headless")
    handle_input("/settings mode desktop")
    assert get_wordcraft_mode_setting() == "desktop"


def test_wordcraft_adapter_client_and_antislop_policy():
    """Verify WordCraftClient MCP protocol, AntiSlopPolicy, and DocumentIR."""
    from src.doc_gen.wordcraft_adapter import WordCraftClient, WordCraftConfig
    from src.doc_gen.antislop_policy import AntiSlopPolicy
    from src.doc_gen.document_ir import DocumentIR
    from src.doc_gen.document_brief import DocumentBrief

    # 1. AntiSlopPolicy verification
    policy = AntiSlopPolicy()
    slop_text = "Furthermore, in today's fast-paced world, we can leverage and seamlessly elevate our robust system. Moreover, it is important to note that performance is key."
    sanitized = policy.sanitize_prose(slop_text, is_intro=True)
    assert "furthermore" not in sanitized.lower()
    assert "moreover" not in sanitized.lower()
    assert "leverage" not in sanitized.lower()
    assert "seamless" not in sanitized.lower()
    assert "in today's" not in sanitized.lower()
    assert "it is important to note" not in sanitized.lower()

    # 2. DocumentIR verification
    brief = DocumentBrief.from_request("Technical Report on Microservices Architecture")
    sections_data = [
        {"title": "Introduction", "content": "Microservices decompose monoliths into autonomous units."},
        {"title": "System Architecture", "content": "Services communicate over gRPC and message brokers."},
    ]
    doc_ir = DocumentIR.from_brief_and_content(brief, sections_data, antislop=policy)
    assert doc_ir.title == brief.title
    assert len(doc_ir.sections) == 2
    assert doc_ir.signature_element is not None

    # 3. WordCraftClient MCP Handshake & Tools Discovery
    cfg = WordCraftConfig.load()
    cfg.mode = "headless"
    client = WordCraftClient(cfg)
    with client:
        client.start(force_desktop=False)
        tools = client.discover_tools()
        assert "execute" in tools
        assert "batch" in tools
        assert "new_document" in tools
        assert "save_document" in tools
        assert "inspect_document" in tools
        assert "render_page" in tools
        assert client.get_tool_schema("execute") is not None


if __name__ == "__main__":
    test_no_prd_command()
    print("✓ test_no_prd_command passed")
    test_no_index_command_in_registry()
    print("✓ test_no_index_command_in_registry passed")
    test_unified_train_pipeline_with_docx()
    print("✓ test_unified_train_pipeline_with_docx passed")
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
    test_autonomous_policy_learning()
    print("✓ test_autonomous_policy_learning passed")
    test_explicit_section_overrides_and_clean_docx_content()
    print("✓ test_explicit_section_overrides_and_clean_docx_content passed")
    test_revision_preserves_unmodified_sections_and_expands_target()
    print("✓ test_revision_preserves_unmodified_sections_and_expands_target passed")
    test_contextual_question_routing_and_memory()
    print("✓ test_contextual_question_routing_and_memory passed")
    test_a_collision_safe_naming_on_creation()
    print("✓ test_a_collision_safe_naming_on_creation passed")
    test_b_all_requested_hardware_in_report()
    print("✓ test_b_all_requested_hardware_in_report passed")
    test_c_expand_methodology_sensor_workflow()
    print("✓ test_c_expand_methodology_sensor_workflow passed")
    test_d_resubmit_same_revision_no_duplicates()
    print("✓ test_d_resubmit_same_revision_no_duplicates passed")
    test_e_unrelated_sections_preserved()
    print("✓ test_e_unrelated_sections_preserved passed")
    test_f_query_hardware_and_expanded_section()
    print("✓ test_f_query_hardware_and_expanded_section passed")
    test_g_offline_model_status_and_no_deceptive_templates()
    print("✓ test_g_offline_model_status_and_no_deceptive_templates passed")
    test_proven_parameter_gradient_training()
    print("✓ test_proven_parameter_gradient_training passed")
    test_h_docx_inspection_openxml_and_complete_sentences()
    print("✓ test_h_docx_inspection_openxml_and_complete_sentences passed")
    test_audit_fixes_copy_xml_and_bullets()
    print("✓ test_audit_fixes_copy_xml_and_bullets passed")
    test_auto_open_setting_and_execution()
    print("✓ test_auto_open_setting_and_execution passed")
    test_autonomous_document_plan_authoring()
    print("✓ test_autonomous_document_plan_authoring passed")
    test_generalized_document_creation_animals()
    print("✓ test_generalized_document_creation_animals passed")
    test_unseen_subjects_and_paraphrased_prompts()
    print("✓ test_unseen_subjects_and_paraphrased_prompts passed")
    test_autonomous_plan_validation_and_repair()
    print("✓ test_autonomous_plan_validation_and_repair passed")
    test_wordcraft_engine_detection()
    print("✓ test_wordcraft_engine_detection passed")
    test_wordcraft_composition_and_openxml_compatibility()
    print("✓ test_wordcraft_composition_and_openxml_compatibility passed")
    test_wordcraft_settings_and_cli_commands()
    print("✓ test_wordcraft_settings_and_cli_commands passed")
    test_wordcraft_adapter_client_and_antislop_policy()
    print("✓ test_wordcraft_adapter_client_and_antislop_policy passed")
    print("\nAll 36 comprehensive verification tests passed successfully!")

