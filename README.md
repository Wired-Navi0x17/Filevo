# Filevo

```
  ███████╗██╗██╗     ███████╗██╗   ██╗ ██████╗
  ██╔════╝██║██║     ██╔════╝██║   ██║██╔═══██╗
  █████╗  ██║██║     █████╗  ██║   ██║██║   ██║
  ██╔══╝  ██║██║     ██╔══╝  ╚██╗ ██╔╝██║   ██║
  ██║     ██║███████╗███████╗ ╚████╔╝ ╚██████╔╝
  ╚═╝     ╚═╝╚══════╝╚══════╝  ╚═══╝   ╚═════╝
```

> **Conversational Document Intelligence & RLCD Generation Engine**  
> Reinforcement Learning from Calibrated Decisions · Native OpenXML DOCX Synthesis · Persistent Knowledge Base · Zero External C-Dependencies

---

## Overview

**Filevo** is an interactive, conversational terminal application and document intelligence engine designed to learn structural and stylistic patterns from user-supplied Microsoft Word (`.docx`) files and generate calibrated documents via **Reinforcement Learning from Calibrated Decisions (RLCD)**.

Built entirely on Python standard libraries (`zipfile`, `xml.etree.ElementTree`, `ast`, `math`, `readline`), Filevo requires **zero external C-extension dependencies** and runs reliably across all Linux distributions, including NixOS.

---

## Key Capabilities

* **Conversational Terminal Chat**: Responds naturally to questions and queries, with built-in readline history and tab completion.
* **Unified Intent Routing**: Natural language requests (`"create a docx on AI"`, `"train policy on my docs"`, `"show status"`) invoke the exact same underlying logic as explicit slash commands (`/create`, `/train`, `/status`).
* **`@file` Attachment Mentions**: Reference any file in your queries using `@path/to/file` (e.g. `@report.docx what is in this document?`). Filevo extracts the outline, headings, and metrics to ground the conversation.
* **Persistent Document Knowledge Base**: Incrementally hashes files using SHA-256. Unchanged documents are skipped instantly without reprocessing.
* **Generalization without Overfitting**: Learns document archetypes, section progressions, heading hierarchies, and typography conventions rather than memorizing literal text.
* **RLCD Calibrated Decision Model**: Dual-perspective consensus scoring (structural prior vs. learned policy), Jensen-Shannon Divergence ($\text{JSD}$), normalized Shannon entropy ($H_{\text{norm}}$), and calibrated risk gates.
* **Dedicated OpenXML DOCX Renderer & Validator**: Directly generates styled, professional `.docx` files with custom typography, accent palettes, margins, tables, and callouts, validating the ZIP and XML tree post-generation.
* **Companion Live Training**: Run live policy training streams side-by-side in a separate terminal window via `report-train 10`.

---

## Quickstart

### Launch the Conversational CLI
Simply type `report` from anywhere in your terminal:
```bash
report
```

### Direct Execution Examples
```bash
# Create a validated DOCX via RLCD
report create "Technical report on Cloud Architecture"

# Index sample DOCX documents into the persistent knowledge base
report index /path/to/documents

# Inspect system and index status
report status

# View calibrated policy distribution
report model

# Record feedback on the last generation
report feedback +1.0

# Stream live policy training across 10 episodes in a separate window
report-train 10
```

---

## Command Reference

| Command | Natural Language Equivalent | Description |
|---|---|---|
| `/help` | `"help"`, `"what can you do?"` | Displays available commands and usage guide |
| `/create <topic>` | `"create a docx on <topic>"` | Synthesizes a calibrated DOCX file via RLCD |
| `/analyze <path>` | `"analyze <path>"`, `"inspect <path>"` | Inspects a document or codebase structure |
| `/train [@file\|dir\|live]` | `"train on @doc.docx"`, `"train live 10"` | Unified 3-in-1 pipeline: ingests documents, compiles supervision datasets & adapts policy gradients |
| `/feedback <score>` | `"feedback +1.0"`, `"rate -0.5"` | Records human feedback on the last generation |
| `/model` | `"model"`, `"show weights"` | Reports calibrated policy probabilities and typography preferences |
| `/status` | `"status"`, `"system status"` | Reports indexed document counts and RLCD metrics |
| `/clear` | `"clear"`, `"cls"` | Clears terminal screen and redraws the Filevo header |
| `/exit` | `"exit"`, `"quit"`, `"bye"` | Exits the application |

---

## Architecture

