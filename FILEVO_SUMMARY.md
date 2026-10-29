# Filevo Codebase: Per-File Technical Summary & Architecture Guide

> **Target Audience**: AI Agents, LLMs, and System Engineers continuing work on Filevo.  
> **Repository Location**: `/home/l41n-pr0t0/.opencode/plan/src/doc_gen/`  
> **Global Launchers**: `~/.local/bin/report`, `~/.local/bin/report-train`  
> **Persistent State Root**: `~/.filevo/`

---

## 1. System Overview

**Filevo** is an interactive, conversational terminal application and document intelligence engine for scanning, indexing, and generating calibrated Microsoft Word (`.docx`) documents.

### Key Architectural Pillars:
1. **Zero External C-Dependencies**: Built entirely using Python standard libraries (`zipfile`, `xml.etree.ElementTree`, `ast`, `hashlib`, `math`, `readline`). 100% portable on NixOS and Linux without shared library issues.
2. **Conversational Chatbot with Unified Intent Dispatch**: Users can run explicit slash commands (`/create`, `/index`, `/train`, etc.) or chat naturally (`"create a docx about..."`, `"what is this document?"`). Both invoke identical underlying logic.
3. **`@file` Attachment Mentions**: Supports referencing any file path via `@path` in the chat input. Files are read, parsed (extracting structure for `.docx`), and injected into conversational context.
4. **Persistent Knowledge Base**: Incremental hashing via SHA-256 so unchanged documents are never re-parsed. Learns structural and typography archetypes without overfitting to verbatim text.
5. **RLCD Calibrated Decision Model**: Reinforcement Learning from Calibrated Decisions. Evaluates prompt and corpus context using dual-perspective consensus scoring (structural prior vs. learned policy), normalized Shannon entropy ($H_{\text{norm}}$), Jensen-Shannon Divergence ($\text{JSD}$), and risk gating before generating.
6. **Dedicated OpenXML DOCX Renderer & Validator**: Directly writes styled OpenXML XML packages and validates ZIP and XML tree integrity.
7. **No PRD Functionality**: All legacy `/prd` commands, parsers, and special cases have been removed.

---

## 2. Per-File Detailed Summary

### 2.1. `__init__.py`
* **Path**: `src/doc_gen/__init__.py`
* **Role**: Package marker and metadata.
* **Exports**: Package docstring and `__version__ = "1.0.0"`.

---

### 2.2. `filevo_cli.py` (CLI & Conversational Controller)
* **Path**: `src/doc_gen/filevo_cli.py`
* **Size / Lines**: ~710 lines
* **Role**: Primary entry point for interactive and one-shot execution. Handles terminal UI, readline completion, chat handling, intent classification, and command dispatching.
* **Key Components**:
  * `FILEVO_LOGO` & `WELCOME_MSG`: ASCII branding for the terminal interface.
  * `COMMANDS`: Registry mapping slash commands to human descriptions (`/help`, `/create`, `/analyze`, `/index`, `/train`, `/feedback`, `/model`, `/status`, `/clear`, `/exit`). **`/prd` is strictly omitted.**
  * `resolve_file_mentions(text)`: Regex scanner matching `@([a-zA-Z0-9_\-\.\/\~]+)`. Reads and extracts text or DOCX structural summaries.
  * `handle_chat_and_intents(user_input)`: Natural language understanding router:
    * Routes phrases starting with `"create"`, `"generate"`, `"make a doc"` to `cmd_create`.
    * Routes phrases starting with `"analyze"`, `"inspect"` to `cmd_analyze`.
    * Routes phrases starting with `"index"`, `"scan"` to `cmd_index`.
    * Routes phrases starting with `"train"` to `cmd_train`.
    * Routes phrases starting with `"feedback"`, `"score"` to `cmd_feedback`.
    * Answers conversational queries (`"hello"`, `"hi"`) using word-boundary matching.
    * Prioritizes answering questions about referenced `@file` attachments.
  * `handle_input(user_input)`: Dispatches leading slash commands to dedicated handlers or routes to `handle_chat_and_intents`.
  * `cmd_create(request_str, attachments)`: Triggers RLCD decision engine, retrieves knowledge profile, synthesizes grounded sections, invokes `DocxRenderer`, and validates output.
  * `cmd_index(path_arg)`: Calls `DocumentKnowledgeBase.index_directory` and triggers self-adaptation on `RLCDDecisionEngine`.
  * `cmd_train(arg)`: Supports corpus self-adaptation, direct reward updates, and live streaming via `_run_live_training_stream(n_episodes)`.
  * `cmd_feedback(reward_str)`: Applies policy gradient feedback to the active or recent generation decision.
  * `cmd_model()` & `cmd_status()`: Outputs ASCII distribution bars and knowledge base statistics.
  * `interactive_loop()`: Readline-enabled terminal REPL with tab-completion and history persistence (`~/.filevo/history`).
  * `main()`: `argparse` wrapper supporting direct CLI subcommands (`report create`, `report train`, `report status`, etc.).

---

