# Filevo Visual Identity & Web Architecture Source of Truth (DESIGN.md)

This specification defines the editorial, visual, and behavioral standards for Filevo's interactive presentation and documentation web interface. It enforces the anti-slop guidelines defined under `/antislop-web`.

---

## 1. Dials & Foundations

- **VARIANCE**: `7` (Controlled Asymmetry — bans centered heroes; enforces 50/50 split and structural telemetry ribbons).
- **MOTION**: `5` (Subtle Cinematic Choreography — CSS transforms and timeline transitions; strict `prefers-reduced-motion` compliance).
- **DENSITY**: `4` (Publication Editorial — generous whitespace, strict monospace for telemetry/hex codes/indices, relaxed body leading).

---

## 2. Palette (Zero Neon / Zero Pure Black)

| Color Name | Hex Code | Functional Role |
|---|---|---|
| Deep Space Off-Black | `#090D14` | Primary viewport background |
| Dark Surface Slate | `#111827` | Card, container, and inspector surface |
| Elevated Surface | `#1E293B` | Floating controls, active tabs, hover states |
| Border Slate | `#334155` | Structural dividers, grid borders, hairline rules |
| Muted Foreground Slate | `#94A3B8` | Secondary labels, captions, metadata |
| High-Contrast White | `#F8FAFC` | Primary headlines, emphatic metrics |
| Calibrated Teal (Accent) | `#0D9488` | Active telemetry, timeline cursor, pass badges |
| Warm Gold (Diagnostic) | `#D97706` | Warning gates, ambiguous states, cache notices |

*Color Bans*: No pure `#000000`. No AI purple/neon gradient overlays. No outer neon glows.

---

## 3. Typography

- **Display & Headings**: `Cabinet Grotesk`, sans-serif (Weights: 600, 700; tight letter-spacing `-0.03em`).
- **Body & Editorial**: `Geist`, -apple-system, sans-serif (Weights: 400, 500; line-height: 1.6; max measure: 68ch).
- **Technical & Telemetry**: `JetBrains Mono`, monospace (Weights: 400, 500; letter-spacing: `-0.01em`).

*Typography Bans*: Banned `Inter`. Banned generic script or screaming uppercase H1s.

---

## 4. Anti-Patterns & AI Tells (Strictly Prohibited)

- 🚫 **No AI buzzwords**: Banned "Elevate", "Seamless", "Next-Gen", "Unleash", "Game-changing".
- 🚫 **No fake round metrics**: Use organic telemetry values (e.g., `JSD = 0.0056`, `H_norm = 0.9977`, `40.3ms layout`).
- 🚫 **No 3 identical cards in a row**: Use asymmetric split grids, timeline tracks, and interactive state viewers.
- 🚫 **No emojis as UI icons**: Clean SVG vector glyphs only.

---

## 5. Signature Element

**Interactive Live Pipeline Inspector & Execution Timeline Scrubber**:
A bidirectional timeline scrubber tracing the end-to-end execution of `create 5 pages on cat with images`:
1. *Intent Decomposition & Entity Extraction* (Separating topic `domestic cats` from constraints `5 pages`, `with images`).
2. *RLCD Decision Consensus* (Structural prior vs learned policy; JSD divergence; entropy gate).
3. *Multimodal Asset Acquisition* (Magic byte verification, SHA-256 caching, EMU dimension scaling).
4. *Domain-Grounded Prose Synthesis* (Near Eastern wildcat lineage, tapetum lucidum, floating clavicle).
5. *OpenXML / DrawingML Assembly* (`word/media/`, relationship IDs, WordCraft & native XML composition).
6. *Automated Validation & Conformance* (OOXML schema validation, LibreOffice & WordCraft rendering).
