//! Comprehensive OpenXML DOCX Package Validator.
//!
//! Validates:
//! - Package archive structure and required parts.
//! - XML well-formedness of all XML and .rels parts.
//! - Relationship targets exist in archive.
//! - Content Types declaration consistency.
//! - Internal cross-references: numbering numIds, bookmarks, footnotes, header/footer relationship IDs.

use quick_xml::events::Event;
use quick_xml::reader::Reader;
use std::collections::{HashMap, HashSet};
use std::fs::File;
use std::io::Read;
use std::path::Path;
use thiserror::Error;
use zip::ZipArchive;

#[derive(Error, Debug)]
pub enum ValidationError {
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),
    #[error("ZIP package error: {0}")]
    Zip(#[from] zip::result::ZipError),
    #[error("XML parsing error in {part}: {source}")]
    Xml {
        part: String,
        source: quick_xml::Error,
    },
    #[error("Required package part missing: {0}")]
    MissingRequiredPart(String),
    #[error("Relationship target missing in package: rel_id={rel_id}, target={target}, source_part={source_part}")]
    MissingRelationshipTarget {
        source_part: String,
        rel_id: String,
        target: String,
    },
    #[error("Content type mismatch: {0}")]
    ContentTypeMismatch(String),
    #[error("Invalid numbering reference: numId={0} in document.xml does not exist in numbering.xml")]
    MissingNumberingId(u32),
    #[error("Mismatched bookmark: bookmarkEnd id={0} has no matching bookmarkStart")]
    MismatchedBookmarkEnd(usize),
    #[error("Unclosed bookmark: bookmarkStart id={0} has no matching bookmarkEnd")]
    UnclosedBookmarkStart(usize),
    #[error("Invalid footnote reference: id={0} in document.xml does not exist in footnotes.xml")]
    MissingFootnoteId(usize),
    #[error("Invalid header/footer relationship reference: r:id={rel_id} not found in document.xml.rels")]
    MissingHeaderFooterRel { rel_id: String },
}

#[derive(Debug, Default)]
pub struct ValidationSummary {
    pub total_parts_checked: usize,
    pub xml_parts_verified: usize,
    pub relationships_verified: usize,
    pub overrides_verified: usize,
    pub numbering_ids_verified: usize,
    pub bookmarks_verified: usize,
    pub footnotes_verified: usize,
}

pub struct DocxValidator;