### 2.3. `rlcd_engine.py` (RLCD Calibrated Decision Engine)
* **Path**: `src/doc_gen/rlcd_engine.py`
* **Size / Lines**: ~365 lines
* **Role**: Calibrated decision-making system. Decides document archetype, section structure, and typography while evaluating confidence and risk.
* **Mathematical Foundations**:
  * **Dual-Perspective Scoring**:
    1. Lexical / Structural Prior: $P_{\text{struct}} = \text{Softmax}(S_{\text{lex}} / T_{\text{struct}})$
    2. Learned Policy Prior: $P_{\text{policy}} = \text{Softmax}((\theta_{\text{arch}} + 1.0) / T_{\text{policy}})$
    3. Consensus Ensemble: $P_{\text{ens}} = 0.5 \cdot (P_{\text{struct}} + P_{\text{policy}})$
  * **Disagreement & Agreement**:
    * Jensen-Shannon Divergence: $\text{JSD}(P_{\text{struct}} \parallel P_{\text{policy}}) \in [0, 1]$
    * Agreement: $1 - \text{JSD}$
  * **Normalized Shannon Entropy**:
    $$H_{\text{norm}}(P) = -\frac{\sum_{i} P_i \log_2 P_i}{\log_2 K} \in [0, 1]$$
  * **Calibrated Risk Gate**:
    Decision is `CONFIDENT` if $\text{Confidence} \ge 0.50 \land \text{Agreement} \ge 0.65 \land H_{\text{norm}} \le 0.85$. Otherwise marked `AMBIGUOUS` (requiring human review).
  * **Policy Gradient Update**:
    $$\theta \leftarrow \theta + \alpha \cdot (R - b) \cdot \nabla_\theta \log \pi_\theta(a)$$
    * Exponential moving average baseline: $b \leftarrow 0.9 b + 0.1 R$.
    * Positive rewards reinforce chosen archetype and formatting; corrections penalize the incorrect prediction and boost the user's ground-truth choice.
* **Key Classes**:
  * `FormattingStrategy`: Dataclass holding font family, accent color, margins, line spacing, table toggle, callout toggle, and alignment.
  * `RLCDDecision`: Dataclass containing selected archetype, confidence, agreement, disagreement, entropy, gate status, formatting strategy, recommended sections, and rationale.
  * `RLCDDecisionEngine`: Encapsulates weights, mathematical primitives, `decide()`, `record_feedback()`, `train_on_knowledge_corpus()`, and persistence to `~/.filevo/policy/rlcd_policy.json`.

---

### 2.4. `knowledge_base.py` (Persistent Document Knowledge)
* **Path**: `src/doc_gen/knowledge_base.py`
* **Size / Lines**: ~330 lines
* **Role**: Extracts, indexes, and caches structural and stylistic supervision from user-supplied DOCX files incrementally.
* **Key Features**:
  * **Incremental SHA-256 Caching**: Reads file bytes and computes hash. If hash matches existing record in `document_index.json`, skips processing entirely.
  * **OpenXML Native Extraction**:
    * Reads `docProps/core.xml` for title and creator.
    * Reads `word/styles.xml` for font families (`w:rFonts`).
    * Reads `word/document.xml` for paragraph count, word count, heading styles (`w:pStyle`), visual headings, table count, and bullet frequencies.
  * **Generalization without Overfitting**: Extracts heading progressions (e.g., $H_1 \to H_2 \to H_2$), average paragraph length, and abstract section topics. Filters out document-specific names, entities, and literal numbers.
  * **Archetype Clustering**: Clusters documents into:
    * `Technical Report`
    * `Academic Monograph`
    * `Project Proposal`
    * `Executive Summary`
* **Key Classes**:
  * `StyleProfile`: Dataclass for font, sizes, spacing, accent color, margins.
  * `StructuralProfile`: Dataclass for archetype, word count, heading hierarchy, section topics, table counts.
  * `DocumentMetadata`: Container for file path, hash, timestamp, title, author, style, and structure.
  * `DocumentKnowledgeBase`: Manages `index_directory()`, `index_file_if_changed()`, `get_archetype_profile()`, `save()`, `load()`, and stores state in `~/.filevo/knowledge/document_index.json`.

---

### 2.5. `docx_renderer.py` (Dedicated OpenXML Renderer & Validator)
* **Path**: `src/doc_gen/docx_renderer.py`
* **Size / Lines**: ~280 lines
* **Role**: Generates fully-formed, valid `.docx` OpenXML ZIP archives from scratch with zero external libraries.
* **Key Features**:
  * Constructs complete OpenXML directory tree in-memory and compresses with `zipfile.ZIP_DEFLATED`:
    1. `[Content_Types].xml`: Registers MIME types for document and styles.
    2. `_rels/.rels`: Establishes package relationship to `word/document.xml`.
    3. `word/_rels/document.xml.rels`: Links `document.xml` to `styles.xml`.
    4. `word/styles.xml`: Configures default font family, Heading 1, Heading 2, Title, and paragraph spacing.
    5. `word/document.xml`: Builds paragraphs, headings, bullet lists, callout highlight boxes, tables with accent headers, and margin geometry (`w:pgMar`).
  * `validate(docx_path)`: Post-generation health check verifying file size $> 0$, presence of mandatory OpenXML components, and valid XML syntax via `xml.etree.ElementTree`.
