# Sortwise

> **Calibrated Academic Document Router & Visual Storage Manager**  
> Physical Native Desktop Application (Linux X11/Wayland) · RLCD Calibrated Classification · Filelight Proportion Map · BCUninstaller Multi-Threaded Disk Scanner

[![Tests](https://img.shields.io/badge/tests-109%20passed-10b981.svg)](#test-suite)
[![Python](https://img.shields.io/badge/python-3.11+-3b82f6.svg)](pyproject.toml)
[![UI](https://img.shields.io/badge/ui-native%20desktop%20(customtkinter)-20242f.svg)](src/native_app.py)

---

## Overview

**Sortwise** is an intelligent, physical desktop application designed to discover, calibrate, classify, rename, and organize university course study materials (`.pdf`, `.docx`, `.pptx`).

Unlike web or browser-based tools, Sortwise runs as a **100% physical native desktop window** on Linux (Wayland / X11) using **CustomTkinter** and vector-rendered Tk canvas widgets. It features a matte graphite monochrome aesthetic with subtle functional tints, large anti-aliased typography scale ($15\text{pt}$ body, $20\text{--}24\text{pt}$ headers), high-resolution vector icons, an in-flight renamer, and an undo ledger.

### Key Capabilities

* **BCUninstaller-Style Multi-Threaded Disk Scanner**: High-throughput background disk traversal fanning out across worker threads. Intelligently skips system pseudo-filesystems (`/proc`, `/sys`, `/dev`, `/run`, `/nix/store`) and build/dependency caches (`.git`, `node_modules`, `.cache`, `.venv`).
* **Startup Target Wizard**: Choose at launch between:
  * **Mode A (Folder Scan)**: Target an intake directory (e.g. `~/Downloads` or course directory).
  * **Mode B (Deep System Scan)**: Traverses your User Home (`~/`) or Entire OS filesystem (`/`) for orphaned lecture slides, notes, and syllabus documents.
* **Live Streaming Progress & Cooperative Cancellation**: Real-time progress dialog displaying visited folders, inspected files, discovered documents, elapsed time, and a responsive cancel button.
* **RLCD Calibrated Decisions**: Dual-perspective classification (lexical tokens + dense SentenceTransformer `all-MiniLM-L6-v2` embeddings), Jensen-Shannon Divergence ($D_{\text{JS}} \le 0.25$), normalized Shannon entropy ($H_{\text{norm}} \le 0.55$), Expected Calibration Error (ECE) telemetry, and human-in-the-loop contextual bandit policy gradient optimization.
* **Curriculum Taxonomy (Semester 3)**: Tailored keyword profiles and embeddings for core computer science & mathematics subjects, explicitly including **CS2806 - Calculus**.
* **Filelight-Style Proportion Map**: Pastel-tinted proportion pill bars and folder shelf visualizing disk footprint and distribution.
* **In-Flight Document Inspector & Renaming**: Inspect recovered metadata, slide/page counts, and generated titles with 1-click routing.
* **Activity Ledger with Instant Undo**: Every file relocation is recorded in an atomic JSON ledger with 1-click rollback.

---

## Semester 3 Taxonomy

Sortwise includes rich subject profiles and syllabus keywords for Semester 3 university courses:

| Course Code | Subject Label | Syllabus Focus / Keywords |
| :--- | :--- | :--- |
| **CS2806** | **CS2806 - Calculus** | Limits, derivatives, integrals, Taylor series, multivariate calculus, gradient vectors, eigenvalues |
| **CS2227** | **CS2227 - AI and ML** | Supervised learning, classification, neural networks, loss functions, reinforcement learning, RLCD |
| **CS2000** | **CS2000 - Design and Analysis of Algorithms** | Asymptotic notation, divide-and-conquer, dynamic programming, Dijkstra, greedy algorithms, graph search |
| **CS2235** | **CS2235 - Data Science** | Pandas, exploratory data analysis, hypothesis testing, regression, data visualization, feature engineering |
| **CS2405** | **CS2405 - Cyber Security** | Cryptography, RSA, network defense, penetration testing, authentication, malware analysis |
| **CS2500** | **CS2500 - Cloud Computing and Big Data** | Distributed systems, AWS, Kubernetes, MapReduce, Hadoop, object storage, microservices |
| **CS2403** | **CS2403 - Computer Networks** | TCP/IP, OSI model, routing protocols, sockets, DNS, congestion control |
| **CS2404** | **CS2404 - Internet of Things** | Embedded sensors, MQTT, edge computing, microcontrollers, Raspberry Pi |

---

## RLCD Calibration & Reinforcement Architecture

```
                       ┌───────────────────────────────┐
                       │   Extracted Document (.pdf,   │
                       │     .docx, .pptx, .txt, .md)  │
                       └──────────────┬────────────────┘
                                      │
                 ┌────────────────────┴────────────────────┐
                 │                                         │
                 ▼                                         ▼
  ┌──────────────────────────────┐          ┌──────────────────────────────┐
  │      Lexical Classifier      │          │     Semantic Bi-Encoder      │
  │ Sublinear Length-Normalized  │          │   SentenceTransformer MiniLM │
  │ Keyword & N-Gram Frequencies │          │    Dense Cosine Similarity   │
  └──────────────┬───────────────┘          └──────────────┬───────────────┘
                 │                                         │
                 ▼                                         ▼
  ┌──────────────────────────────┐          ┌──────────────────────────────┐
  │  Tempered Softmax (P_lex)    │          │  Tempered Softmax (P_sem)    │
  │     Scale-Balanced Logits    │          │       Centered Logits        │
  └──────────────┬───────────────┘          └──────────────┬───────────────┘
                 │                                         │
                 └────────────────────┬────────────────────┘
                                      │
                                      ▼
                       ┌───────────────────────────────┐
                       │  Classifier Disagreement      │
                       │  Jensen-Shannon Divergence    │
                       │  D_JS(P_lex || P_sem)         │
                       │  Agreement = 1.0 - D_JS       │
                       └──────────────┬────────────────┘
                                      │
                                      ▼
                       ┌───────────────────────────────┐
                       │   Ensemble Posterior & Gates  │
                       │   P_ens = 0.5*(P_lex + P_sem) │
                       │   H_norm = H(P_ens)/log2(K)   │
                       └──────────────┬────────────────┘
                                      │
                     ┌────────────────┴────────────────┐
                     │                                 │
                     ▼                                 ▼
         ┌────────────────────────┐        ┌────────────────────────┐
         │ Confidence >= 0.70 AND │        │  Confidence < 0.70 OR  │
         │   Agreement >= 0.75    │        │    Agreement < 0.75    │
         │   H_norm <= 0.55       │        │     H_norm > 0.55      │
         └───────────┬────────────┘        └───────────┬────────────┘
                     │                                 │
                     ▼                                 ▼
             [CONFIDENT TIER]                   [REVIEW QUEUE]
           Auto-route to Subject             Held for User Inspection
            Archive Directory                       & Override
                     │                                 │
                     └────────────────┬────────────────┘
                                      │
                                      ▼
                       ┌───────────────────────────────┐
                       │ Human-in-the-Loop Feedback:   │
                       │ Contextual Policy Gradient    │
                       │   theta <- theta + a*grad*R   │
                       │ Non-Catastrophic Centroids    │
                       │ ECE & Brier Score Telemetry   │
                       └───────────────────────────────┘
```

---

## Installation

### Prerequisites

* Linux OS (Wayland or X11)
* Python 3.11+
* [`uv`](https://github.com/astral-sh/uv) (recommended fast package manager) or standard `pip`

### Step 1: Clone the Repository

```bash
git clone git@github.com:Wired-Navi0x17/Sortwise.git
cd Sortwise
```

### Step 2: Install Dependencies

With `uv`:
```bash
uv sync
```

Or using standard `pip`:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Step 3: Install Desktop Integration

Run the bundled desktop installer to generate the application icon, launcher script, and KDE/GNOME application menu entry (`sortwise.desktop`):

```bash
./install_desktop.sh
```

---

## Usage

### Launching the Application

You can launch Sortwise directly from your desktop application launcher (search **Sortwise**) or via terminal:

```bash
# Using installed launcher
sortwise

# Or via uv
uv run python src/native_app.py
```

### Command-Line Options

```
usage: sortwise [-h] [--config CONFIG] [--ledger LEDGER] [--watch WATCH]
                [--target TARGET] [--no-scan-wizard] [--version]

options:
  -h, --help        Show this help message and exit
  --config CONFIG   Path to config.json (default: ~/.config/sortwise/config.json)
  --ledger LEDGER   Path to history.json (default: ~/.local/share/sortwise/history.json)
  --watch WATCH     Override intake watch folder for this session
  --target TARGET   Override archive root for this session
  --no-scan-wizard  Bypass the startup scan target dialog
  --version         Print version and exit
```

---

## Bulk Crap Uninstaller Disk Scanner

Inspired by [Bulk Crap Uninstaller](https://github.com/BCUninstaller/Bulk-Crap-Uninstaller), Sortwise features high-speed filesystem scanning:

1. **Multi-Threaded Worker Queue**: Traverses directory trees with concurrent workers utilizing `os.scandir` without blocking the GUI.
2. **Virtual Filesystem Exclusion**: Automatically excludes `/proc`, `/sys`, `/dev`, `/run`, `/nix/store`, `/boot`, and `/lost+found`.
3. **Build & Package Cache Exclusion**: Bypasses `node_modules`, `.git`, `.venv`, `.cargo`, `__pycache__`, and `~/.cache`.
4. **Cooperative Cancellation**: Instantly halts traversal on user cancellation and displays all discovered items found up to that moment.
5. **Bulk Action Toolbar**: Select all confident items with one click and batch-route them to target folders while reviewing uncertain items individually.

---

## Test Suite

Sortwise maintains an extensive test suite covering document extraction, taxonomy matching, tempered softmax calibration, entropy gates, undo ledgers, disk scanning, and desktop application components.

Run all tests:

```bash
PYTHONPATH=. LD_LIBRARY_PATH="/run/current-system/sw/share/nix-ld/lib:$LD_LIBRARY_PATH" uv run pytest tests/
```

Results:
```
======================== 109 passed in ~36s ========================
```