impl DocxValidator {
    pub fn validate_package(path: &Path) -> Result<ValidationSummary, ValidationError> {
        let file = File::open(path)?;
        let mut archive = ZipArchive::new(file)?;
        let mut summary = ValidationSummary::default();

        // 1. Mandatory Core Parts
        let required_parts = [
            "[Content_Types].xml",
            "_rels/.rels",
            "word/document.xml",
            "word/_rels/document.xml.rels",
            "word/styles.xml",
        ];

        for req in required_parts {
            archive.by_name(req).map_err(|_| {
                ValidationError::MissingRequiredPart(req.to_string())
            })?;
        }

        // 2. Collect all part names in archive
        let mut part_names: HashSet<String> = HashSet::new();
        for i in 0..archive.len() {
            let file = archive.by_index(i)?;
            let name = file.name().to_string();
            part_names.insert(name);
        }
        summary.total_parts_checked = part_names.len();

        // 3. Verify XML Well-Formedness across ALL .xml and .rels files
        for part in &part_names {
            if part.ends_with(".xml") || part.ends_with(".rels") {
                let mut content = String::new();
                let mut entry = archive.by_name(part)?;
                entry.read_to_string(&mut content)?;

                let mut reader = Reader::from_str(&content);
                reader.config_mut().trim_text(false);

                // Verify XML has no undeclared entities (only standard XML entities or numeric references)
                let mut search_from = 0;
                while let Some(amp_pos) = content[search_from..].find('&') {
                    let actual_pos = search_from + amp_pos;
                    if let Some(semi_pos) = content[actual_pos..].find(';') {
                        if semi_pos <= 10 {
                            let entity = &content[actual_pos + 1..actual_pos + semi_pos];
                            if !matches!(entity, "amp" | "lt" | "gt" | "quot" | "apos") && !entity.starts_with('#') {
                                return Err(ValidationError::Xml {
                                    part: part.clone(),
                                    source: quick_xml::Error::Io(std::io::Error::new(
                                        std::io::ErrorKind::InvalidData,
                                        format!("Undeclared XML entity '&{};' at byte {}", entity, actual_pos),
                                    ).into()),
                                });
                            }
                        }
                        search_from = actual_pos + semi_pos + 1;
                    } else {
                        search_from = actual_pos + 1;
                    }
                }

                let mut buf = Vec::new();
                loop {
                    match reader.read_event_into(&mut buf) {
                        Ok(Event::Eof) => break,
                        Err(e) => {
                            return Err(ValidationError::Xml {
                                part: part.clone(),
                                source: e,
                            });
                        }
                        _ => {}
                    }
                    buf.clear();
                }
                summary.xml_parts_verified += 1;
            }
        }

        // 4. Verify Content Types Declarations
        let mut declared_overrides: HashSet<String> = HashSet::new();
        let mut default_extensions: HashSet<String> = HashSet::new();
        {
            let mut ct_xml = String::new();
            archive.by_name("[Content_Types].xml")?.read_to_string(&mut ct_xml)?;

            let mut reader = Reader::from_str(&ct_xml);
            let mut buf = Vec::new();
            loop {
                match reader.read_event_into(&mut buf) {
                    Ok(Event::Eof) => break,
                    Ok(Event::Empty(ref e)) | Ok(Event::Start(ref e)) => {
                        let qname = e.name();
                        if qname.as_ref() == b"Override" {
                            for attr in e.attributes().flatten() {
                                if attr.key.as_ref() == b"PartName" {
                                    if let Ok(val) = std::str::from_utf8(&attr.value) {
                                        let clean_part = val.trim_start_matches('/');
                                        declared_overrides.insert(clean_part.to_string());
                                    }
                                }
                            }
                        } else if qname.as_ref() == b"Default" {
                            for attr in e.attributes().flatten() {
                                if attr.key.as_ref() == b"Extension" {
                                    if let Ok(val) = std::str::from_utf8(&attr.value) {
                                        default_extensions.insert(val.to_string());
                                    }
                                }
                            }
                        }
                    }
                    Err(e) => {
                        return Err(ValidationError::Xml {
                            part: "[Content_Types].xml".into(),
                            source: e,
                        });
                    }
                    _ => {}
                }
                buf.clear();
            }

            // Every declared override must exist in the archive
            for ov in &declared_overrides {
                if !part_names.contains(ov) {
                    return Err(ValidationError::ContentTypeMismatch(format!(
                        "Override PartName '/{}' declared in [Content_Types].xml does not exist in package",
                        ov
                    )));
                }
                summary.overrides_verified += 1;
            }

            // Every file in the archive must be covered by either a default extension or an override
            for part in &part_names {
                if part == "[Content_Types].xml" {
                    continue;
                }
                let ext = if let Some(idx) = part.rfind('.') {
                    &part[idx + 1..]
                } else {
                    ""
                };
                if !default_extensions.contains(ext) && !declared_overrides.contains(part) {
                    return Err(ValidationError::ContentTypeMismatch(format!(
                        "Part '{}' is not covered by any Default extension or Override in [Content_Types].xml",
                        part
                    )));
                }
            }
        }

        // 5. Verify Relationships and Target Existence
        let mut document_rels: HashMap<String, String> = HashMap::new();
        {
            // Root relationships: _rels/.rels
            let mut root_rels = String::new();
            archive.by_name("_rels/.rels")?.read_to_string(&mut root_rels)?;
            Self::verify_relationships(&root_rels, "_rels/.rels", "", &part_names, &mut HashMap::new(), &mut summary)?;

            // Document relationships: word/_rels/document.xml.rels
            let mut doc_rels = String::new();
            archive.by_name("word/_rels/document.xml.rels")?.read_to_string(&mut doc_rels)?;
            Self::verify_relationships(&doc_rels, "word/_rels/document.xml.rels", "word", &part_names, &mut document_rels, &mut summary)?;
        }

        // 6. Verify Numbering Cross-References
        let mut valid_num_ids: HashSet<u32> = HashSet::new();
        if part_names.contains("word/numbering.xml") {
            let mut num_xml = String::new();
            archive.by_name("word/numbering.xml")?.read_to_string(&mut num_xml)?;
            let mut reader = Reader::from_str(&num_xml);
            let mut buf = Vec::new();
            loop {
                match reader.read_event_into(&mut buf) {
                    Ok(Event::Eof) => break,
                    Ok(Event::Start(ref e)) | Ok(Event::Empty(ref e)) => {
                        if e.name().as_ref() == b"w:num" {
                            for attr in e.attributes().flatten() {
                                if attr.key.as_ref() == b"w:numId" {
                                    if let Ok(val) = std::str::from_utf8(&attr.value) {
                                        if let Ok(nid) = val.parse::<u32>() {
                                            valid_num_ids.insert(nid);
                                        }
                                    }
                                }
                            }
                        }
                    }
                    _ => {}
                }
                buf.clear();
            }
        }

        // 7. Verify Footnotes in word/footnotes.xml if present
        let mut valid_footnote_ids: HashSet<usize> = HashSet::new();
        if part_names.contains("word/footnotes.xml") {
            let mut fn_xml = String::new();
            archive.by_name("word/footnotes.xml")?.read_to_string(&mut fn_xml)?;
            let mut reader = Reader::from_str(&fn_xml);
            let mut buf = Vec::new();
            loop {
                match reader.read_event_into(&mut buf) {
                    Ok(Event::Eof) => break,
                    Ok(Event::Start(ref e)) | Ok(Event::Empty(ref e)) => {
                        if e.name().as_ref() == b"w:footnote" {
                            for attr in e.attributes().flatten() {
                                if attr.key.as_ref() == b"w:id" {
                                    if let Ok(val) = std::str::from_utf8(&attr.value) {
                                        if let Ok(id) = val.parse::<usize>() {
                                            valid_footnote_ids.insert(id);
                                        }
                                    }
                                }
                            }
                        }
                    }
                    _ => {}
                }
                buf.clear();
            }
        }

        // 8. Inspect word/document.xml for cross-references
        {
            let mut doc_xml = String::new();
            archive.by_name("word/document.xml")?.read_to_string(&mut doc_xml)?;

            let mut reader = Reader::from_str(&doc_xml);
            let mut buf = Vec::new();
            let mut bookmark_starts: HashSet<usize> = HashSet::new();
            let mut bookmark_ends: HashSet<usize> = HashSet::new();

            loop {
                match reader.read_event_into(&mut buf) {
                    Ok(Event::Eof) => break,
                    Ok(Event::Empty(ref e)) | Ok(Event::Start(ref e)) => {
                        let name = e.name();
                        if name.as_ref() == b"w:numId" {
                            for attr in e.attributes().flatten() {
                                if attr.key.as_ref() == b"w:val" {
                                    if let Ok(val) = std::str::from_utf8(&attr.value) {
                                        if let Ok(nid) = val.parse::<u32>() {
                                            if !valid_num_ids.contains(&nid) {
                                                return Err(ValidationError::MissingNumberingId(nid));
                                            }
                                            summary.numbering_ids_verified += 1;
                                        }
                                    }
                                }
                            }
                        } else if name.as_ref() == b"w:bookmarkStart" {
                            for attr in e.attributes().flatten() {
                                if attr.key.as_ref() == b"w:id" {
                                    if let Ok(val) = std::str::from_utf8(&attr.value) {
                                        if let Ok(bid) = val.parse::<usize>() {
                                            bookmark_starts.insert(bid);
                                        }
                                    }
                                }
                            }
                        } else if name.as_ref() == b"w:bookmarkEnd" {
                            for attr in e.attributes().flatten() {
                                if attr.key.as_ref() == b"w:id" {
                                    if let Ok(val) = std::str::from_utf8(&attr.value) {
                                        if let Ok(bid) = val.parse::<usize>() {
                                            if !bookmark_starts.contains(&bid) {
                                                return Err(ValidationError::MismatchedBookmarkEnd(bid));
                                            }
                                            bookmark_ends.insert(bid);
                                            summary.bookmarks_verified += 1;
                                        }
                                    }
                                }
                            }
                        } else if name.as_ref() == b"w:footnoteReference" {
                            for attr in e.attributes().flatten() {
                                if attr.key.as_ref() == b"w:id" {
                                    if let Ok(val) = std::str::from_utf8(&attr.value) {
                                        if let Ok(fid) = val.parse::<usize>() {
                                            if !valid_footnote_ids.contains(&fid) {
                                                return Err(ValidationError::MissingFootnoteId(fid));
                                            }
                                            summary.footnotes_verified += 1;
                                        }
                                    }
                                }
                            }
                        } else if name.as_ref() == b"w:headerReference" || name.as_ref() == b"w:footerReference" {
                            for attr in e.attributes().flatten() {
                                if attr.key.as_ref() == b"r:id" {
                                    if let Ok(val) = std::str::from_utf8(&attr.value) {
                                        if !document_rels.contains_key(val) {
                                            return Err(ValidationError::MissingHeaderFooterRel {
                                                rel_id: val.to_string(),
                                            });
                                        }
                                    }
                                }
                            }
                        } else if name.as_ref() == b"a:blip" {
                            for attr in e.attributes().flatten() {
                                if attr.key.as_ref() == b"r:embed" {
                                    if let Ok(val) = std::str::from_utf8(&attr.value) {
                                        if let Some(target) = document_rels.get(val) {
                                            let full_target = if target.starts_with('/') {
                                                target.trim_start_matches('/').to_string()
                                            } else {
                                                format!("word/{target}")
                                            };
                                            if !part_names.contains(&full_target) {
                                                return Err(ValidationError::MissingRelationshipTarget {
                                                    source_part: "word/document.xml".into(),
                                                    rel_id: val.to_string(),
                                                    target: full_target,
                                                });
                                            }
                                        } else {
                                            return Err(ValidationError::MissingRelationshipTarget {
                                                source_part: "word/document.xml".into(),
                                                rel_id: val.to_string(),
                                                target: "undeclared relationship".into(),
                                            });
                                        }
                                    }
                                }
                            }
                        }
                    }
                    Err(e) => {
                        return Err(ValidationError::Xml {
                            part: "word/document.xml".into(),
                            source: e,
                        });
                    }
                    _ => {}
                }
                buf.clear();
            }

            // Verify all bookmark starts have a matching end
            for bid in bookmark_starts {
                if !bookmark_ends.contains(&bid) {
                    return Err(ValidationError::UnclosedBookmarkStart(bid));
                }
            }
        }

        Ok(summary)
    }

