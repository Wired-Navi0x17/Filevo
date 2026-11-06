//! Granular Decision Catalogue (Domains A through J).
//!
//! Exposes atomic, descriptive decision schemas covering every facet of document design.

use crate::schema::{ChoiceOption, DecisionSchema, NoulCondition};

pub fn build_catalogue() -> Vec<DecisionSchema> {
    vec![
        // ==========================================
        // Domain A: Page Geometry
        // ==========================================
        DecisionSchema::Choice {
            id: "page_geometry:paper_size".into(),
            domain: "Page Geometry".into(),
            description: "Physical dimensions of the output page.".into(),
            options: vec![
                ChoiceOption {
                    id: "A4".into(),
                    label: "A4 (210 x 297 mm)".into(),
                    description: "Standard international paper size used globally outside North America.".into(),
                    visual_characteristics: "Tall, balanced aspect ratio (1:1.414).".into(),
                    recommended_when: "International reports, academic monographs, ISO standard documents.".into(),
                    limitations: "Less standard in North America.".into(),
                },
                ChoiceOption {
                    id: "Letter".into(),
                    label: "US Letter (8.5 x 11 in)".into(),
                    description: "Standard North American office and legal paper size.".into(),
                    visual_characteristics: "Slightly wider and shorter than A4.".into(),
                    recommended_when: "US/Canadian corporate, academic, and governmental deliverables.".into(),
                    limitations: "Less standard in Europe and Asia.".into(),
                },
                ChoiceOption {
                    id: "Legal".into(),
                    label: "US Legal (8.5 x 14 in)".into(),
                    description: "Extended page format for comprehensive tables or contracts.".into(),
                    visual_characteristics: "Noticeably elongated vertical profile.".into(),
                    recommended_when: "Legal briefs, statutory contracts, complex financial registers.".into(),
                    limitations: "Awkward to read on standard displays without zooming.".into(),
                },
            ],
            default_fallback: "Letter".into(),
            dependencies: vec![],
            selection_criteria: "Select based on geographic locale and publication target.".into(),
            constraints: vec!["Must be a standard supported OpenXML page dimension.".into()],
        },
        DecisionSchema::Choice {
            id: "page_geometry:orientation".into(),
            domain: "Page Geometry".into(),
            description: "Orientation of pages in the main body.".into(),
            options: vec![
                ChoiceOption {
                    id: "Portrait".into(),
                    label: "Portrait".into(),
                    description: "Vertical orientation optimized for reading long-form text.".into(),
                    visual_characteristics: "Standard book/report format.".into(),
                    recommended_when: "General narratives, academic monographs, corporate reports.".into(),
                    limitations: "Restricted width for wide multi-column tables.".into(),
                },
                ChoiceOption {
                    id: "Landscape".into(),
                    label: "Landscape".into(),
                    description: "Horizontal orientation optimized for broad tables and data matrices.".into(),
                    visual_characteristics: "Panoramic wide profile.".into(),
                    recommended_when: "Data dashboards, wide balance sheets, multi-column comparison tables.".into(),
                    limitations: "Tiring to read multi-paragraph prose.".into(),
                },
            ],
            default_fallback: "Portrait".into(),
            dependencies: vec![],
            selection_criteria: "Use Landscape only when wide tabular matrices predominate.".into(),
            constraints: vec!["Inverts page width and height dimensions in section properties.".into()],
        },
        DecisionSchema::Choice {
            id: "page_geometry:margins".into(),
            domain: "Page Geometry".into(),
            description: "Boundary distance from paper edge to printable text area.".into(),
            options: vec![
                ChoiceOption {
                    id: "Standard".into(),
                    label: "Standard 1.0 inch (72 pt / 1440 twips)".into(),
                    description: "Balanced traditional margins recommended by Chicago and APA.".into(),
                    visual_characteristics: "Formal, dignified whitespace.".into(),
                    recommended_when: "Formal publications, academic submissions, government filings.".into(),
                    limitations: "Consumes more pages than compact margins.".into(),
                },
                ChoiceOption {
                    id: "Compact".into(),
                    label: "Compact 0.75 inch (54 pt / 1080 twips)".into(),
                    description: "Efficient margins maximizing printable space per page.".into(),
                    visual_characteristics: "Denser textual presence, modern engineering aesthetic.".into(),
                    recommended_when: "Technical documentation, engineering specifications, executive briefs.".into(),
                    limitations: "Can feel crowded if line length exceeds 85 characters.".into(),
                },
                ChoiceOption {
                    id: "Spacious".into(),
                    label: "Spacious 1.25 inch (90 pt / 1800 twips)".into(),
                    description: "Generous margins creating wide editorial gutters.".into(),
                    visual_characteristics: "Literary, relaxed reading rhythm.".into(),
                    recommended_when: "Essays, monographs, artistic retrospectives.".into(),
                    limitations: "Reduces usable horizontal space.".into(),
                },
            ],
            default_fallback: "Standard".into(),
            dependencies: vec![],
            selection_criteria: "Match document density and reader environment.".into(),
            constraints: vec!["Printable width must be >= 3600 twips (2.5 inches).".into()],
        },
        DecisionSchema::Choice {
            id: "page_geometry:column_count".into(),
            domain: "Page Geometry".into(),
            description: "Number of text columns across the main body.".into(),
            options: vec![
                ChoiceOption {
                    id: "1".into(),
                    label: "Single Column".into(),
                    description: "Standard continuous single text column spanning page width.".into(),
                    visual_characteristics: "Continuous, clear hierarchy.".into(),
                    recommended_when: "Most technical documents, memos, monographs.".into(),
                    limitations: "Lines can exceed optimal 75-character length with narrow margins.".into(),
                },
                ChoiceOption {
                    id: "2".into(),
                    label: "Two Columns".into(),
                    description: "Two-column grid layout standard in IEEE and academic proceedings.".into(),
                    visual_characteristics: "Scholarly, dense, efficient space usage.".into(),
                    recommended_when: "Research papers, academic conference proceedings.".into(),
                    limitations: "Awkward for wide tables and full-width code blocks.".into(),
                },
            ],
            default_fallback: "1".into(),
            dependencies: vec![],
            selection_criteria: "Single column for technical manuals; two columns for IEEE/academic conference formats.".into(),
            constraints: vec!["Two-column layout requires minimum 720 twip column spacing.".into()],
        },

        // ==========================================
        // Domain B: Typography
        // ==========================================
        DecisionSchema::Choice {
            id: "typography:body_font".into(),
            domain: "Typography".into(),
            description: "Primary typeface used for body paragraphs and lists.".into(),
            options: vec![
                ChoiceOption {
                    id: "Aptos".into(),
                    label: "Aptos".into(),
                    description: "Microsoft's contemporary default neo-grotesque sans-serif.".into(),
                    visual_characteristics: "Clean, humanized geometric curves, exceptional screen legibility.".into(),
                    recommended_when: "Modern technical reports, executive memos, digital-first reading.".into(),
                    limitations: "Lacks traditional academic gravitas.".into(),
                },
                ChoiceOption {
                    id: "Times New Roman".into(),
                    label: "Times New Roman".into(),
                    description: "Traditional transitional serif typeface with high economy of space.".into(),
                    visual_characteristics: "Sharp serifs, high contrast, classical authority.".into(),
                    recommended_when: "Academic papers, legal briefs, formal monographs.".into(),
                    limitations: "Can feel archaic or template-like if unstyled.".into(),
                },
                ChoiceOption {
                    id: "Georgia".into(),
                    label: "Georgia".into(),
                    description: "Sturdy, elegant digital serif with generous x-height.".into(),
                    visual_characteristics: "Warm, literary, comfortable for prolonged reading.".into(),
                    recommended_when: "Long monographs, historical treatises, editorial publications.".into(),
                    limitations: "Numbers are non-lining old-style figures by default.".into(),
                },
                ChoiceOption {
                    id: "Calibri".into(),
                    label: "Calibri".into(),
                    description: "Soft, rounded humanist sans-serif with subtle warm strokes.".into(),
                    visual_characteristics: "Informative, approachable, compact width.".into(),
                    recommended_when: "Corporate proposals, internal guides, agile briefs.".into(),
                    limitations: "Less formal than Aptos or Times.".into(),
                },
            ],
            default_fallback: "Aptos".into(),
            dependencies: vec![],
            selection_criteria: "Sans-serif for technical and digital readability; serif for academic and formal authority.".into(),
            constraints: vec!["Typeface must be widely available across Windows, macOS, and Linux fallback systems.".into()],
        },
        DecisionSchema::Choice {
            id: "typography:heading_font".into(),
            domain: "Typography".into(),
            description: "Typeface used for Title, Subtitle, and Headings.".into(),
            options: vec![
                ChoiceOption {
                    id: "Aptos Display".into(),
                    label: "Aptos Display".into(),
                    description: "Display cut of Aptos with tighter letter spacing and sharpened terminals.".into(),
                    visual_characteristics: "Bold, modern architectural impact.".into(),
                    recommended_when: "Pairs with Aptos or Calibri body text.".into(),
                    limitations: "Clashes with serif body fonts like Times.".into(),
                },
                ChoiceOption {
                    id: "Georgia".into(),
                    label: "Georgia Bold".into(),
                    description: "Sturdy serif display heading with strong academic weight.".into(),
                    visual_characteristics: "Scholarly, authoritative, handsome contrast.".into(),
                    recommended_when: "Pairs with Georgia or Times New Roman body text.".into(),
                    limitations: "Heavy profile in small font sizes.".into(),
                },
                ChoiceOption {
                    id: "Arial".into(),
                    label: "Arial Black / Bold".into(),
                    description: "Neutral utilitarian grotesque sans-serif.".into(),
                    visual_characteristics: "Industrial, clean, objective.".into(),
                    recommended_when: "Standard engineering specifications.".into(),
                    limitations: "Visually uninspired.".into(),
                },
            ],
            default_fallback: "Aptos Display".into(),
            dependencies: vec!["typography:body_font".into()],
            selection_criteria: "Must harmonize with body font without jarring contrast clash.".into(),
            constraints: vec!["Cannot pair Times New Roman body with Arial headings.".into()],
        },
        DecisionSchema::Choice {
            id: "typography:code_font".into(),
            domain: "Typography".into(),
            description: "Monospace typeface used for code snippets and inline keywords.".into(),
            options: vec![
                ChoiceOption {
                    id: "Consolas".into(),
                    label: "Consolas".into(),
                    description: "Clear, highly legible modern programming monospace.".into(),
                    visual_characteristics: "Consistent glyph metrics, slashed zero, distinct punctuation.".into(),
                    recommended_when: "Default for all technical documentation and source blocks.".into(),
                    limitations: "Standard Microsoft typeface.".into(),
                },
                ChoiceOption {
                    id: "Courier New".into(),
                    label: "Courier New".into(),
                    description: "Traditional typewriter monospaced serif.".into(),
                    visual_characteristics: "Thin slab serifs, mechanical appearance.".into(),
                    recommended_when: "Retro technical specs or legal typewritten filings.".into(),
                    limitations: "Sprawling character pitch.".into(),
                },
            ],
            default_fallback: "Consolas".into(),
            dependencies: vec![],
            selection_criteria: "Consolas preferred for code blocks.".into(),
            constraints: vec!["Must be fixed-width monospace.".into()],
        },
        DecisionSchema::Choice {
            id: "typography:body_size".into(),
            domain: "Typography".into(),
            description: "Base font size for body prose in points.".into(),
            options: vec![
                ChoiceOption {
                    id: "10pt".into(),
                    label: "10 pt (20 half-points)".into(),
                    description: "Compact size suitable for high density documents and two-column layouts.".into(),
                    visual_characteristics: "High information density.".into(),
                    recommended_when: "Two-column conference proceedings, dense reference manuals.".into(),
                    limitations: "Requires sharp screen or high resolution print.".into(),
                },
                ChoiceOption {
                    id: "11pt".into(),
                    label: "11 pt (22 half-points)".into(),
                    description: "Modern standard reading size across contemporary typography.".into(),
                    visual_characteristics: "Balanced legibility and pacing.".into(),
                    recommended_when: "Technical reports, corporate deliverables, internal specifications.".into(),
                    limitations: "None.".into(),
                },
                ChoiceOption {
                    id: "12pt".into(),
                    label: "12 pt (24 half-points)".into(),
                    description: "Classical academic and legal size.".into(),
                    visual_characteristics: "Stately, large x-height.".into(),
                    recommended_when: "Academic theses, legal submissions, government filings.".into(),
                    limitations: "Consumes more vertical space.".into(),
                },
            ],
            default_fallback: "11pt".into(),
            dependencies: vec![],
            selection_criteria: "10pt for dense two-column; 11pt for technical reports; 12pt for formal academic monographs.".into(),
            constraints: vec!["Values must be mapped to valid OpenXML half-points.".into()],
        },
        DecisionSchema::Choice {
            id: "typography:line_spacing".into(),
            domain: "Typography".into(),
            description: "Line pitch multiplier for body prose.".into(),
            options: vec![
                ChoiceOption {
                    id: "1.0".into(),
                    label: "Single (240 twips)".into(),
                    description: "Tight single line pitch.".into(),
                    visual_characteristics: "Compact, dense.".into(),
                    recommended_when: "Tables, code blocks, lists.".into(),
                    limitations: "Harder to read across long prose lines.".into(),
                },
                ChoiceOption {
                    id: "1.15".into(),
                    label: "1.15 line pitch (276 twips)".into(),
                    description: "Contemporary standard for digital and office reading.".into(),
                    visual_characteristics: "Comfortable air without exaggerated vertical spread.".into(),
                    recommended_when: "Default for all reports and business documentation.".into(),
                    limitations: "None.".into(),
                },
                ChoiceOption {
                    id: "1.5".into(),
                    label: "1.5 line pitch (360 twips)".into(),
                    description: "Spacious academic draft spacing.".into(),
                    visual_characteristics: "Wide leading allowing editorial markup.".into(),
                    recommended_when: "Manuscript review, formal thesis drafts.".into(),
                    limitations: "Doubles page count quickly.".into(),
                },
            ],
            default_fallback: "1.15".into(),
            dependencies: vec![],
            selection_criteria: "1.15 for modern reading; 1.5 for draft reviews; 1.0 for tables and code.".into(),
            constraints: vec!["Mapped to w:line in twips with w:lineRule='auto'.".into()],
        },

        // ==========================================
        // Domain C: Paragraph Formatting
        // ==========================================
        DecisionSchema::Choice {
            id: "paragraphs:alignment".into(),
            domain: "Paragraph Formatting".into(),
            description: "Horizontal alignment policy for body text paragraphs.".into(),
            options: vec![
                ChoiceOption {
                    id: "Left".into(),
                    label: "Left-Aligned (Ragged Right)".into(),
                    description: "Even word spacing with a natural right ragged margin.".into(),
                    visual_characteristics: "Uniform word spacing, relaxed organic right margin.".into(),
                    recommended_when: "Modern technical reports, screen reading, short paragraphs.".into(),
                    limitations: "Does not have the sharp formal grid of justified text.".into(),
                },
                ChoiceOption {
                    id: "Justified".into(),
                    label: "Justified".into(),
                    description: "Text aligns flush to both left and right margins.".into(),
                    visual_characteristics: "Formal architectural columns.".into(),
                    recommended_when: "Academic monographs, published books, multi-column journals.".into(),
                    limitations: "Requires wide lines and hyphenation to avoid river gaps.".into(),
                },
            ],
            default_fallback: "Left".into(),
            dependencies: vec![],
            selection_criteria: "Left-align for technical reports; justified for academic monographs.".into(),
            constraints: vec!["Justified requires first-line indent or paragraph spacing.".into()],
        },
        DecisionSchema::Noul {
            id: "paragraphs:widow_orphan_control".into(),
            domain: "Paragraph Formatting".into(),
            description: "Whether to enforce widow and orphan suppression on all paragraphs.".into(),
            condition: NoulCondition {
                question: "Should paragraphs suppress lone orphan and widow lines across page breaks?".into(),
                true_condition: "All professional documents where pagination cleanliness is required.".into(),
                false_condition: "Never disabled in production documents.".into(),
                clarifying_criteria: "Emits w:widowControl on paragraph properties.".into(),
            },
            default_fallback: true,
            dependencies: vec![],
            selection_criteria: "Always true for publication quality.".into(),
            constraints: vec!["Enforced via <w:widowControl/> in docDefaults and pPr.".into()],
        },

        // ==========================================
        // Domain D: Heading Hierarchy
        // ==========================================
        DecisionSchema::Choice {
            id: "headings:h1_size".into(),
            domain: "Heading Hierarchy".into(),
            description: "Font size for Level 1 Section Headings in points.".into(),
            options: vec![
                ChoiceOption {
                    id: "16pt".into(),
                    label: "16 pt (32 half-points)".into(),
                    description: "Standard proportional size for primary section headings.".into(),
                    visual_characteristics: "Clear authority without visual shouting.".into(),
                    recommended_when: "Standard technical reports and monographs.".into(),
                    limitations: "None.".into(),
                },
                ChoiceOption {
                    id: "18pt".into(),
                    label: "18 pt (36 half-points)".into(),
                    description: "Prominent size for major chapter dividers.".into(),
                    visual_characteristics: "Strong section demarcation.".into(),
                    recommended_when: "Executive summaries and multi-chapter monographs.".into(),
                    limitations: "Can cause multi-line wrapping on long headings.".into(),
                },
            ],
            default_fallback: "16pt".into(),
            dependencies: vec![],
            selection_criteria: "Proportional to body font size.".into(),
            constraints: vec!["Must be larger than H2 size.".into()],
        },
        DecisionSchema::Choice {
            id: "headings:h2_size".into(),
            domain: "Heading Hierarchy".into(),
            description: "Font size for Level 2 Subsection Headings in points.".into(),
            options: vec![
                ChoiceOption {
                    id: "13pt".into(),
                    label: "13 pt (26 half-points)".into(),
                    description: "Subtle subsection heading size.".into(),
                    visual_characteristics: "Clean inline hierarchy.".into(),
                    recommended_when: "10pt or 11pt body text.".into(),
                    limitations: "Less contrast against 12pt body.".into(),
                },
                ChoiceOption {
                    id: "14pt".into(),
                    label: "14 pt (28 half-points)".into(),
                    description: "Standard subsection heading size.".into(),
                    visual_characteristics: "Distinct, recognizable subsection anchor.".into(),
                    recommended_when: "11pt or 12pt body text.".into(),
                    limitations: "None.".into(),
                },
            ],
            default_fallback: "14pt".into(),
            dependencies: vec!["headings:h1_size".into()],
            selection_criteria: "Must be smaller than H1 and larger than body.".into(),
            constraints: vec!["H2 size must satisfy Body < H2 < H1.".into()],
        },
        DecisionSchema::Noul {
            id: "headings:keep_with_next".into(),
            domain: "Heading Hierarchy".into(),
            description: "Whether to enforce keep-with-next pagination rules on all headings.".into(),
            condition: NoulCondition {
                question: "Should headings be kept with the next paragraph to prevent orphaned headings?".into(),
                true_condition: "All documents to eliminate orphaned headings at page bottoms.".into(),
                false_condition: "Never disabled.".into(),
                clarifying_criteria: "Emits w:keepNext on all heading paragraphs.".into(),
            },
            default_fallback: true,
            dependencies: vec![],
            selection_criteria: "Always true in professional document engineering.".into(),
            constraints: vec!["Must emit <w:keepNext/> on every heading style and instance.".into()],
        },

        // ==========================================
        // Domain E: Visual Identity & Color
        // ==========================================
        DecisionSchema::Choice {
            id: "visual:primary_accent".into(),
            domain: "Visual Identity".into(),
            description: "Primary accent color for headings, rules, and table headers.".into(),
            options: vec![
                ChoiceOption {
                    id: "1F4E79".into(),
                    label: "Deep Navy (#1F4E79)".into(),
                    description: "Trustworthy corporate and academic blue with high contrast.".into(),
                    visual_characteristics: "Stately, dependable, crisp contrast against white.".into(),
                    recommended_when: "Technical reports, formal corporate memos, research papers.".into(),
                    limitations: "Conservative and traditional.".into(),
                },
                ChoiceOption {
                    id: "2E75B6".into(),
                    label: "Slate Blue (#2E75B6)".into(),
                    description: "Modern vibrant blue suited for engineering documentation.".into(),
                    visual_characteristics: "Clean, technological, dynamic.".into(),
                    recommended_when: "Software specifications, engineering guides, product proposals.".into(),
                    limitations: "Slightly less contrast than Deep Navy.".into(),
                },
                ChoiceOption {
                    id: "2D6A4F".into(),
                    label: "Forest Green (#2D6A4F)".into(),
                    description: "Natural organic emerald green.".into(),
                    visual_characteristics: "Calm, biological, ecological.".into(),
                    recommended_when: "Life sciences, botany, sustainability reports, environmental studies.".into(),
                    limitations: "Niche semantic fit.".into(),
                },
                ChoiceOption {
                    id: "333333".into(),
                    label: "Charcoal Slate (#333333)".into(),
                    description: "Monochrome architectural dark gray.".into(),
                    visual_characteristics: "Minimalist, quiet luxury, distraction-free.".into(),
                    recommended_when: "Minimalist monographs, design critiques, philosophical essays.".into(),
                    limitations: "Lacks color differentiation.".into(),
                },
            ],
            default_fallback: "1F4E79".into(),
            dependencies: vec![],
            selection_criteria: "Align with document domain: navy for engineering/corporate; green for environmental/biological; charcoal for minimalist.".into(),
            constraints: vec!["Must pass minimum 4.5:1 WCAG contrast against white background.".into()],
        },

        // ==========================================
        // Domain F: Tables
        // ==========================================
        DecisionSchema::Choice {
            id: "tables:border_style".into(),
            domain: "Tables".into(),
            description: "Border styling policy for tabular blocks.".into(),
            options: vec![
                ChoiceOption {
                    id: "HorizontalRulesOnly".into(),
                    label: "Horizontal Rules Only (Booktabs Anti-Slop)".into(),
                    description: "Only top rule, header bottom rule, and table closing rule. Zero vertical lines.".into(),
                    visual_characteristics: "Clean, elegant, academic publishing standard.".into(),
                    recommended_when: "Academic papers, modern business reports, scientific data.".into(),
                    limitations: "Requires well-spaced columns to distinguish adjacent data.".into(),
                },
                ChoiceOption {
                    id: "MinimalGrid".into(),
                    label: "Subtle Grid".into(),
                    description: "Very light horizontal and vertical lines in 10% opacity gray.".into(),
                    visual_characteristics: "Disciplined data matrix without visual noise.".into(),
                    recommended_when: "Large technical matrices with dense numeric cells.".into(),
                    limitations: "Slightly higher visual clutter than horizontal rules.".into(),
                },
            ],
            default_fallback: "HorizontalRulesOnly".into(),
            dependencies: vec![],
            selection_criteria: "Horizontal rules preferred to prevent table clutter.".into(),
            constraints: vec!["Rendered with explicit OpenXML w:tblBorders.".into()],
        },
        DecisionSchema::Noul {
            id: "tables:zebra_shading".into(),
            domain: "Tables".into(),
            description: "Whether to apply alternating row shading to data rows.".into(),
            condition: NoulCondition {
                question: "Should table rows have alternating subtle gray shading?".into(),
                true_condition: "Table has >= 5 rows of dense numeric data requiring horizontal scanning.".into(),
                false_condition: "Table is compact (<= 4 rows) or uses clear horizontal rules.".into(),
                clarifying_criteria: "Zebra shading aids horizontal tracking across wide tables.".into(),
            },
            default_fallback: true,
            dependencies: vec![],
            selection_criteria: "Enabled for data-heavy reports.".into(),
            constraints: vec!["Zebra fill color must maintain WCAG contrast with text.".into()],
        },
        DecisionSchema::Noul {
            id: "tables:repeat_header".into(),
            domain: "Tables".into(),
            description: "Whether table header rows should repeat when spanning across page breaks.".into(),
            condition: NoulCondition {
                question: "Should the table header repeat at the top of each page if the table breaks?".into(),
                true_condition: "All professional tables to maintain context across pages.".into(),
                false_condition: "Never disabled for multi-page tables.".into(),
                clarifying_criteria: "Emits w:tblHeader on first row.".into(),
            },
            default_fallback: true,
            dependencies: vec![],
            selection_criteria: "Always true for professional tables.".into(),
            constraints: vec!["Must emit <w:tblHeader/> on header row.".into()],
        },
        DecisionSchema::Noul {
            id: "tables:cant_split".into(),
            domain: "Tables".into(),
            description: "Whether table rows should be prohibited from splitting awkwardly across page breaks.".into(),
            condition: NoulCondition {
                question: "Should individual table rows be kept intact on a single page?".into(),
                true_condition: "Prevents a single row of data from breaking across page boundaries.".into(),
                false_condition: "Only if row contains massive multi-paragraph cells.".into(),
                clarifying_criteria: "Emits w:cantSplit on table row properties.".into(),
            },
            default_fallback: true,
            dependencies: vec![],
            selection_criteria: "Recommended for clean pagination.".into(),
            constraints: vec!["Must emit <w:cantSplit/> on trPr.".into()],
        },

        // ==========================================
        // Domain H: Headers and Footers
        // ==========================================
        DecisionSchema::Noul {
            id: "headers_footers:include_page_numbers".into(),
            domain: "Headers & Footers".into(),
            description: "Whether to print page numbers in the document footer.".into(),
            condition: NoulCondition {
                question: "Should page numbers be included in the footer?".into(),
                true_condition: "Document has >= 2 pages and requires pagination navigation.".into(),
                false_condition: "Single-page letters or brief one-page memos.".into(),
                clarifying_criteria: "Emits PAGE and NUMPAGES fields in footer1.xml.".into(),
            },
            default_fallback: true,
            dependencies: vec![],
            selection_criteria: "True for all multi-page deliverables.".into(),
            constraints: vec!["Must use genuine OpenXML dynamic fields, never hardcoded numbers.".into()],
        },
        DecisionSchema::Noul {
            id: "headers_footers:different_first_page".into(),
            domain: "Headers & Footers".into(),
            description: "Whether the first (title) page suppresses header and footer content.".into(),
            condition: NoulCondition {
                question: "Should headers and footers be suppressed on the title page?".into(),
                true_condition: "Formal documents with a distinct title/cover presentation.".into(),
                false_condition: "Informal memos where content begins immediately at the top.".into(),
                clarifying_criteria: "Emits w:titlePg in sectPr.".into(),
            },
            default_fallback: true,
            dependencies: vec![],
            selection_criteria: "True for formal reports and monographs.".into(),
            constraints: vec!["Enforced via <w:titlePg/> in w:sectPr.".into()],
        },

        // ==========================================
        // Domain I: Navigation
        // ==========================================
        DecisionSchema::Noul {
            id: "navigation:include_toc".into(),
            domain: "Navigation".into(),
            description: "Whether to generate a Table of Contents at the front of the document.".into(),
            condition: NoulCondition {
                question: "Does this document warrant a Table of Contents?".into(),
                true_condition: "Document has >= 4 sections and spans >= 4 pages.".into(),
                false_condition: "Document is a short memo, brief letter, or <= 3 sections.".into(),
                clarifying_criteria: "Letters and short briefs must never include a TOC.".into(),
            },
            default_fallback: true,
            dependencies: vec![],
            selection_criteria: "True for technical reports and academic monographs; false for executive briefs.".into(),
            constraints: vec!["Requires bookmark anchors on all headings for hyperlink navigation.".into()],
        },
    ]
}
