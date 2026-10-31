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
> Reinforcement Learning from Calibrated Decisions · WordCraft MCP Live Composition · Native OpenXML DOCX Fallback · Anti-Slop Discipline · Zero External C-Dependencies

---

## Overview

**Filevo** is an interactive, conversational terminal application and document intelligence engine. It extracts structural, stylistic, and taxonomic patterns from Microsoft Word (`.docx`) documents to train a policy via **Reinforcement Learning from Calibrated Decisions (RLCD)** and synthesizes calibrated documents.

### Highlights
- **WordCraft MCP Integration**: Live, visible desktop composition in ArtCraft WordCraft (`127.0.0.1:7981`) or headless background generation. Documents open automatically in WordCraft upon completion.
- **Dedicated OpenXML Fallback**: High-performance, zero C-dependency pure-Python DOCX renderer and element validator.
- **Anti-Slop Discipline**: Strict BLUF (Bottom Line Up Front), Times New Roman typography, substantive multi-paragraph synthesis, and elimination of generic AI cliches.
- **Calibrated Page Budgeting**: Exact page targeting (e.g. 250 pages = exactly 250 pages) with automatic overflow prevention.
- **Opt-In PDF Export**: Produces clean `.docx` by default. Companion `.pdf` export occurs strictly when requested via `--pdf`.
- **Zero C-Dependencies**: Core fallback runs on standard Python libraries (`zipfile`, `xml.etree.ElementTree`, `math`, `readline`) for 100% portability on Linux and NixOS.

---

## Quickstart

### 1. Launch the Interactive CLI
Launch Filevo directly from anywhere:
```bash
report
```
*(Or invoke directly with `python3 src/doc_gen/filevo_cli.py`)*

### 2. Generate a Document
Generate reports directly from CLI arguments or interactively in chat:

```bash
# Standard report (DOCX only, default Times New Roman)
report create "Technical Report on Microservices Architecture"

# Watch live document construction in the WordCraft desktop GUI
report create --live "Autonomous Robotics Sensor Fusion"

# Generate an exact multi-page monograph (e.g. 250 pages)
report create "250-page monograph on wild plants"

# Opt-in PDF export alongside DOCX
report create --pdf "Quarterly Financial Analysis"
```

### 3. Ingest Documents & Train Policy
Filevo uses a unified 3-in-1 pipeline (Ingestion -> Dataset Compilation -> RLCD Policy Gradient Adaptation):

```bash
# Train policy on a single document mention
report train @sample.docx

# Train policy on an entire folder of reference documents
report train /path/to/reference_documents/

# Stream live policy training episodes in a companion terminal
report-train 10
```

### 4. Provide Feedback & Calibrate Policy
Steer the RLCD policy weights based on generated document quality:
```bash
report feedback +1.0   # Reward structural alignment
report feedback -0.5   # Penalize formatting or outline drift
```

---

## Command Reference

| Command | Natural Language Equivalent | Description |
|---|---|---|
| `/create <topic> [--live] [--pdf]` | `"create a docx on <topic>"` | Synthesizes a calibrated document. Add `--live` for GUI mode, `--pdf` for PDF export |
| `/train [@file\|dir\|live N]` | `"train on @doc.docx"`, `"train live 10"` | Ingests `.docx` files and updates the RLCD policy gradients |
| `/settings mode [desktop\|headless]` | `"switch mode to desktop"` | Toggles WordCraft visible desktop application or headless server |
| `/settings engine [wordcraft\|native]` | `"switch engine to native"` | Sets primary composition engine (WordCraft MCP or pure OpenXML) |
| `/settings auto_open [on\|off]` | `"enable auto open"` | Toggles opening documents in WordCraft upon creation |
| `/analyze <path>` | `"analyze <path>"`, `"inspect <path>"` | Inspects document structure, outline, or codebase AST |
| `/feedback <score>` | `"feedback +1.0"`, `"rate -0.5"` | Records human feedback to tune policy weights |
| `/status` | `"status"`, `"system status"` | Reports indexed document counts, RLCD metrics, and engine status |
| `/status wordcraft` | `"wordcraft status"` | Displays WordCraft MCP server connection and process state |
| `/model` | `"model"`, `"show weights"` | Displays RLCD policy probabilities and typography configuration |
| `/clear` | `"clear"`, `"cls"` | Clears the terminal screen |
| `/exit` | `"exit"`, `"quit"`, `"bye"` | Exits Filevo |