    fn verify_relationships(
        rels_xml: &str,
        part_name: &str,
        base_dir: &str,
        part_names: &HashSet<String>,
        collected_rels: &mut HashMap<String, String>,
        summary: &mut ValidationSummary,
    ) -> Result<(), ValidationError> {
        let mut reader = Reader::from_str(rels_xml);
        let mut buf = Vec::new();

        loop {
            match reader.read_event_into(&mut buf) {
                Ok(Event::Eof) => break,
                Ok(Event::Empty(ref e)) | Ok(Event::Start(ref e)) => {
                    if e.name().as_ref() == b"Relationship" {
                        let mut rel_id = String::new();
                        let mut target = String::new();
                        let mut target_mode = String::new();

                        for attr in e.attributes().flatten() {
                            match attr.key.as_ref() {
                                b"Id" => {
                                    if let Ok(v) = std::str::from_utf8(&attr.value) {
                                        rel_id = v.to_string();
                                    }
                                }
                                b"Target" => {
                                    if let Ok(v) = std::str::from_utf8(&attr.value) {
                                        target = v.to_string();
                                    }
                                }
                                b"TargetMode" => {
                                    if let Ok(v) = std::str::from_utf8(&attr.value) {
                                        target_mode = v.to_string();
                                    }
                                }
                                _ => {}
                            }
                        }

                        if !rel_id.is_empty() && !target.is_empty() {
                            collected_rels.insert(rel_id.clone(), target.clone());

                            if target_mode != "External"
                                && !target.starts_with("http://")
                                && !target.starts_with("https://")
                                && !target.starts_with("mailto:")
                            {
                                let resolved_target = if base_dir.is_empty() {
                                    target.trim_start_matches('/').to_string()
                                } else {
                                    format!("{}/{}", base_dir, target.trim_start_matches('/'))
                                };

                                if !part_names.contains(&resolved_target) {
                                    return Err(ValidationError::MissingRelationshipTarget {
                                        source_part: part_name.to_string(),
                                        rel_id,
                                        target: resolved_target,
                                    });
                                }
                                summary.relationships_verified += 1;
                            }
                        }
                    }
                }
                Err(e) => {
                    return Err(ValidationError::Xml {
                        part: part_name.to_string(),
                        source: e,
                    });
                }
                _ => {}
            }
            buf.clear();
        }

        Ok(())
    }
}
