//! Filevo Contextual Memory & Reference Engine.
//!
//! Tracks document identities (hashes, paths, versions), conversation turns,
//! model-interpreted intent resolution, and concurrency-safe non-destructive versioning.

use filevo_docx::DocxReader;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::fs::{self, File};
use std::io::Read;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};
use thiserror::Error;

#[derive(Error, Debug)]
pub enum MemoryError {
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),
    #[error("JSON serialization error: {0}")]
    Json(#[from] serde_json::Error),
    #[error("Document error: {0}")]
    Docx(#[from] filevo_docx::DocxError),
    #[error("Document not found: {0}")]
    DocumentNotFound(String),
    #[error("Hash mismatch on {path}: expected {expected}, got {actual}")]
    HashMismatch {
        path: PathBuf,
        expected: String,
        actual: String,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum Role {
    User,
    Assistant,
    System,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocumentIdentity {
    pub id: String,
    pub file_path: PathBuf,
    pub content_hash: String,
    pub title: String,
    pub version: u32,
    pub sections: Vec<String>,
    pub created_at: u64,
}

impl DocumentIdentity {
    pub fn from_file(path: &Path, title_override: Option<String>) -> Result<Self, MemoryError> {
        if !path.exists() {
            return Err(MemoryError::DocumentNotFound(path.display().to_string()));
        }

        let hash = compute_sha256(path)?;
        let doc = DocxReader::read_from_file(path)?;
        let title = title_override.unwrap_or(doc.title);
        let sections = doc.sections.into_iter().map(|s| s.heading).collect();

        let stem = path.file_stem().and_then(|s| s.to_str()).unwrap_or("");
        let version = extract_version_from_stem(stem);

        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();

        let id = format!("{}_{}", stem, &hash[..8]);

        Ok(Self {
            id,
            file_path: path.to_path_buf(),
            content_hash: hash,
            title,
            version,
            sections,
            created_at: now,
        })
    }

    pub fn verify_integrity(&self) -> Result<(), MemoryError> {
        let current_hash = compute_sha256(&self.file_path)?;
        if current_hash != self.content_hash {
            return Err(MemoryError::HashMismatch {
                path: self.file_path.clone(),
                expected: self.content_hash.clone(),
                actual: current_hash,
            });
        }
        Ok(())
    }

    pub fn compute_next_version_path(&self) -> PathBuf {
        let parent = self.file_path.parent().unwrap_or_else(|| Path::new("."));
        let stem = self.file_path.file_stem().and_then(|s| s.to_str()).unwrap_or("document");
        let ext = self.file_path.extension().and_then(|s| s.to_str()).unwrap_or("docx");

        // Strip any existing _v[0-9]+
        let base_name = if let Some(idx) = stem.rfind("_v") {
            if stem[idx + 2..].chars().all(|c| c.is_ascii_digit()) {
                &stem[..idx]
            } else {
                stem
            }
        } else {
            stem
        };

        let mut candidate_version = self.version.max(1) + 1;
        loop {
            let candidate_filename = format!("{base_name}_v{candidate_version}.{ext}");
            let candidate_path = parent.join(candidate_filename);
            if !candidate_path.exists() {
                return candidate_path;
            }
            candidate_version += 1;
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum UserIntent {
    CreateDocument {
        topic: String,
        explicit_sections: Vec<String>,
    },
    ReviseDocument {
        target_section: Option<String>,
        instruction: String,
    },
    AskQuestion {
        query: String,
        target_document_id: Option<String>,
    },
    ChatConversation {
        message: String,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Turn {
    pub role: Role,
    pub content: String,
    pub timestamp: u64,
    pub active_document_id: Option<String>,
    pub referenced_section: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ConversationMemory {
    pub turns: Vec<Turn>,
    pub active_document: Option<DocumentIdentity>,
    pub document_history: Vec<DocumentIdentity>,
}

impl ConversationMemory {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn set_active_document(&mut self, doc: DocumentIdentity) {
        self.active_document = Some(doc.clone());
        if !self.document_history.iter().any(|d| d.id == doc.id) {
            self.document_history.push(doc);
        }
    }

    pub fn add_turn(&mut self, role: Role, content: impl Into<String>) {
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        let doc_id = self.active_document.as_ref().map(|d| d.id.clone());
        self.turns.push(Turn {
            role,
            content: content.into(),
            timestamp: now,
            active_document_id: doc_id,
            referenced_section: None,
        });
    }

    /// Disentangles Intent Resolution from Reference Resolution
    pub fn resolve_intent(&self, input: &str) -> UserIntent {
        let text = input.trim();
        let lower = text.to_lowercase();

        // 1. History Question Check (Must never be treated as document revision or creation)
        let is_query = lower.starts_with("which")
            || lower.starts_with("what")
            || lower.starts_with("how")
            || lower.starts_with("tell me")
            || lower.starts_with("did")
            || lower.starts_with("was")
            || lower.contains('?')
            || lower.contains("which hardware")
            || lower.contains("which section");

        if is_query {
            let doc_id = self.active_document.as_ref().map(|d| d.id.clone());
            return UserIntent::AskQuestion {
                query: text.to_string(),
                target_document_id: doc_id,
            };
        }

        // 2. Document Creation Check (Creation intent ALWAYS takes precedence over active doc existence)
        let creation_cues = [
            "create a", "create detailed", "create technical", "create report", "create document",
            "generate a", "generate detailed", "generate report", "write a report", "write a technical",
            "draft a", "produce a", "build a report",
        ];
        let has_creation_cue = creation_cues.iter().any(|cue| lower.contains(cue))
            || lower.starts_with("create ")
            || lower.starts_with("generate ")
            || lower.starts_with("draft ");

        if has_creation_cue || lower.contains("specifying") {
            let explicit_sections = extract_explicit_sections(text);
            let topic = extract_topic_from_creation(text);
            return UserIntent::CreateDocument {
                topic,
                explicit_sections,
            };
        }

        // 3. Revision Check (Requires active document or explicit target document reference)
        let revision_cues = [
            "make the", "make it", "expand", "elaborate", "revise", "rewrite",
            "more detailed", "add a section", "update the doc", "modify",
        ];
        let has_revision_cue = revision_cues.iter().any(|cue| lower.contains(cue));

        if self.active_document.is_some() && has_revision_cue {
            let target_section = self.extract_target_section(&lower);
            return UserIntent::ReviseDocument {
                target_section,
                instruction: text.to_string(),
            };
        }

        UserIntent::ChatConversation {
            message: text.to_string(),
        }
    }

    pub fn extract_target_section(&self, lower_input: &str) -> Option<String> {
        if let Some(ref doc) = self.active_document {
            for sec in &doc.sections {
                if lower_input.contains(&sec.to_lowercase()) {
                    return Some(sec.clone());
                }
            }
        }
        for common in ["methodology", "hardware design", "introduction", "testing", "conclusion", "architecture"] {
            if lower_input.contains(common) {
                return Some(capitalize_title(common));
            }
        }
        None
    }
}

pub fn compute_sha256(path: &Path) -> Result<String, MemoryError> {
    let mut file = File::open(path)?;
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 8192];
    loop {
        let n = file.read(&mut buffer)?;
        if n == 0 {
            break;
        }
        hasher.update(&buffer[..n]);
    }
    let res = hasher.finalize();
    Ok(format!("{:x}", res))
}

fn extract_version_from_stem(stem: &str) -> u32 {
    if let Some(idx) = stem.rfind("_v") {
        if let Ok(v) = stem[idx + 2..].parse::<u32>() {
            return v;
        }
    }
    1
}

fn extract_explicit_sections(text: &str) -> Vec<String> {
    let lower = text.to_lowercase();
    let marker = if let Some(idx) = lower.find("specifying") {
        Some(idx + 10)
    } else if let Some(idx) = lower.find("with sections") {
        Some(idx + 13)
    } else if let Some(idx) = lower.find("sections:") {
        Some(idx + 9)
    } else {
        None
    };

    let mut sections = Vec::new();
    if let Some(idx) = marker {
        let sub = &text[idx..];
        let cleaned = sub.replace(" and ", ", ");
        for part in cleaned.split(',') {
            let trimmed = part.trim().trim_matches('.');
            if !trimmed.is_empty() {
                sections.push(trimmed.to_string());
            }
        }
    }
    sections
}

fn extract_topic_from_creation(text: &str) -> String {
    let lower = text.to_lowercase();
    for prefix in ["create a ", "generate a ", "write a report on ", "draft a "] {
        if let Some(idx) = lower.find(prefix) {
            let rem = &text[idx + prefix.len()..];
            if let Some(end) = rem.to_lowercase().find(" specifying") {
                return rem[..end].trim().to_string();
            }
            return rem.trim().to_string();
        }
    }
    text.to_string()
}

fn capitalize_title(s: &str) -> String {
    s.split_whitespace()
        .map(|w| {
            let mut c = w.chars();
            match c.next() {
                None => String::new(),
                Some(f) => f.to_uppercase().collect::<String>() + c.as_str(),
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_intent_vs_reference_resolution() {
        let mut mem = ConversationMemory::new();

        // 1. Initial creation
        let intent1 = mem.resolve_intent("Create a cricket scoring report specifying Introduction, Hardware Design, Methodology, Testing and Conclusion");
        match intent1 {
            UserIntent::CreateDocument { topic, explicit_sections } => {
                assert!(topic.to_lowercase().contains("cricket scoring report"));
                assert_eq!(explicit_sections, vec!["Introduction", "Hardware Design", "Methodology", "Testing", "Conclusion"]);
            }
            _ => panic!("Expected CreateDocument intent"),
        }

        // Set active document
        let doc = DocumentIdentity {
            id: "cricket_001".into(),
            file_path: PathBuf::from("/tmp/Cricket_Scoring_Report.docx"),
            content_hash: "abcd1234efgh5678".into(),
            title: "Cricket Scoring Report".into(),
            version: 1,
            sections: vec!["Introduction".into(), "Hardware Design".into(), "Methodology".into(), "Testing".into(), "Conclusion".into()],
            created_at: 1000,
        };
        mem.set_active_document(doc);

        // 2. Contextual Revision request: "Make the methodology in that report more detailed"
        let intent2 = mem.resolve_intent("Make the methodology in that report more detailed");
        match intent2 {
            UserIntent::ReviseDocument { target_section, instruction } => {
                assert_eq!(target_section, Some("Methodology".to_string()));
                assert!(instruction.contains("more detailed"));
            }
            _ => panic!("Expected ReviseDocument intent, got {:?}", intent2),
        }

        // 3. Question about document: "Which hardware was discussed and which section was expanded?"
        let intent3 = mem.resolve_intent("Which hardware was discussed and which section was expanded?");
        match intent3 {
            UserIntent::AskQuestion { query, target_document_id } => {
                assert!(query.contains("Which hardware"));
                assert_eq!(target_document_id, Some("cricket_001".to_string()));
            }
            _ => panic!("Expected AskQuestion intent, got {:?}", intent3),
        }
    }

    #[test]
    fn test_non_destructive_monotonic_versioning() {
        use filevo_docx::{DocxDocument, DocxWriter};
        let tmp = tempfile::tempdir().unwrap();
        let file1 = tmp.path().join("Cricket_Scoring_Report.docx");
        
        let mut d1 = DocxDocument::new("Cricket Scoring Report");
        d1.add_section("Introduction", vec!["V1 intro".into()]);
        DocxWriter::write_to_file(&d1, &file1).unwrap();

        let doc1 = DocumentIdentity::from_file(&file1, Some("Cricket Scoring Report".into())).unwrap();
        assert_eq!(doc1.version, 1);

        let next_path = doc1.compute_next_version_path();
        assert_eq!(next_path.file_name().unwrap(), "Cricket_Scoring_Report_v2.docx");

        // Write v2 and check next
        let mut d2 = DocxDocument::new("Cricket Scoring Report (Version 2)");
        d2.add_section("Introduction", vec!["V2 intro".into()]);
        DocxWriter::write_to_file(&d2, &next_path).unwrap();

        let doc2 = DocumentIdentity::from_file(&next_path, Some("Cricket Scoring Report".into())).unwrap();
        assert_eq!(doc2.version, 2);

        let v3_path = doc2.compute_next_version_path();
        assert_eq!(v3_path.file_name().unwrap(), "Cricket_Scoring_Report_v3.docx");

        // Original file integrity remains intact
        doc1.verify_integrity().expect("Original file hash must remain unchanged");
    }
}