* **Key Classes**:
  * `DocxRenderer`: Provides `render()` and `validate()`.

---

### 2.6. `rl_model.py` (REINFORCE Policy Gradient & Jev Primitives)
* **Path**: `src/doc_gen/rl_model.py`
* **Size / Lines**: ~310 lines
* **Role**: REINFORCE policy gradient engine for structural decisions using TypeSafe Jev-style decision primitives.
* **Decision Primitives**:
  * `Choice` (`softmax`): Categorical distribution over discrete mutually-exclusive choices.
  * `Score` (`score`): Ordinal ranking with calibrated confidence.
  * `Noul` (`sigmoid`): Boolean gating probability for feature inclusion.
* **Bug Fix Note**: Corrects previous inverted sign bug where negative rewards caused positive weight shifts. Now uses true analytical gradient $\nabla_\theta \log \pi$ multiplied by $(R - b)$.
* **State Persistence**: Serializes weights, baseline, episode count, and last trajectory to `~/.filevo/model.json`.

---

### 2.7. `codebase_analyzer.py` (AST Codebase Examiner)
* **Path**: `src/doc_gen/codebase_analyzer.py`
* **Size / Lines**: ~235 lines
* **Role**: Traverses Python codebases, extracts functions, classes, methods, imports, patterns, and computes cyclomatic complexity.
* **Bug Fixes & Capabilities**:
  * Uses `node.body` for `ast.ClassDef` methods (fixing crash on `node.methods`).
  * Handles both `ast.FunctionDef` and `ast.AsyncFunctionDef`.
  * Excludes virtual environment and cache folders (`.venv`, `.git`, `node_modules`, `__pycache__`).
  * Populates `self.complexity` per function ($CC = E - N + 2P$).
  * Populates `self.patterns` (context managers, inheritance, decorated functions, test classes).
  * Returns normalized 8-dimensional state vector for model consumption.

---

### 2.8. `document_generator.py` (Markdown & Code Synthesis Pipeline)
* **Path**: `src/doc_gen/document_generator.py`
* **Size / Lines**: ~450 lines
* **Role**: Connects `CodebaseAnalyzer` and `RLProbabilisticModel` to generate detailed codebase markdown reports.
* **Design**:
  * Replaced previous 86% random coin-flip drop rate with deterministic ranking from softmax distribution.
  * Grounds introduction, architecture, methodology, and complexity in parsed AST metrics.
  * Records trajectory for reward credit assignment.
* **Key Classes**:
  * `DocumentGenerator`: Generates reports and metadata.
  * `DocumentTrainer`: Connects reward signals to trajectories.

---

### 2.9. `cli.py` (Backward-Compatibility Bridge)
* **Path**: `src/doc_gen/cli.py`
* **Role**: Forwards legacy invocations of `python src/doc_gen/cli.py` directly to `filevo_cli.main()`.

---

### 2.10. `test_filevo.py` (Verification Test Suite)
* **Path**: `src/doc_gen/test_filevo.py`
* **Role**: Comprehensive regression and unit test suite.
* **Tests**:
  1. `test_no_prd_command`: Asserts `/prd` is absent from `COMMANDS`.
  2. `test_docx_renderer_and_validation`: Tests OpenXML generation and XML validation.
  3. `test_knowledge_base_incremental_indexing`: Tests SHA-256 skip caching.
  4. `test_rlcd_decision_engine`: Tests consensus scoring, risk gating, and feedback gradients.
  5. `test_file_mention_resolver`: Tests `@file` extraction and parsing.

---

## 3. Persistent Data Files & Directory Layout

```
~/.filevo/
├── history                       # Terminal readline command history
├── model.json                    # RLProbabilisticModel weights, baseline, trajectory
├── knowledge/
│   └── document_index.json       # SHA-256 hashes, style & structural profiles, archetype clusters
├── policy/
│   └── rlcd_policy.json          # RLCDDecisionEngine biases, baseline, last_decision
└── output/                       # Generated .docx and .md documents
    ├── Technical_Report_On_Cloud_Architect.docx
    └── ...
```

---

## 4. Global Launchers

* **`~/.local/bin/report`**:
  ```bash
  #!/usr/bin/env bash
  exec python3 /home/l41n-pr0t0/.opencode/plan/src/doc_gen/filevo_cli.py "$@"
  ```
* **`~/.local/bin/report-train`**:
  ```bash
  #!/usr/bin/env bash
  exec python3 /home/l41n-pr0t0/.opencode/plan/src/doc_gen/filevo_cli.py train live "${1:-10}"
  ```

---

## 5. Verification Commands

Run the test suite:
```bash
python3 /home/l41n-pr0t0/.opencode/plan/src/doc_gen/test_filevo.py
```

Launch the conversational CLI:
```bash
report
```

Train policy live across 10 episodes in a companion window:
```bash
report-train 10
```
