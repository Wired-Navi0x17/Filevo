# Academic Corpus Metadata Analysis & Provenance Audit Report

**Date of Execution**: 2026-10-21 13:26:29 UTC  
**Actual Metadata Records Ingested**: **200 OpenAlex JSON records**  
**Full-Text Documents Downloaded**: 0  
**Model Parameters Updated**: 0 (Corpus summary analysis only, not model training)  
**Execution Duration**: 24.01 seconds  
**Profile Path**: [`data/academic_model_profile.json`](file:///home/l41n-pr0t0/Workspace/University/Semester 3/CS2227 - AI and ML/CIE/data/academic_model_profile.json)

---

## 1. Verified Data Provenance & Audit Status

This run records the actual metadata records retrieved from the OpenAlex Works API (`https://api.openalex.org/works`).
A prior run recorded a claim of 10,000 papers trained due to a synthetic fallback loop in an `except` block. That loop has been eliminated.
No model training occurred during this process; the script strictly extracted vocabulary distributions and citation frequencies from JSON summaries.

1. **OpenAlex Global Open Research Corpus** (`https://api.openalex.org/works`):
   - Open catalog of scholarly works, indexing metadata, DOIs, citation graphs, and inverted abstract indexes.
   - Filter criteria applied: `has_doi:true`, `type:article`, `language:en`.

---

## 2. Statistical Findings & Model Invariants

- **Sample Size Analyzed**: 200 metadata records
- **Average Citations per Record**: 62437.4
- **Average Abstract Length**: 152.0 words
- **Top Observed Concepts**: Computer science, Mathematics, Biology, Physics, Statistics

Note: Structural formatting rules (IEEE Roman numerals, Booktabs horizontal rules, dual column layout) are deterministic publication standards enforced in code, not learned model parameters.

---

## 3. Sample of Ingested Research Papers

| # | DOI | Title | Year | Citations |
|---|---|---|---|---|
| 1 | [https://doi.org/10.1585/pfr.15.2402039](https://doi.org/10.1585/pfr.15.2402039) | Radiation Resistant Camera System for Monitoring Deuterium Plasma Discharges in the Large Helical Device | 2020 | 801217 |
| 2 | [https://doi.org/10.1016/s0021-9258(19)52451-6](https://doi.org/10.1016/s0021-9258(19)52451-6) | PROTEIN MEASUREMENT WITH THE FOLIN PHENOL REAGENT | 1951 | 317528 |
| 3 | [https://doi.org/10.1006/abio.1976.9999](https://doi.org/10.1006/abio.1976.9999) | A Rapid and Sensitive Method for the Quantitation of Microgram Quantities of Protein Utilizing the Principle of Protein-Dye Binding | 1976 | 255160 |
| 4 | [https://doi.org/10.1038/227680a0](https://doi.org/10.1038/227680a0) | Cleavage of Structural Proteins during the Assembly of the Head of Bacteriophage T4 | 1970 | 249911 |
| 5 | [https://doi.org/10.1103/physrevlett.77.3865](https://doi.org/10.1103/physrevlett.77.3865) | Generalized Gradient Approximation Made Simple | 1996 | 214918 |
| 6 | [https://doi.org/10.1191/1478088706qp063oa](https://doi.org/10.1191/1478088706qp063oa) | Using thematic analysis in psychology | 2006 | 193071 |
| 7 | [https://doi.org/10.1006/meth.2001.1262](https://doi.org/10.1006/meth.2001.1262) | Analysis of Relative Gene Expression Data Using Real-Time Quantitative PCR and the 2−ΔΔCT Method | 2001 | 180496 |
| 8 | [https://doi.org/10.1023/a:1010933404324](https://doi.org/10.1023/a:1010933404324) | Random Forests | 2001 | 132218 |
| 9 | [https://doi.org/10.1103/physrevb.54.11169](https://doi.org/10.1103/physrevb.54.11169) | Efficient iterative schemes for ab initio total-energy calculations using a plane-wave basis set | 1996 | 123252 |
| 10 | [https://doi.org/10.1145/3065386](https://doi.org/10.1145/3065386) | ImageNet classification with deep convolutional neural networks | 2017 | 112093 |
| 11 | [https://doi.org/10.1111/j.2517-6161.1995.tb02031.x](https://doi.org/10.1111/j.2517-6161.1995.tb02031.x) | Controlling the False Discovery Rate: A Practical and Powerful Approach to Multiple Testing | 1995 | 108840 |
| 12 | [https://doi.org/10.1177/002224378101800104](https://doi.org/10.1177/002224378101800104) | Evaluating Structural Equation Models with Unobservable Variables and Measurement Error | 1981 | 108594 |
| 13 | [https://doi.org/10.1080/10705519909540118](https://doi.org/10.1080/10705519909540118) | Cutoff criteria for fit indexes in covariance structure analysis: Conventional criteria versus new alternatives | 1999 | 108386 |
| 14 | [https://doi.org/10.3322/caac.21660](https://doi.org/10.3322/caac.21660) | Global Cancer Statistics 2020: GLOBOCAN Estimates of Incidence and Mortality Worldwide for 36 Cancers in 185 Countries | 2021 | 108330 |
| 15 | [https://doi.org/10.1063/1.464913](https://doi.org/10.1063/1.464913) | Density-functional thermochemistry. III. The role of exact exchange | 1993 | 103601 |

---

## 4. Verification & Model Readiness

The model profile has been successfully integrated into:
- [`src/ieee_latex_creator.py`](file:///home/l41n-pr0t0/Workspace/University/Semester%203/CS2227%20-%20AI%20and%20ML/CIE/src/ieee_latex_creator.py)
- [`src/docx_creator.py`](file:///home/l41n-pr0t0/Workspace/University/Semester%203/CS2227%20-%20AI%20and%20ML/CIE/src/docx_creator.py)
- [`src/research_engine.py`](file:///home/l41n-pr0t0/Workspace/University/Semester%203/CS2227%20-%20AI%20and%20ML/CIE/src/research_engine.py)
