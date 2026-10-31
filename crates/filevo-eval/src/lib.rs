//! Filevo Independent Quality Evaluation Engine.
//!
//! Provides objective, decoupled evaluation of generated documents:
//! section coverage, repetition analysis, telemetry absence, and preservation across revisions.

use filevo_docx::DocxDocument;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct QualityReport {
    pub schema_valid: bool,
    pub section_coverage: f32,
    pub missing_sections: Vec<String>,
    pub repetition_score: f32,
    pub telemetry_leaked: bool,
    pub leaked_strings: Vec<String>,
    pub factual_grounding: f32,
    pub composite_reward: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PreservationReport {
    pub untargeted_sections_preserved: bool,
    pub target_section_expanded: bool,
    pub mismatched_sections: Vec<String>,
    pub original_target_length: usize,
    pub revised_target_length: usize,
}

pub const FORBIDDEN_TELEMETRY: &[&str] = &[
    "agreement (jsd)",
    "normalized entropy",
    "decision gate",
    "synthesized with filevo rlcd engine",
    "edge processing unit",
    "target specification",
    "benchmark value",
    "policy episode",
];

pub struct QualityEvaluator;

impl QualityEvaluator {
    pub fn evaluate_document(
        expected_topic: &str,
        expected_sections: &[String],
        doc: &DocxDocument,
    ) -> QualityReport {
        let schema_valid = !doc.sections.is_empty();
        if !schema_valid {
            return QualityReport {
                schema_valid: false,
                section_coverage: 0.0,
                missing_sections: expected_sections.to_vec(),
                repetition_score: 0.0,
                telemetry_leaked: false,
                leaked_strings: Vec::new(),
                factual_grounding: 0.0,
                composite_reward: -1.0,
            };
        }

        // 1. Section coverage
        let mut missing_sections = Vec::new();
        let doc_headings: Vec<String> = doc.sections.iter().map(|s| s.heading.to_lowercase()).collect();

        for req in expected_sections {
            let req_lower = req.to_lowercase();
            if !doc_headings.iter().any(|h| h == &req_lower || h.contains(&req_lower) || req_lower.contains(h)) {
                missing_sections.push(req.clone());
            }
        }

        let section_coverage = if expected_sections.is_empty() {
            1.0
        } else {
            (expected_sections.len() - missing_sections.len()) as f32 / expected_sections.len() as f32
        };

        // 2. Leaked telemetry check
        let mut leaked_strings = Vec::new();
        let mut all_text = String::new();
        let mut total_words = 0;
        for sec in &doc.sections {
            for p in &sec.paragraphs {
                all_text.push_str(p);
                all_text.push(' ');
                total_words += p.split_whitespace().count();
            }
        }
        let all_text_lower = all_text.to_lowercase();

        for &forbidden in FORBIDDEN_TELEMETRY {
            if all_text_lower.contains(forbidden) {
                leaked_strings.push(forbidden.to_string());
            }
        }
        let telemetry_leaked = !leaked_strings.is_empty();

        // 3. Boilerplate detection
        let canned_boilerplate = [
            "split-brain state anomalies",
            "dead-letter queues",
            "tls-encrypted streaming",
            "ntp synchronization",
            "compliance requirements and architectural invariants",
            "adherence to production standards",
            "lorem ipsum",
        ];
        let mut boilerplate_count = 0;
        for &bp in &canned_boilerplate {
            if all_text_lower.contains(bp) {
                boilerplate_count += 1;
            }
        }

        // 4. Repetition score
        let mut duplicates = 0;
        let mut total_paras = 0;
        for sec in &doc.sections {
            total_paras += sec.paragraphs.len();
            for i in 1..sec.paragraphs.len() {
                if sec.paragraphs[i] == sec.paragraphs[i - 1] {
                    duplicates += 1;
                }
            }
        }
        let repetition_score = if total_paras > 0 {
            duplicates as f32 / total_paras as f32
        } else {
            0.0
        };

        // 5. Concept coverage / factual grounding
        let topic_terms: Vec<&str> = expected_topic
            .split_whitespace()
            .filter(|w| w.len() > 3 && !matches!(w.to_lowercase().as_str(), "create" | "report" | "about" | "with" | "using"))
            .collect();
        let mut matched_terms = 0;
        for term in &topic_terms {
            if all_text_lower.contains(&term.to_lowercase()) {
                matched_terms += 1;
            }
        }
        let factual_grounding = if topic_terms.is_empty() {
            0.8
        } else {
            (matched_terms as f32 / topic_terms.len() as f32).clamp(0.0, 1.0)
        };

        // 6. Composite reward calculation
        let mut reward = 0.45 * factual_grounding + 0.35 * section_coverage + 0.20 * (1.0 - repetition_score);

        if telemetry_leaked {
            reward -= 0.60;
        }
        if boilerplate_count > 0 {
            reward -= 0.50 * boilerplate_count as f32;
        }
        if total_words < 200 {
            reward -= 0.30;
        }
        if factual_grounding < 0.40 {
            reward = reward.min(0.15);
        }

        let composite_reward = reward.clamp(-1.0, 1.0);

        QualityReport {
            schema_valid,
            section_coverage,
            missing_sections,
            repetition_score,
            telemetry_leaked,
            leaked_strings,
            factual_grounding,
            composite_reward,
        }
    }

    pub fn evaluate_preservation(
        original: &DocxDocument,
        revised: &DocxDocument,
        target_section: &str,
    ) -> PreservationReport {
        let target_lower = target_section.trim().to_lowercase();
        let mut mismatched = Vec::new();
        let mut orig_len = 0;
        let mut rev_len = 0;

        for orig_sec in &original.sections {
            let is_target = orig_sec.heading.to_lowercase().contains(&target_lower);
            if is_target {
                orig_len = orig_sec.paragraphs.iter().map(|p| p.len()).sum();
            } else {
                // Must match in revised
                if let Some(rev_sec) = revised.sections.iter().find(|s| s.heading == orig_sec.heading) {
                    if rev_sec.paragraphs != orig_sec.paragraphs {
                        mismatched.push(orig_sec.heading.clone());
                    }
                } else {
                    mismatched.push(orig_sec.heading.clone());
                }
            }
        }

        if let Some(rev_target) = revised.sections.iter().find(|s| s.heading.to_lowercase().contains(&target_lower)) {
            rev_len = rev_target.paragraphs.iter().map(|p| p.len()).sum();
        }

        PreservationReport {
            untargeted_sections_preserved: mismatched.is_empty(),
            target_section_expanded: rev_len > orig_len,
            mismatched_sections: mismatched,
            original_target_length: orig_len,
            revised_target_length: rev_len,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_quality_evaluation_clean_document() {
        let mut doc = DocxDocument::new("Cricket Scoring Report");
        doc.add_section("Introduction", vec![
            "This technical report presents the system architecture and edge deployment of an automated cricket scoring platform. The system leverages high-speed IoT optical barriers and ball tracking telemetry to accurately register pitch bounces, wickets, and run completions in real time.".into()
        ]);
        doc.add_section("Hardware Design", vec![
            "The physical edge infrastructure comprises an ESP32 dual-core microcontroller interfaced with precision optical gate sensors, ambient lux calibration phototransistors, and ultra-wideband transceivers for real-time edge processing.".into()
        ]);
        doc.add_section("Methodology", vec![
            "The methodology implements an event-driven finite state tracking algorithm. Sensor signals are sampled via hardware interrupts, filtered through a moving average window, and transformed into distinct ball transit state vectors.".into()
        ]);
        doc.add_section("Testing", vec![
            "Comprehensive empirical testing was conducted across 50 simulated match overs under variable stadium illumination conditions. The system recorded zero dropped ball event frames with a 99.8% precision score.".into()
        ]);
        doc.add_section("Conclusion", vec![
            "The edge IoT cricket scoring system demonstrates robust operational reliability, strict latency guarantees under 25 milliseconds, and complete hardware-software integration suitable for tournament deployment.".into()
        ]);

        let req_sections = vec![
            "Introduction".into(),
            "Hardware Design".into(),
            "Methodology".into(),
            "Testing".into(),
            "Conclusion".into(),
        ];

        let report = QualityEvaluator::evaluate_document("cricket scoring report", &req_sections, &doc);
        assert!(report.schema_valid);
        assert_eq!(report.section_coverage, 1.0);
        assert!(!report.telemetry_leaked);
        assert!(report.composite_reward > 0.6, "Substantive clean doc must receive high positive reward, got {}", report.composite_reward);
    }

    #[test]
    fn test_telemetry_leakage_penalized() {
        let mut doc = DocxDocument::new("Cricket Scoring Report");
        doc.add_section("Introduction", vec!["Agreement (JSD): 0.12, normalized entropy: 0.44".into()]);

        let report = QualityEvaluator::evaluate_document("cricket", &["Introduction".into()], &doc);
        assert!(report.telemetry_leaked);
        assert!(report.leaked_strings.contains(&"agreement (jsd)".to_string()));
        assert!(report.composite_reward < 0.2, "Telemetry leakage must trigger heavy penalty");
    }

    #[test]
    fn test_generic_boilerplate_penalized() {
        let mut doc = DocxDocument::new("IoT Cricket Scoring System");
        doc.add_section("Introduction", vec![
            "The architecture employs resilient microservice components communicating over TLS-encrypted streaming protocols with dead-letter queues. Split-brain state anomalies are mitigated via Raft consensus.".into()
        ]);

        let report = QualityEvaluator::evaluate_document("cricket scoring", &["Introduction".into()], &doc);
        assert!(report.composite_reward <= 0.15, "Generic off-topic boilerplate must never receive high reward, got {}", report.composite_reward);
    }
}

