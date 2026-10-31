# DOC.md — Document Design Specification

## Document Overview
- **Title**: Dual First-Order Optimization in Document Intelligence: Mathematical Foundations, Algorithmic Analysis, and Empirical Benchmarking of Gradient Descent and Gradient Ascent in Filevo
- **Target Audience**: Academic faculty, machine learning researchers, and systems engineers evaluating CS2227 (Artificial Intelligence and Machine Learning) CIE-3.
- **Core Purpose**: Demonstrate rigorous mathematical formulation, computational complexity analysis, and production implementation of continuous first-order optimization (Gradient Descent and Gradient Ascent) within an autonomous document intelligence engine (Filevo).
- **Principal Finding (BLUF)**: First-order iterative optimization is computationally mandatory over closed-form normal equations due to O(d^3) matrix inversion complexity and rank-deficient ill-conditioning in high-dimensional feature spaces (d > 10,000). With L2 Tikhonov regularization, the empirical cross-entropy loss landscape is strictly convex (H > 0), guaranteeing unconditional global convergence for Gradient Descent. For autonomous decision routing, REINFORCE Policy Gradient Ascent with moving baseline variance reduction enables stable policy optimization over non-differentiable typographic feedback, achieving monotonic probability mass concentration.

---

## Design Dials
- **FORMALITY: 8 / 10** — Rigorous academic and engineering voice. Direct, declarative statements without colloquialisms or pompous academic inflation.
- **DENSITY: 7 / 10** — High information density. Complete mathematical derivations, vector diagrams, tabular comparative benchmarks, and production code snippets.
- **ORNAMENT: 2 / 10** — Minimalist editorial styling. Absolutely zero decorative clip art, zero harsh colored frames, and zero colored side borders.

---

## Editorial Typography & Visual System
- **Body Text**: Times New Roman, 12pt (sz=24), 1.15 line spacing (line=276), 6pt space after (after=120), color #111827.
- **Headings**:
  - Heading 1: Times New Roman Bold, 14pt (sz=28), 16pt before, 7pt after, uppercase styling.
  - Heading 2: Times New Roman Bold, 12.5pt (sz=25), 11pt before, 5pt after.
  - Heading 3: Times New Roman Bold, 12pt (sz=24), 8pt before, 4pt after.
- **Code Blocks**: Consolas, 9.5pt (sz=19), single line spacing (line=220), clean #F8FAFC background shading, 16pt left indent, NO vertical side borders.
- **Mathematical Equations**: Native Microsoft Word OpenXML Math (<m:oMath>), Times New Roman / Cambria Math typography, centered display equations with formal equation numbers (Eq. X.Y) right-aligned. NO enclosing side borders.
- **Tables**: Academic booktabs styling. Top border (12pt single #1E293B), header bottom border (8pt single #334155), table bottom border (12pt single #1E293B), light #F8FAFC alternating fills, zero vertical borders.
- **Callouts & Highlights**: Clean indented paragraph styling (16pt left indent, subtle italic body text, #F8FAFC shading), NO harsh colored or black left borders.

---

## Anti-Slop Writing Discipline (Strict Enforcement)
1. **Prose as Default**: Arguments, derivations, and discussions must flow in continuous, articulate paragraphs. Eliminate numbered bold lists that chop up continuous reasoning.
2. **Elimination of Bold-Bombing**: Bold text is strictly reserved for the first introduction of critical mathematical definitions. No repetitive bold labels (**1. Topic:**) across paragraphs.
3. **Ban on AI Filler & Connectors**: Strictly avoid "Furthermore", "Moreover", "In conclusion", "It is crucial to note", "delve", "leverage", "seamless", "elevate", and staged negative contrasts ("not only X, but Y").
4. **Permanent Removal of Viva Relics**: The appendix is titled APPENDIX: MATHEMATICAL DETAILS OF GRADIENT DESCENT AND ASCENT IN FILEVO. All examiner prompts, viva board labels, and oral examination references are banned.
5. **Directness (BLUF)**: Each section opens with its core finding or mathematical reality before proceeding to supporting derivations.
