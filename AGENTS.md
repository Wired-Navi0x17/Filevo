# AGENTS.md: Filevo

This repository = **Filevo**, an interactive conversational terminal application and document intelligence engine for scanning, indexing, and generating calibrated Microsoft Word (`.docx`) documents using Reinforcement Learning from Calibrated Decisions (RLCD).

---

## Quickstart

| Action | Command |
|---|---|
| Launch Interactive CLI | `report` |
| Direct DOCX Generation | `report create "Technical report on Microservices"` |
| Incremental DOCX Indexing | `report index /path/to/docs` |
| Check Model & Status | `report status` or `report model` |
| Live Policy Training | `report train live 10` or `report-train 10` |
| Run Test Suite | `python3 tests/test_filevo.py` |

---

## Architecture & Components

- **Entry point**: `src/doc_gen/filevo_cli.py:main()` — also globally symlinked to `~/.local/bin/report`
- **Conversational CLI**: `filevo_cli.py` — OpenCode-style interactive terminal REPL, readline history, tab-completion, word-boundary greeting matching, and unified intent dispatcher
- **`@file` Attachment Resolver**: `filevo_cli.py:resolve_file_mentions()` — parses `@filepath` mentions, extracts structural outlines from `.docx` and content from code/text files, and injects context into chat
- **Persistent Knowledge Base**: `src/doc_gen/knowledge_base.py` — native OpenXML reader, SHA-256 hash skip cache, style and structural archetype clustering (`~/.filevo/knowledge/document_index.json`)
- **RLCD Decision Engine**: `src/doc_gen/rlcd_engine.py` — dual-perspective consensus scoring (structural vs policy), Jensen-Shannon Divergence ($\text{JSD}$), normalized Shannon entropy ($H_{\text{norm}}$), calibrated risk gates, and REINFORCE policy gradients (`~/.filevo/policy/rlcd_policy.json`)
- **Dedicated OpenXML DOCX Renderer**: `src/doc_gen/docx_renderer.py` — constructs validated Microsoft Word packages with zero C-dependencies using standard library `zipfile` and `xml.etree.ElementTree`
- **Probabilistic Model**: `src/doc_gen/rl_model.py` — REINFORCE policy gradient engine with Jev primitives (`Choice`, `Score`, `Noul`)
- **Codebase Analyzer**: `src/doc_gen/codebase_analyzer.py` — AST parser extracting functions, classes, async definitions, complexity, and structural patterns

---

## Critical Conventions & Quirks

- **Zero C-Dependencies**: Uses strictly Python standard libraries for ZIP and XML parsing to guarantee 100% portability on Linux and NixOS without shared library issues.
- **Unified Command & Intent Routing**: Commands (`/create`, `/index`, `/train`, `/feedback`, etc.) and natural language phrases (`"create a docx..."`, `"index docs..."`) share identical underlying handlers.
- **No PRD Functionality**: `/prd` is permanently excised. Calling `/prd` returns unknown command.
- **Incremental Indexing**: Uses SHA-256 file hashing. Unchanged documents are never re-parsed.
- **Launchers**:
  - `~/.local/bin/report`: Main CLI wrapper.
  - `~/.local/bin/report-train`: Companion terminal live training streamer.