---

## WordCraft MCP Live Composition

Filevo connects to ArtCraft's WordCraft engine via MCP (`wordcraft-cli mcp`):

1. **Desktop GUI Mode (`mode = "desktop"`)**:
   - Automatically connects to or launches WordCraft (`~/.local/bin/wordcraft --control 7981`).
   - Displays real-time typing, styling, tables, and page-layout operations live on your desktop.
   - Automatically opens generated `.docx` files in WordCraft when finished.
2. **Headless Mode (`mode = "headless"`)**:
   - Executes WordCraft MCP commands silently in the background for batch processing.
3. **Pure OpenXML Fallback**:
   - If WordCraft is unavailable or disabled via `/settings engine native`, Filevo falls back to its built-in native OpenXML engine.

---

## Anti-Slop Document Policy

Every generated document adheres to strict editorial and formatting rules:
- **BLUF (Bottom Line Up Front)**: First sentence of every section conveys core thesis and direct findings.
- **Prose-First**: Avoids bullet-point soup; uses substantive paragraphs unless describing strict procedural steps.
- **No AI Cliches**: Filters out generic tropes (`"Furthermore"`, `"Moreover"`, `"In today's fast-paced world"`, `"Leverage"`, `"Seamless"`).
- **Substantive Depth**: Guarantees technical depth, hardware specifications, taxonomic classifications, and domain metrics without filler.
- **Calibrated Page Budgeting**: Automatically calculates target section lengths and suppresses unrequested tables of contents on large volumes to deliver exact requested page counts.
- **Typography Source of Truth**: Standardized on Times New Roman (Display and Body) with high-contrast monochrome and crisp accent palettes.

---

## Project Structure

```
.
├── src/
│   ├── doc_gen/
│   │   ├── filevo_cli.py         # Terminal REPL, intent router, and @file resolver
│   │   ├── wordcraft_engine.py   # WordCraft MCP client & live GUI bridge
│   │   ├── wordcraft_adapter.py  # High-level WordCraft RPC adapter & tool caller
│   │   ├── antislop_policy.py    # BLUF, typography, and anti-cliche prose filter
│   │   ├── document_brief.py     # Hierarchical section planning & page budgeting
│   │   ├── document_ir.py        # Intermediate representation for documents
│   │   ├── docx_renderer.py      # Native OpenXML builder & package validator
│   │   ├── rlcd_engine.py        # Dual-perspective RLCD model & risk gates
│   │   ├── knowledge_base.py     # Native OpenXML reader & SHA-256 caching
│   │   ├── llm_client.py         # Local model inference & analytical synthesizer
│   │   ├── model_trainer.py      # Supervision dataset compilation & training
│   │   ├── rl_model.py           # REINFORCE policy gradients & Jev primitives
│   │   ├── codebase_analyzer.py  # AST parser for codebases
│   │   └── rich_ui.py            # Terminal styling, banners, and layout tables
│   └── filevo_cli_rs/            # High-performance companion Rust TUI
│       ├── Cargo.toml
│       └── src/
├── tests/
│   └── test_filevo.py            # Comprehensive 36-test automated verification suite
├── AGENTS.md                     # Agent specifications & architecture guidelines
├── DOC.md                        # Anti-slop document design source of truth
└── pyproject.toml                # Project metadata & console scripts
```

---

## Persistent State Layout

Configuration and persistent state are stored in standard user directories:
- `~/.config/filevo/wordcraft.toml`: WordCraft MCP and Anti-Slop typography settings.
- `~/.filevo/config.json`: Filevo preferences (active engine, mode, auto-open).
- `~/.filevo/knowledge/document_index.json`: Cached document outlines, styles, and SHA-256 signatures.
- `~/.filevo/policy/rlcd_policy.json`: Calibrated archetype biases and REINFORCE weights.
- `~/.filevo/output/`: Default target directory for generated `.docx` documents.
- `~/.filevo/history`: Interactive terminal command history.

---

## Testing

Run the Python verification test suite (all 36 tests pass):
```bash
python3 tests/test_filevo.py
```

Run the companion Rust TUI test suite (all 51 tests pass):
```bash
nix-shell -p cargo rustc --run "cargo test --manifest-path src/filevo_cli_rs/Cargo.toml"
```