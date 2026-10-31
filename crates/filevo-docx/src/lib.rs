//! Pure-Rust OpenXML (.docx) Engine for Filevo.
//!
//! Provides zero-C-dependency OpenXML package inspection, structural section extraction,
//! typed AST creation, targeted section revision with preservation, and ZIP package rendering.

use quick_xml::events::Event;
use quick_xml::reader::Reader;
use serde::{Deserialize, Serialize};
use std::fs::File;
use std::io::{Read, Write};
use std::path::Path;
use thiserror::Error;
use zip::write::SimpleFileOptions;
use zip::{ZipArchive, ZipWriter};

#[derive(Error, Debug)]
pub enum DocxError {
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),
    #[error("ZIP package error: {0}")]
    Zip(#[from] zip::result::ZipError),
    #[error("XML parsing error: {0}")]
    Xml(#[from] quick_xml::Error),
    #[error("Malformed OpenXML package: {0}")]
    MalformedPackage(String),
    #[error("Section not found: {0}")]
    SectionNotFound(String),
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct DocxTable {
    pub headers: Vec<String>,
    pub rows: Vec<Vec<String>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct DocxSection {
    pub heading: String,
    pub level: usize,
    pub paragraphs: Vec<String>,
    pub tables: Vec<DocxTable>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct DocxDocument {
    pub title: String,
    pub sections: Vec<DocxSection>,
}

impl DocxDocument {
    pub fn new(title: impl Into<String>) -> Self {
        Self {
            title: title.into(),
            sections: Vec::new(),
        }
    }

    pub fn add_section(&mut self, heading: impl Into<String>, paragraphs: Vec<String>) {
        self.sections.push(DocxSection {
            heading: heading.into(),
            level: 1,
            paragraphs,
            tables: Vec::new(),
        });
    }

    pub fn revise_section(
        &self,
        target_heading: &str,
        new_paragraphs: Vec<String>,
    ) -> Result<Self, DocxError> {
        let mut revised = self.clone();
        let target_lower = target_heading.trim().to_lowercase();
        let mut found = false;

        for sec in &mut revised.sections {
            let sec_lower = sec.heading.trim().to_lowercase();
            if sec_lower == target_lower || sec_lower.contains(&target_lower) || target_lower.contains(&sec_lower) {
                sec.paragraphs = new_paragraphs.clone();
                found = true;
                break;
            }
        }

        if !found {
            return Err(DocxError::SectionNotFound(target_heading.to_string()));
        }

        Ok(revised)
    }
}

pub struct DocxReader;

impl DocxReader {
    pub fn read_from_file(path: &Path) -> Result<DocxDocument, DocxError> {
        let file = File::open(path)?;
        let mut archive = ZipArchive::new(file)?;

        let mut doc_xml = String::new();
        {
            let mut doc_file = archive
                .by_name("word/document.xml")
                .map_err(|_| DocxError::MalformedPackage("word/document.xml missing".into()))?;
            doc_file.read_to_string(&mut doc_xml)?;
        }

        Self::parse_document_xml(&doc_xml, path.file_stem().and_then(|s| s.to_str()).unwrap_or("Document"))
    }

    pub fn parse_document_xml(xml: &str, fallback_title: &str) -> Result<DocxDocument, DocxError> {
        let mut reader = Reader::from_str(xml);
        reader.config_mut().trim_text(true);

        let mut doc = DocxDocument::new(fallback_title);
        let mut in_t = false;
        let mut in_tc = false;
        let mut is_heading = false;
        let mut heading_level = 1;

        let mut current_p_text = String::new();
        let mut current_sec_heading = "Overview".to_string();
        let mut current_sec_paras: Vec<String> = Vec::new();
        let mut current_tables: Vec<DocxTable> = Vec::new();

        let mut current_tbl_rows: Vec<Vec<String>> = Vec::new();
        let mut current_row_cells: Vec<String> = Vec::new();

        let mut buf = Vec::new();

        loop {
            match reader.read_event_into(&mut buf) {
                Ok(Event::Start(ref e)) => {
                    let qname = e.name();
                    let name = qname.as_ref();
                    if name == b"w:p" {
                        is_heading = false;
                        current_p_text.clear();
                    } else if name == b"w:t" {
                        in_t = true;
                    } else if name == b"w:tbl" {
                        current_tbl_rows.clear();
                    } else if name == b"w:tr" {
                        current_row_cells.clear();
                    } else if name == b"w:tc" {
                        in_tc = true;
                    } else if name == b"w:pStyle" {
                        for attr in e.attributes().flatten() {
                            if attr.key.as_ref() == b"w:val" {
                                if let Ok(val) = std::str::from_utf8(&attr.value) {
                                    let v_lower = val.to_lowercase();
                                    if v_lower.contains("heading") || v_lower == "title" {
                                        is_heading = true;
                                        if v_lower.contains('1') {
                                            heading_level = 1;
                                        } else if v_lower.contains('2') {
                                            heading_level = 2;
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                Ok(Event::Empty(ref e)) => {
                    let qname = e.name();
                    let name = qname.as_ref();
                    if name == b"w:pStyle" {
                        for attr in e.attributes().flatten() {
                            if attr.key.as_ref() == b"w:val" {
                                if let Ok(val) = std::str::from_utf8(&attr.value) {
                                    let v_lower = val.to_lowercase();
                                    if v_lower.contains("heading") || v_lower == "title" {
                                        is_heading = true;
                                        if v_lower.contains('1') {
                                            heading_level = 1;
                                        } else if v_lower.contains('2') {
                                            heading_level = 2;
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                Ok(Event::Text(ref e)) => {
                    if in_t {
                        if let Ok(txt) = e.unescape() {
                            current_p_text.push_str(&txt);
                        }
                    }
                }
                Ok(Event::End(ref e)) => {
                    let qname = e.name();
                    let name = qname.as_ref();
                    if name == b"w:t" {
                        in_t = false;
                    } else if name == b"w:p" {
                        let text = current_p_text.trim().to_string();
                        if !text.is_empty() {
                            if is_heading {
                                if !current_sec_paras.is_empty() || !current_tables.is_empty() {
                                    doc.sections.push(DocxSection {
                                        heading: current_sec_heading.clone(),
                                        level: heading_level,
                                        paragraphs: current_sec_paras.clone(),
                                        tables: current_tables.clone(),
                                    });
                                    current_sec_paras.clear();
                                    current_tables.clear();
                                }
                                current_sec_heading = text;
                            } else if in_tc {
                                current_row_cells.push(text);
                            } else {
                                current_sec_paras.push(text);
                            }
                        }
                    } else if name == b"w:tc" {
                        in_tc = false;
                    } else if name == b"w:tr" {
                        if !current_row_cells.is_empty() {
                            current_tbl_rows.push(current_row_cells.clone());
                            current_row_cells.clear();
                        }
                    } else if name == b"w:tbl" {
                        if !current_tbl_rows.is_empty() {
                            let headers = current_tbl_rows[0].clone();
                            let rows = if current_tbl_rows.len() > 1 {
                                current_tbl_rows[1..].to_vec()
                            } else {
                                Vec::new()
                            };
                            current_tables.push(DocxTable { headers, rows });
                            current_tbl_rows.clear();
                        }
                    }
                }
                Ok(Event::Eof) => break,
                Err(e) => return Err(DocxError::Xml(e)),
                _ => {}
            }
            buf.clear();
        }

        if !current_sec_paras.is_empty() || !current_tables.is_empty() {
            doc.sections.push(DocxSection {
                heading: current_sec_heading,
                level: heading_level,
                paragraphs: current_sec_paras,
                tables: current_tables,
            });
        }

        Ok(doc)
    }
}

pub struct DocxWriter;

impl DocxWriter {
    pub fn write_to_file(doc: &DocxDocument, path: &Path) -> Result<(), DocxError> {
        let file = File::create(path)?;
        let mut zip = ZipWriter::new(file);
        let options = SimpleFileOptions::default()
            .compression_method(zip::CompressionMethod::Deflated);

        // 1. [Content_Types].xml
        zip.start_file("[Content_Types].xml", options)?;
        zip.write_all(CONTENT_TYPES_XML.as_bytes())?;

        // 2. _rels/.rels
        zip.start_file("_rels/.rels", options)?;
        zip.write_all(RELS_XML.as_bytes())?;

        // 3. word/_rels/document.xml.rels
        zip.start_file("word/_rels/document.xml.rels", options)?;
        zip.write_all(DOCUMENT_RELS_XML.as_bytes())?;

        // 4. word/styles.xml
        zip.start_file("word/styles.xml", options)?;
        zip.write_all(STYLES_XML.as_bytes())?;

        // 5. word/document.xml
        zip.start_file("word/document.xml", options)?;
        let body_xml = Self::render_document_xml(doc);
        zip.write_all(body_xml.as_bytes())?;

        zip.finish()?;
        Ok(())
    }

    fn render_document_xml(doc: &DocxDocument) -> String {
        let mut xml = String::with_capacity(16_384);
        xml.push_str(r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>"#);
        xml.push_str(r#"<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">"#);
        xml.push_str(r#"<w:body>"#);

        // Document Title
        xml.push_str(r#"<w:p><w:pPr><w:pStyle w:val="Title"/><w:jc w:val="center"/></w:pPr>"#);
        xml.push_str(r#"<w:r><w:rPr><w:b/><w:sz w:val="48"/><w:color w:val="1E293B"/></w:rPr>"#);
        xml.push_str(&format!(r#"<w:t>{}</w:t></w:r></w:p>"#, escape_xml(&doc.title)));

        // Sections
        for sec in &doc.sections {
            let style_val = if sec.level == 2 { "Heading2" } else { "Heading1" };
            let color_val = if sec.level == 2 { "334155" } else { "0F172A" };
            let size_val = if sec.level == 2 { "28" } else { "32" };

            xml.push_str(&format!(
                r#"<w:p><w:pPr><w:pStyle w:val="{style_val}"/><w:spacing w:before="240" w:after="120"/></w:pPr>"#
            ));
            xml.push_str(&format!(
                r#"<w:r><w:rPr><w:b/><w:sz w:val="{size_val}"/><w:color w:val="{color_val}"/></w:rPr>"#
            ));
            xml.push_str(&format!(r#"<w:t>{}</w:t></w:r></w:p>"#, escape_xml(&sec.heading)));

            for p in &sec.paragraphs {
                xml.push_str(r#"<w:p><w:pPr><w:spacing w:after="140" w:line="276" w:lineRule="auto"/></w:pPr>"#);
                xml.push_str(r#"<w:r><w:rPr><w:sz w:val="22"/><w:color w:val="334155"/></w:rPr>"#);
                xml.push_str(&format!(r#"<w:t>{}</w:t></w:r></w:p>"#, escape_xml(p)));
            }

            for tbl in &sec.tables {
                xml.push_str(r#"<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/><w:tblBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/><w:bottom w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/><w:insideH w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/></w:tblBorders></w:tblPr>"#);
                if !tbl.headers.is_empty() {
                    xml.push_str(r#"<w:tr><w:trPr><w:tblHeader/></w:trPr>"#);
                    for h in &tbl.headers {
                        xml.push_str(r#"<w:tc><w:tcPr><w:shd w:val="clear" w:color="auto" w:fill="F1F5F9"/></w:tcPr>"#);
                        xml.push_str(r#"<w:p><w:r><w:rPr><w:b/><w:sz w:val="20"/><w:color w:val="0F172A"/></w:rPr>"#);
                        xml.push_str(&format!(r#"<w:t>{}</w:t></w:r></w:p></w:tc>"#, escape_xml(h)));
                    }
                    xml.push_str(r#"</w:tr>"#);
                }
                for row in &tbl.rows {
                    xml.push_str(r#"<w:tr>"#);
                    for cell in row {
                        xml.push_str(r#"<w:tc><w:p><w:r><w:rPr><w:sz w:val="20"/><w:color w:val="334155"/></w:rPr>"#);
                        xml.push_str(&format!(r#"<w:t>{}</w:t></w:r></w:p></w:tc>"#, escape_xml(cell)));
                    }
                    xml.push_str(r#"</w:tr>"#);
                }
                xml.push_str(r#"</w:tbl>"#);
            }
        }

        xml.push_str(r#"<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>"#);
        xml.push_str(r#"</w:body></w:document>"#);
        xml
    }
}

pub fn validate_docx_package(path: &Path) -> Result<(), DocxError> {
    let file = File::open(path)?;
    let mut archive = ZipArchive::new(file)?;

    let required = [
        "[Content_Types].xml",
        "_rels/.rels",
        "word/document.xml",
    ];
    for r in required {
        archive.by_name(r).map_err(|_| {
            DocxError::MalformedPackage(format!("Required package part missing: {r}"))
        })?;
    }

    let mut doc_xml = String::new();
    {
        let mut entry = archive.by_name("word/document.xml")?;
        entry.read_to_string(&mut doc_xml)?;
    }

    let mut reader = Reader::from_str(&doc_xml);
    let mut buf = Vec::new();
    loop {
        match reader.read_event_into(&mut buf) {
            Ok(Event::Eof) => break,
            Err(e) => return Err(DocxError::Xml(e)),
            _ => {}
        }
        buf.clear();
    }

    Ok(())
}

fn escape_xml(input: &str) -> String {
    input
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

const CONTENT_TYPES_XML: &str = r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"#;

const RELS_XML: &str = r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"#;

const DOCUMENT_RELS_XML: &str = r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"#;

const STYLES_XML: &str = r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/><w:color w:val="334155"/></w:rPr></w:rPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:rPr><w:b/><w:sz w:val="48"/><w:color w:val="1E293B"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:rPr><w:b/><w:sz w:val="32"/><w:color w:val="0F172A"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:rPr><w:b/><w:sz w:val="28"/><w:color w:val="334155"/></w:rPr></w:style>
</w:styles>"#;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_create_and_validate_docx() {
        let mut doc = DocxDocument::new("Cricket Scoring Report");
        doc.add_section("Introduction", vec!["This report introduces the IoT cricket scoring telemetry.".into()]);
        doc.add_section("Hardware Design", vec!["Microcontroller ESP32 connected to high-resolution optical gate sensors.".into()]);
        doc.add_section("Methodology", vec!["Baseline ball tracking pipeline using finite state machines.".into()]);
        doc.add_section("Testing", vec!["Endurance test results across 50 overs with zero dropped ball frames.".into()]);
        doc.add_section("Conclusion", vec!["The system achieves targeted latency and operational reliability.".into()]);

        let tmp = tempfile::NamedTempFile::new().unwrap();
        let path = tmp.path().to_path_buf();
        DocxWriter::write_to_file(&doc, &path).expect("Write docx must succeed");

        validate_docx_package(&path).expect("DOCX package must pass OpenXML validation");

        let read_doc = DocxReader::read_from_file(&path).expect("Read docx must succeed");
        assert_eq!(read_doc.sections.len(), 5);
        assert_eq!(read_doc.sections[0].heading, "Introduction");
        assert_eq!(read_doc.sections[1].heading, "Hardware Design");
        assert_eq!(read_doc.sections[2].heading, "Methodology");
        assert_eq!(read_doc.sections[3].heading, "Testing");
        assert_eq!(read_doc.sections[4].heading, "Conclusion");
    }

    #[test]
    fn test_targeted_section_revision_preserves_untargeted_sections() {
        let mut doc = DocxDocument::new("Cricket Scoring Report");
        doc.add_section("Introduction", vec!["Intro text".into()]);
        doc.add_section("Hardware Design", vec!["Hardware verbatim text".into()]);
        doc.add_section("Methodology", vec!["Brief methodology".into()]);
        doc.add_section("Conclusion", vec!["Conclusion text".into()]);

        let revised = doc
            .revise_section(
                "Methodology",
                vec![
                    "Expanded methodology paragraph 1 with rigorous statistical sampling.".into(),
                    "Expanded methodology paragraph 2 with calibration matrices.".into(),
                ],
            )
            .expect("Revision of Methodology must succeed");

        assert_eq!(revised.sections[0].paragraphs, vec!["Intro text"]);
        assert_eq!(revised.sections[1].paragraphs, vec!["Hardware verbatim text"]);
        assert_eq!(revised.sections[3].paragraphs, vec!["Conclusion text"]);

        assert_eq!(revised.sections[2].paragraphs.len(), 2);
        assert!(revised.sections[2].paragraphs[0].contains("Expanded methodology"));
    }

    #[test]
    fn test_inspect_baseline_corpus_fixtures() {
        let corpus_path = Path::new("../../tests/fixtures/docx_corpus/cricket_scoring_report.docx");
        if corpus_path.exists() {
            let doc = DocxReader::read_from_file(corpus_path).expect("Reading baseline corpus fixture must succeed");
            assert!(!doc.sections.is_empty());
            println!("Corpus fixture sections: {:?}", doc.sections.iter().map(|s| &s.heading).collect::<Vec<_>>());
        }
    }
}
