# Filevo Project: Development TODO & Verification Checklist

> **Rule**: Items in this list are marked as completed `[x]` **only after user review and explicit approval**.  
> The agent must ask the user whether each item is completed before updating this file.

---

### Task 1: Local Hugging Face Transformers Conversational Engine (`src/doc_gen/llm_client.py`)
- [ ] **1.1 Model Selection & Evaluator**:
  - Benchmark candidate lightweight instruction models on 16 GB VRAM (e.g. `HuggingFaceTB/SmolLM2-1.7B-Instruct`, `Qwen/Qwen2.5-1.5B-Instruct`, and `HuggingFaceTB/SmolLM-360M-Instruct`).
  - Measure inference latency, VRAM usage, and output quality on conversational tasks (greetings, technical questions, document instructions).
  - Select the primary model based on measured task performance rather than model branding alone.
- [ ] **1.2 Configurable Model Client**:
  - Keep the model identifier configurable via config (`~/.filevo/config.json`) or environment variable (`FILEVO_MODEL_ID`).
  - Support automatic downloading of weights when online, running from Hugging Face local cache offline, and reporting real missing dependencies if not found (no fabricated mock strings).
- [ ] **1.3 Genuine Conversational & Structured Output Pipeline**:
  - Every ordinary user message reaches the loaded model.
  - The model handles arbitrary greetings (`"sup"`, `"hello"`), explanations, technical questions, and document requests without any hardcoded phrase tables.
  - Extract structured action decisions (e.g., action type, target parameters) from model outputs when tool operations are required.

---

### Task 2: Multi-Turn Conversational Memory (`src/doc_gen/conversation_memory.py`)
- [ ] **2.1 Session Turn Tracking**:
  - Maintain a sliding window of recent conversation turns (user input and assistant response).
  - Ensure prompt context is pruned cleanly so tokens do not grow unbounded.
- [ ] **2.2 Anaphora & Context Resolution**:
  - Enable follow-up instructions to resolve references to previously discussed topics or generated documents (e.g., *"make it more formal"*, *"expand the second section"*, *"regenerate that in navy blue"*).
  - Track active document state and attached `@file` references across consecutive turns.

---

### Task 3: DOCX Supervision Dataset Preparation Pipeline (`src/doc_gen/dataset_builder.py`)
- [ ] **3.1 Structural & Formatting Feature Extraction**:
  - Build a dataset builder that extracts text, heading levels ($H_1, H_2, H_3$), paragraph styles, tables, lists, and formatting conventions from user-supplied DOCX files.
- [ ] **3.2 Task-Output Separation & Data Leakage Prevention**:
  - Distinguish the source document from its prompt instruction (avoid blindly creating naive copy-paste prompt pairs).
  - Generate instruction-outline-content pairs for document generation tasks.
  - Separate training and evaluation datasets by source document to avoid data leakage.
- [ ] **3.3 General Instruction Mixing & Provenance Tracking**:
  - Mix general conversational examples to preserve the model's base dialogue abilities.
  - Track source document provenance (file hash, title, origin) and deduplicate data.
  - Report dataset metrics and limitations honestly.

---

### Task 4: Filevo Trainable Calibrated Decision Policy (`src/doc_gen/rlcd_engine.py`)
- [ ] **4.1 Filevo Policy Architecture**:
  - Implement Filevo's own calibrated decision policy (dual-perspective scoring: structural prior + learned policy prior).
  - Output typed decision objects with probabilities for archetype and formatting selection.
- [ ] **4.2 Policy Optimization**:
  - Optimize policy parameters via REINFORCE policy gradients based on user feedback (`/feedback`).
  - Self-adapt baseline priors from empirical distributions in the indexed knowledge base.

---

### Task 5: Separate Two-Track Input Orchestration (`src/doc_gen/filevo_cli.py`)
- [ ] **5.1 Pathway A (Deterministic Slash Commands)**:
  - Explicit slash commands (`/create`, `/analyze`, `/index`, `/train`, `/feedback`, `/model`, `/status`, `/clear`, `/exit`) use strict argument parsing and reliable execution.
- [ ] **5.2 Pathway B (Natural Language Model Pipeline)**:
  - All ordinary text routes through the multi-turn conversational model.
  - Never use keyword prefixes (such as requiring *"create"*) to decide intent.

---

### Task 6: Antigravity-Style Rich Terminal Interface (`src/doc_gen/rich_ui.py`)
- [ ] **6.1 Modern Antigravity Styling**:
  - Design polished terminal screens using `rich`: dark matte panels, vibrant cyan headers, and status dots.
  - Provide live animated spinners for model inference, OpenXML rendering, and file parsing.
- [ ] **6.2 Real Live Progress & Graceful Fallback**:
  - Real-time progress bars for document indexing and policy training (reflecting actual work, zero fake delays).
  - Support dumb terminals (non-TTY) without animation errors, and handle Ctrl+C cancellation gracefully.
- [ ] **6.3 Colorized Interface & Bottom-Pinned Input Box (Antigravity/OpenCode Aesthetic)**:
  - Use Rich to colorize the entire CLI interface (dark slate palette, cyan/amber accents, syntax-highlighted code/markdown, custom rule dividers).
  - Position the prompt area at the very bottom with a styled status bar header (active model, session mode, context size), vertical accent line, and subtle keybinding hints (`ctrl+c cancel`, `tab complete`).

---

### Task 7: Virtual Environment, NixOS Library Linking & Comprehensive Testing
- [ ] **7.1 NixOS Driver & Library Configuration**:
  - Ensure launchers (`report` and `report-train`) configure `LD_LIBRARY_PATH` with NixOS driver libraries (`libcuda.so`, `libstdc++.so.6`, `libz.so.1`) so PyTorch CUDA and Transformers run reliably on the 16 GB RTX 4090 GPU.
- [ ] **7.2 Verification Test Suite**:
  - Test arbitrary inputs without hardcoded replies.
  - Test multi-turn conversational follow-up resolution.
  - Test DOCX dataset preparation and policy updates.

---

### Task 8: Web Research & Live Topic Exploration Engine (`src/doc_gen/web_researcher.py`)
- [ ] **8.1 Automatic Web Research on Unknown/Unindexed Topics**:
  - Detect when a requested topic is unfamiliar, absent from the local knowledge base, or explicitly flagged for web research.
  - Query web search and knowledge sources (DuckDuckGo, Wikipedia API) to retrieve real-time facts, summaries, key sections, and reference citations.
- [ ] **8.2 Knowledge Synthesis & Document Context Enrichment**:
  - Clean and summarize fetched web text, extracting structural outline headings and rich technical content.
  - Inject researched context into the RLCD decision engine and DOCX generation pipeline so documents contain accurate, up-to-date facts.
- [ ] **8.3 Conversational Web Browsing Integration**:
  - Enable conversational queries to search and browse the web on demand with source attribution.

---

### Task 9: High-Performance Rust Native CLI Interface (`src/filevo_cli_rs`)
- [ ] **9.1 Rust Interactive Terminal Interface**:
  - Build a native Rust CLI interface binary (`filevo` / `report-cli`) with styled ANSI / Rich-like terminal output.
  - Implement bottom-docked status bar, prompt window, readline command history, and tab completion.
- [ ] **9.2 Rust-Python Backend Bridge**:
  - Connect the Rust frontend seamlessly to the Python document intelligence & RLCD engine for document generation, indexing, and training.
  - Handle streaming output, animated spinners, and error propagation cleanly.
