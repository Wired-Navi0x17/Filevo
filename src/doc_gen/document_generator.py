"""Document Generation Module.

Combines codebase analysis results with the RL probabilistic model to generate
documents. All structural decisions (which sections, what depth, whether to
include formulas) are made by the RL model's Choice/Score/Noul primitives.

No hardcoded templates — content is synthesized from actual AST data.
"""

import math
import os
import random
from datetime import datetime
from pathlib import Path

from src.doc_gen.codebase_analyzer import CodebaseAnalyzer
from src.doc_gen.rl_model import RLProbabilisticModel


class DocumentGenerator:
    """Generates documents from codebase analysis using RL model decisions.

    Key design:
    1. Model decisions via Choice/Score/Noul primitives
    2. Content grounded in actual AST analysis (no hallucinated facts)
    3. Trajectory recorded for reward attribution
    """

    def __init__(self, model: RLProbabilisticModel | None = None,
                 analyzer: CodebaseAnalyzer | None = None):
        self.model = model or RLProbabilisticModel()
        self.analyzer = analyzer

    def generate_from_codebase(self, codebase_path: str,
                               output_path: str | None = None,
                               format: str = "md") -> str:
        """Generate a document analyzing the given codebase.

        Returns path to the generated document file.
        """
        # Step 1: Analyze the codebase
        if self.analyzer is None:
            self.analyzer = CodebaseAnalyzer(codebase_path)
        insights = self.analyzer.get_insights()

        # Step 2: Use RL model to make structural decisions (record trajectory)
        decisions, trajectory = self._make_decisions(insights)

        # Step 3: Generate content for selected sections
        sections = self._generate_sections(insights, decisions)

        # Step 4: Assemble final document
        document = self._assemble_document(sections, decisions, insights)

        # Step 5: Record trajectory for later reward attribution
        self.model.record_trajectory(trajectory)

        # Step 6: Write output
        if output_path is None:
            output_dir = Path.home() / ".filevo" / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = str(output_dir / f"doc_{timestamp}.{format}")

        self._write_output(document, output_path, format)
        return output_path

    def _make_decisions(self, insights: dict) -> tuple[dict, dict]:
        """Use RL model primitives to decide document structure.

        Returns (decisions_dict, trajectory_dict).
        """
        trajectory = {"choices": [], "gates": []}

        # Choice: Which sections to include
        section_features = [
            "section_introduction",
            "section_methodology",
            "section_architecture",
            "section_patterns",
            "section_complexity",
            "section_conclusion",
        ]
        section_probs = self.model.softmax(section_features)

        # Select top sections by probability (at least 3)
        sorted_sections = sorted(section_probs.items(), key=lambda x: -x[1])
        n_sections = max(3, sum(1 for _, p in sorted_sections if p > 1.0 / len(section_features)))
        selected_sections = [feat for feat, _ in sorted_sections[:n_sections]]

        for feat in section_features:
            trajectory["choices"].append({
                "feature_set": section_features,
                "selected": feat if feat in selected_sections else None,
            })
        # Record as a single categorical choice (the top pick)
        trajectory["choices"] = [{
            "feature_set": section_features,
            "selected": selected_sections[0],
        }]

        # Score: Math rigor level
        rigor_feats = ["rigor_none", "rigor_asymptotic", "rigor_formal"]
        rigor_level, rigor_conf = self.model.score(rigor_feats)
        trajectory["choices"].append({
            "feature_set": rigor_feats,
            "selected": rigor_level,
        })

        # Score: Detail depth
        depth_feats = ["depth_brief", "depth_standard", "depth_deep"]
        depth_level, depth_conf = self.model.score(depth_feats)
        trajectory["choices"].append({
            "feature_set": depth_feats,
            "selected": depth_level,
        })

        # Noul: Boolean gates
        include_formulas = self.model.sample_binary("include_formulas")
        include_diagrams = self.model.sample_binary("include_diagrams")
        include_benchmarks = self.model.sample_binary("include_benchmarks")

        trajectory["gates"].extend([
            {"feature": "include_formulas", "selected": include_formulas},
            {"feature": "include_diagrams", "selected": include_diagrams},
            {"feature": "include_benchmarks", "selected": include_benchmarks},
        ])

        decisions = {
            "sections": selected_sections,
            "section_probabilities": section_probs,
            "rigor_level": rigor_level,
            "rigor_confidence": rigor_conf,
            "depth_level": depth_level,
            "depth_confidence": depth_conf,
            "include_formulas": include_formulas,
            "include_diagrams": include_diagrams,
            "include_benchmarks": include_benchmarks,
        }

        return decisions, trajectory

    def _generate_sections(self, insights: dict, decisions: dict) -> list[dict]:
        """Generate content for each selected section based on AST data."""
        sections = []
        file_count = insights.get("file_count", 0)
        func_count = insights.get("function_count", 0)
        class_count = insights.get("class_count", 0)
        avg_complexity = insights.get("avg_complexity", 0)
        max_complexity = insights.get("max_complexity", 0)

        raw_insights = insights.get("insights", {})
        functions = raw_insights.get("functions", {})
        classes = raw_insights.get("classes", {})
        imports = raw_insights.get("imports", {})
        patterns = raw_insights.get("patterns", {})
        complexity_data = raw_insights.get("complexity", {})

        for section_key in decisions["sections"]:
            section_name = section_key.replace("section_", "")

            if section_name == "introduction":
                content = self._build_introduction(
                    file_count, func_count, class_count, avg_complexity,
                    decisions
                )
                sections.append({"title": "Introduction", "content": content})

            elif section_name == "architecture":
                content = self._build_architecture(
                    file_count, func_count, class_count, classes, imports
                )
                sections.append({"title": "Architecture Analysis", "content": content})

            elif section_name == "methodology":
                content = self._build_methodology(
                    file_count, avg_complexity, decisions
                )
                sections.append({"title": "Methodology", "content": content})

            elif section_name == "patterns":
                content = self._build_patterns(patterns, classes)
                sections.append({"title": "Detected Patterns", "content": content})

            elif section_name == "complexity":
                content = self._build_complexity(
                    complexity_data, functions, avg_complexity, max_complexity,
                    decisions
                )
                sections.append({"title": "Complexity Analysis", "content": content})

            elif section_name == "conclusion":
                content = self._build_conclusion(
                    file_count, func_count, class_count, avg_complexity, patterns
                )
                sections.append({"title": "Conclusion", "content": content})

        return sections

    # ------------------------------------------------------------------ #
    # Section Builders — grounded in actual AST data
    # ------------------------------------------------------------------ #

    def _build_introduction(self, file_count, func_count, class_count,
                            avg_complexity, decisions) -> str:
        lines = [
            f"This report analyzes a Python codebase comprising **{file_count}** source files, "
            f"**{func_count}** functions, and **{class_count}** classes.",
            "",
        ]

        if avg_complexity > 0:
            if avg_complexity < 3:
                complexity_desc = "low overall complexity, suggesting well-factored code"
            elif avg_complexity < 7:
                complexity_desc = "moderate complexity, typical of production systems"
            else:
                complexity_desc = "high complexity, indicating dense algorithmic logic"
            lines.append(f"The codebase exhibits {complexity_desc} "
                        f"(average cyclomatic complexity: {avg_complexity:.1f}).")
            lines.append("")

        if decisions.get("include_formulas") and decisions.get("rigor_level") != "rigor_none":
            lines.append(
                f"Complexity measurements use cyclomatic complexity "
                f"$CC = E - N + 2P$, where $E$ = edges, $N$ = nodes, "
                f"$P$ = connected components in the control flow graph."
            )
            lines.append("")

        depth = decisions.get("depth_level", "depth_standard")
        if depth == "depth_deep":
            lines.append(
                "This deep-dive analysis examines structural patterns, dependency "
                "relationships, algorithmic complexities, and provides quantitative "
                "metrics for each major component."
            )
        elif depth == "depth_brief":
            lines.append(
                "This executive summary highlights the key structural "
                "characteristics of the codebase."
            )
        else:
            lines.append(
                "The following sections detail the architecture, detected patterns, "
                "and complexity characteristics observed across the project."
            )

        return "\n".join(lines)

    def _build_architecture(self, file_count, func_count, class_count,
                            classes, imports) -> str:
        lines = [
            f"The codebase organizes **{func_count}** functions across "
            f"**{class_count}** classes in **{file_count}** modules.",
            "",
        ]

        # List actual classes found
        if classes:
            lines.append("### Key Classes")
            lines.append("")
            for key, cdata in list(classes.items())[:10]:
                name = cdata.get("name", "Unknown")
                methods = cdata.get("methods", [])
                bases = cdata.get("bases", [])
                base_str = f" (extends {', '.join(bases)})" if bases else ""
                lines.append(f"- **{name}**{base_str}: {len(methods)} methods")
                if methods[:5]:
                    method_list = ", ".join(f"`{m}`" for m in methods[:5])
                    if len(methods) > 5:
                        method_list += f", ... (+{len(methods)-5} more)"
                    lines.append(f"  - Methods: {method_list}")
            lines.append("")

        # Top imports
        all_imports = set()
        for imp_data in imports.values():
            for mod in imp_data.get("modules", []):
                top_mod = mod.split(".")[0]
                all_imports.add(top_mod)

        if all_imports:
            lines.append("### Key Dependencies")
            lines.append("")
            for mod in sorted(all_imports)[:15]:
                lines.append(f"- `{mod}`")
            lines.append("")

        return "\n".join(lines)

    def _build_methodology(self, file_count, avg_complexity, decisions) -> str:
        lines = [
            "The analysis methodology follows a structured pipeline:",
            "",
            "1. **AST Parsing**: Each Python file is parsed into an Abstract Syntax Tree "
            "to extract functions, classes, imports, and structural elements.",
            "",
            "2. **Dependency Mapping**: Import statements are tracked to build a "
            "module dependency graph.",
            "",
            "3. **Cyclomatic Complexity Measurement**: Control flow decision points "
            "(if/while/for/try/except/assert/boolean operators) are counted per function.",
            "",
        ]

        if avg_complexity > 0:
            lines.append(
                f"4. **Aggregate Statistics**: Across {file_count} files, the average "
                f"cyclomatic complexity is **{avg_complexity:.1f}**, indicating "
                f"{'relatively modular' if avg_complexity < 5 else 'denser'} code."
            )
            lines.append("")

        lines.append(
            f"5. **Pattern Detection**: Structural analysis identifies class hierarchies, "
            f"context managers, test suites, and decorator usage patterns."
        )
        lines.append("")

        if decisions.get("include_formulas"):
            lines.append(
                "6. **Formal Metrics**: Cyclomatic complexity is defined as "
                "$CC = E - N + 2P$ where $E$ = edges in the control flow graph, "
                "$N$ = nodes, and $P$ = connected components."
            )

        return "\n".join(lines)

    def _build_patterns(self, patterns, classes) -> str:
        if not patterns:
            lines = [
                "No recurrent structural patterns were detected in the codebase. "
                "This may indicate a procedural codebase without explicit "
                "object-oriented design patterns.",
            ]
            return "\n".join(lines)

        lines = ["The following structural patterns were identified:", ""]

        for pattern_name, pattern_data in sorted(patterns.items()):
            count = pattern_data.get("count", 0)
            density = pattern_data.get("density", 0)
            display_name = pattern_name.replace("_", " ").title()
            lines.append(f"- **{display_name}**: {count} occurrence(s) "
                        f"(density: {density:.3f} per file)")

        lines.append("")
        total = sum(d.get("count", 0) for d in patterns.values())
        lines.append(
            f"Total pattern instances: **{total}**. These patterns provide insight "
            f"into the codebase's architectural style and maintainability characteristics."
        )

        return "\n".join(lines)

    def _build_complexity(self, complexity_data, functions, avg_complexity,
                          max_complexity, decisions) -> str:
        lines = [
            f"**Average cyclomatic complexity**: {avg_complexity:.1f}",
            f"**Maximum cyclomatic complexity**: {max_complexity}",
            "",
        ]

        if decisions.get("include_formulas"):
            lines.extend([
                "Cyclomatic complexity measures the number of linearly independent "
                "paths through a function:",
                "",
                "$$CC = E - N + 2P$$",
                "",
                "where $E$ = edges in the control flow graph, $N$ = nodes, "
                "and $P$ = connected components.",
                "",
            ])

        # Show most complex functions
        complex_funcs = []
        for key, fdata in functions.items():
            cc = fdata.get("complexity", 1)
            if cc > 1:
                complex_funcs.append((fdata.get("name", "?"), cc, key))

        if complex_funcs:
            complex_funcs.sort(key=lambda x: -x[1])
            lines.append("### Most Complex Functions")
            lines.append("")
            lines.append("| Function | Complexity | Location |")
            lines.append("|---|---|---|")
            for name, cc, loc in complex_funcs[:10]:
                file_part = loc.split("::")[-2] if "::" in loc else loc
                file_part = Path(file_part).name if "/" in file_part or "\\" in file_part else file_part
                lines.append(f"| `{name}` | {cc} | {file_part} |")
            lines.append("")

        # Complexity distribution commentary
        if avg_complexity < 3:
            lines.append(
                "The low average complexity suggests well-factored, testable code "
                "with single-responsibility functions."
            )
        elif avg_complexity < 7:
            lines.append(
                "Moderate complexity indicates a typical production codebase. "
                "Functions with complexity > 10 may benefit from refactoring."
            )
        else:
            lines.append(
                "High average complexity suggests dense control flow. "
                "Consider decomposing complex functions for improved testability."
            )

        return "\n".join(lines)

    def _build_conclusion(self, file_count, func_count, class_count,
                          avg_complexity, patterns) -> str:
        lines = [
            f"This analysis examined **{file_count}** Python files containing "
            f"**{func_count}** functions and **{class_count}** classes.",
            "",
        ]

        if avg_complexity > 0:
            lines.append(
                f"The average cyclomatic complexity of **{avg_complexity:.1f}** "
                f"{'indicates maintainable code' if avg_complexity < 5 else 'suggests opportunities for refactoring'}."
            )
            lines.append("")

        pattern_count = sum(d.get("count", 0) for d in patterns.values())
        if pattern_count > 0:
            lines.append(
                f"**{pattern_count}** structural pattern instances were identified, "
                f"providing insight into the project's architectural maturity."
            )
            lines.append("")

        lines.append(
            "Further analysis with expanded metrics (coupling, cohesion, test coverage) "
            "would yield additional insights into long-term evolution potential."
        )

        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Document Assembly
    # ------------------------------------------------------------------ #

    def _assemble_document(self, sections: list[dict], decisions: dict,
                           insights: dict) -> str:
        lines = []
        file_count = insights.get("file_count", 0)
        func_count = insights.get("function_count", 0)

        # Title
        lines.append("# Codebase Analysis Report")
        lines.append(f"*Generated from {file_count} source files with {func_count} functions*")
        lines.append(f"*Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        lines.append("")

        # Table of Contents
        lines.append("## Table of Contents")
        for i, sec in enumerate(sections, 1):
            anchor = sec["title"].lower().replace(" ", "-")
            lines.append(f"{i}. [{sec['title']}](#{anchor})")
        lines.append("")

        # Sections
        for sec in sections:
            lines.append(f"## {sec['title']}")
            lines.append("")
            lines.append(sec["content"])
            lines.append("")

        # Appendix: Model Decision Summary
        lines.append("---")
        lines.append("## Appendix: Generation Metadata")
        lines.append("")
        lines.append(f"- **Sections generated**: {len(sections)}")
        lines.append(f"- **Math rigor**: {decisions.get('rigor_level', 'N/A').replace('rigor_', '')}")
        lines.append(f"- **Detail depth**: {decisions.get('depth_level', 'N/A').replace('depth_', '')}")
        lines.append(f"- **Formulas included**: {decisions.get('include_formulas', False)}")
        lines.append(f"- **Model episodes**: {self.model.episode_count}")
        lines.append("")

        # Section probability snapshot
        lines.append("### Section Selection Probabilities")
        lines.append("")
        lines.append("| Section | Probability | Selected |")
        lines.append("|---|---|---|")
        for feat, prob in sorted(decisions.get("section_probabilities", {}).items(), key=lambda x: -x[1]):
            name = feat.replace("section_", "").capitalize()
            selected = "✓" if feat in decisions.get("sections", []) else ""
            lines.append(f"| {name} | {prob:.4f} | {selected} |")
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _write_output(document: str, output_path: str, format: str):
        """Write the document to the specified path."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if format == "md":
            with open(path, "w", encoding="utf-8") as f:
                f.write(document)
        else:
            # Fallback: always write markdown (PDF/DOCX require external tools)
            md_path = path.with_suffix(".md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(document)
            if str(path) != str(md_path):
                # Inform user that format conversion requires external tools
                print(f"  Note: {format} export requires external tools. Saved as: {md_path}")


class DocumentTrainer:
    """Handles model training from user feedback on generated documents."""

    def __init__(self, model: RLProbabilisticModel):
        self.model = model

    def provide_reward(self, reward: float) -> dict | None:
        """Provide a reward signal linked to the last generation trajectory.

        Returns update metrics for live display, or None if no trajectory found.
        """
        trajectory = self.model.get_last_trajectory()
        if trajectory is None:
            # Fallback: create a default trajectory covering all features
            section_feats = [f for f in self.model.weights if f.startswith("section_")]
            trajectory = {
                "choices": [
                    {"feature_set": section_feats, "selected": section_feats[0] if section_feats else "section_introduction"},
                    {"feature_set": ["rigor_none", "rigor_asymptotic", "rigor_formal"], "selected": "rigor_asymptotic"},
                    {"feature_set": ["depth_brief", "depth_standard", "depth_deep"], "selected": "depth_standard"},
                ],
                "gates": [
                    {"feature": "include_formulas", "selected": True},
                    {"feature": "include_diagrams", "selected": False},
                    {"feature": "include_benchmarks", "selected": False},
                ],
            }

        return self.model.update(trajectory, reward)

    def get_training_report(self) -> dict:
        """Get the current model training state."""
        return self.model.get_training_report()