```mermaid
flowchart TD
    subgraph CLI ["Conversational Terminal CLI ('report')"]
        UserInput[User Input / Command] --> InputRouter{Input Router}
        InputRouter -->|Starts with /| SlashHandler[Slash Command Handler]
        InputRouter -->|Natural Language| IntentClassifier[Intent Classifier]
        InputRouter -->|Contains @file| FileResolver[@file Attachment Resolver]
        FileResolver --> ChatContext[Augmented Context]
        IntentClassifier --> UnifiedExec[Unified Action Dispatcher]
        SlashHandler --> UnifiedExec
    end

    subgraph Knowledge ["Persistent Knowledge Base (~/.filevo/knowledge/)"]
        IndexCmd[/train or NL 'train on docs'] --> DocxParser[OpenXML Feature Extractor]
        DocxParser --> CacheCheck{SHA-256 Changed?}
        CacheCheck -->|No| Skip[Skip Unchanged File]
        CacheCheck -->|Yes| FeatureExtractor[Extract Style & Structure]
        FeatureExtractor --> MetaStore[(Persistent Metadata Store)]
    end

    subgraph RLCD ["RLCD Decision Model"]
        UnifiedExec -->|Create / Analyze Request| RLCDRouter[RLCD Calibrated Decision Router]
        RLCDRouter --> MetaStore
        RLCDRouter --> DualPerspective[Dual-Perspective Scoring: Structural + Policy]
        DualPerspective --> ConfidenceGate{Calibrated Risk Gate}
        ConfidenceGate -->|Confident| ApplyStrategy[Select Archetype & Formatting]
        ConfidenceGate -->|Ambiguous| RequestReview[Flag for Review]
        FeedbackCmd[/feedback] --> PolicyStore[Contextual Policy Gradient Update]
        PolicyStore --> RLCDRouter
    end

    subgraph Renderer ["Dedicated OpenXML DOCX Renderer"]
        ApplyStrategy --> ContentSynthesizer[Grounded Content Generator]
        ContentSynthesizer --> DocxRenderer[OpenXML DOCX Builder]
        DocxRenderer --> Validator[Zip & XML Validator]
        Validator --> OutputDocx[(Generated .docx Output)]
    end
```

---

## Project Structure

```
.
├── src/
│   └── doc_gen/
│       ├── __init__.py           # Package initialization
│       ├── filevo_cli.py         # Conversational REPL, @file resolver, command router
│       ├── rlcd_engine.py        # RLCD calibrated decision model & policy store
│       ├── knowledge_base.py     # Persistent document knowledge & SHA-256 caching
│       ├── docx_renderer.py      # Dedicated OpenXML DOCX renderer & XML validator
│       ├── rl_model.py           # REINFORCE policy gradient & Jev primitives
│       ├── codebase_analyzer.py  # AST parser for codebases, classes, and complexity
│       ├── document_generator.py # AST-grounded report synthesizer
│       ├── cli.py                # Backward-compatibility bridge
│       └── test_filevo.py        # Verification test suite
├── tests/
│   └── test_filevo.py            # Automated test suite
├── AGENTS.md                     # Agent specifications & architecture guidelines
├── FILEVO_SUMMARY.md             # Per-file technical summary for downstream AI models
├── pyproject.toml                # Project metadata & launcher entrypoint
└── README.md                     # This documentation
```

---

## Persistent State Layout

All persistent files are saved in `~/.filevo/`:
* `~/.filevo/knowledge/document_index.json`: Cached document metadata, structural profiles, and SHA-256 hashes.
* `~/.filevo/policy/rlcd_policy.json`: Calibrated archetype biases, font preferences, baseline returns, and last active decision.
* `~/.filevo/model.json`: Probabilistic model weights and trajectory state.
* `~/.filevo/history`: Readline command history for the interactive CLI.
* `~/.filevo/output/`: Directory where generated `.docx` and `.md` files are stored.

---

## Testing

Run the automated verification suite:
```bash
python3 tests/test_filevo.py
```
Outputs:
```
✓ test_no_prd_command passed
✓ test_docx_renderer_and_validation passed
✓ test_knowledge_base_incremental_indexing passed
✓ test_rlcd_decision_engine passed
✓ test_file_mention_resolver passed

All 5 comprehensive verification tests passed successfully!
```

```
CIE
├─ .python-version
├─ AGENTS.md
├─ FILEVO_SUMMARY.md
├─ LICENSE
├─ README.md
├─ TODO.md
├─ pyproject.toml
├─ src
│  ├─ doc_gen
│  │  ├─ __init__.py
│  │  ├─ cli.py
│  │  ├─ codebase_analyzer.py
│  │  ├─ conversation_memory.py
│  │  ├─ dataset_builder.py
│  │  ├─ document_generator.py
│  │  ├─ docx_renderer.py
│  │  ├─ filevo_cli.py
│  │  ├─ knowledge_base.py
│  │  ├─ llm_client.py
│  │  ├─ rich_ui.py
│  │  ├─ rl_model.py
│  │  ├─ rlcd_engine.py
│  │  ├─ test_filevo.py
│  │  └─ web_researcher.py
│  └─ filevo_cli_rs
│     ├─ Cargo.lock
│     ├─ Cargo.toml
│     └─ src
│        └─ main.rs
├─ tests
│  └─ test_filevo.py
└─ uv.lock

```