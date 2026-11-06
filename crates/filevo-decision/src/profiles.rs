//! Baseline Design Profiles for coherent document foundations.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum DesignProfile {
    AcademicMonograph,
    TechnicalReport,
    ExecutiveSummary,
    MinimalistModern,
    ResearchPublication,
}

impl DesignProfile {
    pub fn from_topic_and_genre(topic: &str, genre: &str) -> Self {
        let combined = format!("{} {}", topic, genre).to_lowercase();

        if combined.contains("monograph") || combined.contains("academic") || combined.contains("treatise") || combined.contains("history") {
            Self::AcademicMonograph
        } else if combined.contains("executive") || combined.contains("brief") || combined.contains("strategy") || combined.contains("strategic") {
            Self::ExecutiveSummary
        } else if combined.contains("research") || combined.contains("journal") || combined.contains("paper") {
            Self::ResearchPublication
        } else if combined.contains("minimal") || combined.contains("essay") {
            Self::MinimalistModern
        } else {
            Self::TechnicalReport
        }
    }

    pub fn baseline_decisions(&self) -> HashMap<String, String> {
        let mut d = HashMap::new();
        match self {
            Self::AcademicMonograph => {
                d.insert("page_geometry:paper_size".into(), "Letter".into());
                d.insert("page_geometry:orientation".into(), "Portrait".into());
                d.insert("page_geometry:margins".into(), "Standard".into());
                d.insert("page_geometry:column_count".into(), "1".into());
                d.insert("typography:body_font".into(), "Georgia".into());
                d.insert("typography:heading_font".into(), "Georgia".into());
                d.insert("typography:code_font".into(), "Consolas".into());
                d.insert("typography:body_size".into(), "12pt".into());
                d.insert("typography:line_spacing".into(), "1.15".into());
                d.insert("paragraphs:alignment".into(), "Justified".into());
                d.insert("headings:h1_size".into(), "16pt".into());
                d.insert("headings:h2_size".into(), "14pt".into());
                d.insert("visual:primary_accent".into(), "1F4E79".into());
                d.insert("tables:border_style".into(), "HorizontalRulesOnly".into());
            }
            Self::TechnicalReport => {
                d.insert("page_geometry:paper_size".into(), "Letter".into());
                d.insert("page_geometry:orientation".into(), "Portrait".into());
                d.insert("page_geometry:margins".into(), "Compact".into());
                d.insert("page_geometry:column_count".into(), "1".into());
                d.insert("typography:body_font".into(), "Aptos".into());
                d.insert("typography:heading_font".into(), "Aptos Display".into());
                d.insert("typography:code_font".into(), "Consolas".into());
                d.insert("typography:body_size".into(), "11pt".into());
                d.insert("typography:line_spacing".into(), "1.15".into());
                d.insert("paragraphs:alignment".into(), "Left".into());
                d.insert("headings:h1_size".into(), "16pt".into());
                d.insert("headings:h2_size".into(), "14pt".into());
                d.insert("visual:primary_accent".into(), "2E75B6".into());
                d.insert("tables:border_style".into(), "HorizontalRulesOnly".into());
            }
            Self::ExecutiveSummary => {
                d.insert("page_geometry:paper_size".into(), "Letter".into());
                d.insert("page_geometry:orientation".into(), "Portrait".into());
                d.insert("page_geometry:margins".into(), "Standard".into());
                d.insert("page_geometry:column_count".into(), "1".into());
                d.insert("typography:body_font".into(), "Calibri".into());
                d.insert("typography:heading_font".into(), "Aptos Display".into());
                d.insert("typography:code_font".into(), "Consolas".into());
                d.insert("typography:body_size".into(), "11pt".into());
                d.insert("typography:line_spacing".into(), "1.15".into());
                d.insert("paragraphs:alignment".into(), "Left".into());
                d.insert("headings:h1_size".into(), "18pt".into());
                d.insert("headings:h2_size".into(), "14pt".into());
                d.insert("visual:primary_accent".into(), "1F4E79".into());
                d.insert("tables:border_style".into(), "MinimalGrid".into());
            }
            Self::MinimalistModern => {
                d.insert("page_geometry:paper_size".into(), "A4".into());
                d.insert("page_geometry:orientation".into(), "Portrait".into());
                d.insert("page_geometry:margins".into(), "Standard".into());
                d.insert("page_geometry:column_count".into(), "1".into());
                d.insert("typography:body_font".into(), "Aptos".into());
                d.insert("typography:heading_font".into(), "Aptos Display".into());
                d.insert("typography:code_font".into(), "Consolas".into());
                d.insert("typography:body_size".into(), "11pt".into());
                d.insert("typography:line_spacing".into(), "1.15".into());
                d.insert("paragraphs:alignment".into(), "Left".into());
                d.insert("headings:h1_size".into(), "16pt".into());
                d.insert("headings:h2_size".into(), "13pt".into());
                d.insert("visual:primary_accent".into(), "333333".into());
                d.insert("tables:border_style".into(), "HorizontalRulesOnly".into());
            }
            Self::ResearchPublication => {
                d.insert("page_geometry:paper_size".into(), "Letter".into());
                d.insert("page_geometry:orientation".into(), "Portrait".into());
                d.insert("page_geometry:margins".into(), "Standard".into());
                d.insert("page_geometry:column_count".into(), "1".into());
                d.insert("typography:body_font".into(), "Times New Roman".into());
                d.insert("typography:heading_font".into(), "Georgia".into());
                d.insert("typography:code_font".into(), "Consolas".into());
                d.insert("typography:body_size".into(), "12pt".into());
                d.insert("typography:line_spacing".into(), "1.15".into());
                d.insert("paragraphs:alignment".into(), "Justified".into());
                d.insert("headings:h1_size".into(), "16pt".into());
                d.insert("headings:h2_size".into(), "14pt".into());
                d.insert("visual:primary_accent".into(), "1F4E79".into());
                d.insert("tables:border_style".into(), "HorizontalRulesOnly".into());
            }
        }
        d
    }
}
