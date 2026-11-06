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

pub mod validator;
pub use validator::{DocxValidator, ValidationError, ValidationSummary};

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
        let mut is_title = false;
        let mut is_toc = false;
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
                        is_title = false;
                        is_toc = false;
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
                                    if v_lower == "title" {
                                        is_title = true;
                                    } else if v_lower.contains("toc") {
                                        is_toc = true;
                                    } else if v_lower.contains("heading") {
                                        is_heading = true;
                                        heading_level = 1;
                                        for lvl in 1..=6 {
                                            if v_lower.contains(&lvl.to_string()) {
                                                heading_level = lvl;
                                                break;
                                            }
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
                                    if v_lower == "title" {
                                        is_title = true;
                                    } else if v_lower.contains("toc") {
                                        is_toc = true;
                                    } else if v_lower.contains("heading") {
                                        is_heading = true;
                                        heading_level = 1;
                                        for lvl in 1..=6 {
                                            if v_lower.contains(&lvl.to_string()) {
                                                heading_level = lvl;
                                                break;
                                            }
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
                            if is_title {
                                doc.title = text;
                            } else if is_toc {
                                // Skip TOC structural elements from polluting body sections
                            } else if is_heading {
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

    /// Renders a complete DOCX package by combining content (DocumentAST) with presentation (DocumentSpec).
    pub fn render_package(
        ast: &filevo_spec::DocumentAST,
        spec: &filevo_spec::DocumentSpec,
        path: &Path,
    ) -> Result<(), DocxError> {
        let file = File::create(path)?;
        let mut zip = ZipWriter::new(file);
        let options = SimpleFileOptions::default()
            .compression_method(zip::CompressionMethod::Deflated);

        let images = Self::collect_images(ast);

        // 1. [Content_Types].xml
        zip.start_file("[Content_Types].xml", options)?;
        zip.write_all(Self::render_content_types_xml(spec).as_bytes())?;

        // 2. _rels/.rels
        zip.start_file("_rels/.rels", options)?;
        zip.write_all(Self::render_root_rels_xml().as_bytes())?;

        // 3. docProps/core.xml & docProps/app.xml
        zip.start_file("docProps/core.xml", options)?;
        zip.write_all(Self::render_core_props_xml(ast).as_bytes())?;

        zip.start_file("docProps/app.xml", options)?;
        zip.write_all(Self::render_app_props_xml().as_bytes())?;

        // 4. word/_rels/document.xml.rels
        zip.start_file("word/_rels/document.xml.rels", options)?;
        zip.write_all(Self::render_document_rels_xml(spec, images.len()).as_bytes())?;

        // 4b. word/media/image{i}.png
        for (idx, img) in images.iter().enumerate() {
            let img_num = idx + 1;
            let (path_str, data_opt) = match img {
                filevo_spec::BlockAST::Image { path, data, .. } => (path.as_str(), data.as_ref()),
                _ => continue,
            };

            let bytes = if let Some(d) = data_opt {
                d.clone()
            } else if Path::new(path_str).exists() {
                std::fs::read(path_str).unwrap_or_else(|_| Self::generate_default_figure_png(800, 480))
            } else {
                Self::generate_default_figure_png(800, 480)
            };

            let media_path = format!("word/media/image{img_num}.png");
            zip.start_file(&media_path, options)?;
            zip.write_all(&bytes)?;
        }

        // 5. word/settings.xml (enables dynamic TOC, PAGE, NUMPAGES evaluation)
        zip.start_file("word/settings.xml", options)?;
        zip.write_all(Self::render_settings_xml().as_bytes())?;

        // 6. word/numbering.xml
        zip.start_file("word/numbering.xml", options)?;
        zip.write_all(Self::render_numbering_xml().as_bytes())?;

        // 7. word/footnotes.xml & word/endnotes.xml
        let footnotes = Self::collect_footnotes(ast);
        zip.start_file("word/footnotes.xml", options)?;
        zip.write_all(Self::render_footnotes_xml(&footnotes).as_bytes())?;

        zip.start_file("word/endnotes.xml", options)?;
        zip.write_all(Self::render_endnotes_xml().as_bytes())?;

        // 8. word/header1.xml & word/footer1.xml (if headers/footers enabled)
        if spec.headers_footers.include_page_numbers || !spec.headers_footers.header_right_text.is_empty() {
            zip.start_file("word/header1.xml", options)?;
            zip.write_all(Self::render_header_xml(ast, spec).as_bytes())?;

            zip.start_file("word/footer1.xml", options)?;
            zip.write_all(Self::render_footer_xml(ast, spec).as_bytes())?;
        }

        // 9. word/styles.xml (dynamically generated from DocumentSpec)
        zip.start_file("word/styles.xml", options)?;
        let styles_xml = Self::render_styles_xml(spec);
        zip.write_all(styles_xml.as_bytes())?;

        // 10. word/document.xml (dynamically generated from AST + Spec)
        zip.start_file("word/document.xml", options)?;
        let body_xml = Self::render_document_xml_from_spec(ast, spec);
        zip.write_all(body_xml.as_bytes())?;

        zip.finish()?;
        Ok(())
    }

    fn render_content_types_xml(spec: &filevo_spec::DocumentSpec) -> String {
        let has_hf = spec.headers_footers.include_page_numbers || !spec.headers_footers.header_right_text.is_empty();
        let mut xml = String::from(r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Default Extension="jpeg" ContentType="image/jpeg"/>
  <Default Extension="jpg" ContentType="image/jpeg"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
  <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
  <Override PartName="/word/footnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/>
  <Override PartName="/word/endnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.endnotes+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>"#);
        if has_hf {
            xml.push_str(r#"
  <Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>
  <Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>"#);
        }
        xml.push_str("\n</Types>");
        xml
    }

    fn render_root_rels_xml() -> String {
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"#.to_string()
    }

    fn render_document_rels_xml(spec: &filevo_spec::DocumentSpec, images_count: usize) -> String {
        let has_hf = spec.headers_footers.include_page_numbers || !spec.headers_footers.header_right_text.is_empty();
        let mut xml = String::from(r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
  <Relationship Id="rIdSettings" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>
  <Relationship Id="rIdFootnotes" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes" Target="footnotes.xml"/>
  <Relationship Id="rIdEndnotes" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/endnotes" Target="endnotes.xml"/>"#);
        if has_hf {
            xml.push_str(r#"
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>
  <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>"#);
        }
        for i in 1..=images_count {
            xml.push_str(&format!(
                r#"
  <Relationship Id="rIdImg{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image{i}.png"/>"#,
                i = i
            ));
        }
        xml.push_str("\n</Relationships>");
        xml
    }

    fn collect_images(ast: &filevo_spec::DocumentAST) -> Vec<filevo_spec::BlockAST> {
        let mut images = Vec::new();
        fn walk_sections(sections: &[filevo_spec::SectionAST], images: &mut Vec<filevo_spec::BlockAST>) {
            for s in sections {
                for b in &s.blocks {
                    if matches!(b, filevo_spec::BlockAST::Image { .. }) {
                        images.push(b.clone());
                    }
                }
                walk_sections(&s.subsections, images);
            }
        }
        walk_sections(&ast.sections, &mut images);
        images
    }

    fn write_png_chunk(png: &mut Vec<u8>, tag: &[u8; 4], data: &[u8]) {
        let len = data.len() as u32;
        png.extend_from_slice(&len.to_be_bytes());
        png.extend_from_slice(tag);
        png.extend_from_slice(data);

        let mut hasher = crc32fast::Hasher::new();
        hasher.update(tag);
        hasher.update(data);
        let crc = hasher.finalize();
        png.extend_from_slice(&crc.to_be_bytes());
    }

    fn generate_default_figure_png(width: u32, height: u32) -> Vec<u8> {
        use flate2::write::ZlibEncoder;
        use flate2::Compression;
        use std::io::Write;

        let w = width as usize;
        let h = height as usize;
        let mut raw_scanlines = Vec::with_capacity(h * (w * 3 + 1));

        for y in 0..h {
            raw_scanlines.push(0);
            for x in 0..w {
                let is_border = x < 2 || x >= w - 2 || y < 2 || y >= h - 2;
                let is_top_accent = y >= 2 && y < 10 && x >= 2 && x < w - 2;
                let is_grid = (x % 40 == 0) || (y % 40 == 0);

                if is_border {
                    raw_scanlines.extend_from_slice(&[203, 213, 225]);
                } else if is_top_accent {
                    raw_scanlines.extend_from_slice(&[31, 78, 121]);
                } else if is_grid {
                    raw_scanlines.extend_from_slice(&[241, 245, 249]);
                } else {
                    raw_scanlines.extend_from_slice(&[248, 250, 252]);
                }
            }
        }

        let mut encoder = ZlibEncoder::new(Vec::new(), Compression::default());
        encoder.write_all(&raw_scanlines).unwrap();
        let compressed_idat = encoder.finish().unwrap();

        let mut png = Vec::new();
        png.extend_from_slice(&[0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]);

        // IHDR
        let mut ihdr_data = Vec::new();
        ihdr_data.extend_from_slice(&width.to_be_bytes());
        ihdr_data.extend_from_slice(&height.to_be_bytes());
        ihdr_data.extend_from_slice(&[8, 2, 0, 0, 0]);
        Self::write_png_chunk(&mut png, b"IHDR", &ihdr_data);

        // IDAT
        Self::write_png_chunk(&mut png, b"IDAT", &compressed_idat);

        // IEND
        Self::write_png_chunk(&mut png, b"IEND", &[]);

        png
    }

    fn render_core_props_xml(ast: &filevo_spec::DocumentAST) -> String {
        format!(
            r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{}</dc:title>
  <dc:creator>Filevo Composition Engine</dc:creator>
  <cp:lastModifiedBy>Filevo</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">2026-11-01T00:00:00Z</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">2026-11-01T00:00:00Z</dcterms:modified>
</cp:coreProperties>"#,
            escape_xml(&ast.title)
        )
    }

    fn render_app_props_xml() -> String {
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Filevo</Application>
  <DocSecurity>0</DocSecurity>
  <ScaleCrop>false</ScaleCrop>
  <Company>Filevo Systems</Company>
  <LinksUpToDate>false</LinksUpToDate>
  <SharedDoc>false</SharedDoc>
  <HyperlinksChanged>false</HyperlinksChanged>
  <AppVersion>1.0.0</AppVersion>
</Properties>"#.to_string()
    }

    fn render_settings_xml() -> String {
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:zoom w:percent="100"/>
  <w:defaultTabStop w:val="720"/>
  <w:evenAndOddHeaders w:val="false"/>
  <w:updateFields w:val="true"/>
</w:settings>"#.to_string()
    }

    fn collect_footnotes(ast: &filevo_spec::DocumentAST) -> Vec<(usize, String)> {
        let mut footnotes = Vec::new();
        let mut seen = std::collections::HashSet::new();

        for fn_item in &ast.footnotes {
            if seen.insert(fn_item.id) {
                footnotes.push((fn_item.id, fn_item.text.clone()));
            }
        }

        fn walk_sections(sections: &[filevo_spec::SectionAST], seen: &mut std::collections::HashSet<usize>, footnotes: &mut Vec<(usize, String)>) {
            for s in sections {
                for b in &s.blocks {
                    if let filevo_spec::BlockAST::Footnote { index, text } = b {
                        if seen.insert(*index) {
                            footnotes.push((*index, text.clone()));
                        }
                    }
                }
                walk_sections(&s.subsections, seen, footnotes);
            }
        }

        walk_sections(&ast.sections, &mut seen, &mut footnotes);
        footnotes.sort_by_key(|(id, _)| *id);
        footnotes
    }

    fn render_footnotes_xml(footnotes: &[(usize, String)]) -> String {
        let mut xml = String::from(r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:footnote w:type="separator" w:id="-1">
    <w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr><w:r><w:separator/></w:r></w:p>
  </w:footnote>
  <w:footnote w:type="continuationSeparator" w:id="0">
    <w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr><w:r><w:continuationSeparator/></w:r></w:p>
  </w:footnote>"#);

        for (id, text) in footnotes {
            xml.push_str(&format!(
                r#"
  <w:footnote w:id="{id}">
    <w:p>
      <w:pPr><w:pStyle w:val="FootnoteText"/><w:spacing w:after="60"/></w:pPr>
      <w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr><w:footnoteRef/></w:r>
      <w:r><w:rPr><w:sz w:val="18"/><w:color w:val="475569"/></w:rPr><w:t xml:space="preserve"> {text}</w:t></w:r>
    </w:p>
  </w:footnote>"#,
                id = id,
                text = escape_xml(text),
            ));
        }

        xml.push_str("\n</w:footnotes>");
        xml
    }

    fn render_endnotes_xml() -> String {
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:endnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:endnote w:type="separator" w:id="-1">
    <w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr><w:r><w:separator/></w:r></w:p>
  </w:endnote>
  <w:endnote w:type="continuationSeparator" w:id="0">
    <w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr><w:r><w:continuationSeparator/></w:r></w:p>
  </w:endnote>
</w:endnotes>"#.to_string()
    }

    fn render_numbering_xml() -> String {
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:abstractNum w:abstractNumId="0">
    <w:multiLevelType w:val="hybridMultilevel"/>
    <w:lvl w:ilvl="0">
      <w:start w:val="1"/>
      <w:numFmt w:val="bullet"/>
      <w:lvlText w:val="•"/>
      <w:lvlJc w:val="left"/>
      <w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr>
      <w:rPr><w:rFonts w:ascii="Symbol" w:hAnsi="Symbol" w:hint="default"/></w:rPr>
    </w:lvl>
    <w:lvl w:ilvl="1">
      <w:start w:val="1"/>
      <w:numFmt w:val="bullet"/>
      <w:lvlText w:val="–"/>
      <w:lvlJc w:val="left"/>
      <w:pPr><w:ind w:left="1440" w:hanging="360"/></w:pPr>
    </w:lvl>
    <w:lvl w:ilvl="2">
      <w:start w:val="1"/>
      <w:numFmt w:val="bullet"/>
      <w:lvlText w:val="▪"/>
      <w:lvlJc w:val="left"/>
      <w:pPr><w:ind w:left="2160" w:hanging="360"/></w:pPr>
    </w:lvl>
  </w:abstractNum>
  <w:abstractNum w:abstractNumId="1">
    <w:multiLevelType w:val="hybridMultilevel"/>
    <w:lvl w:ilvl="0">
      <w:start w:val="1"/>
      <w:numFmt w:val="decimal"/>
      <w:lvlText w:val="%1."/>
      <w:lvlJc w:val="left"/>
      <w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr>
    </w:lvl>
    <w:lvl w:ilvl="1">
      <w:start w:val="1"/>
      <w:numFmt w:val="lowerLetter"/>
      <w:lvlText w:val="%2."/>
      <w:lvlJc w:val="left"/>
      <w:pPr><w:ind w:left="1440" w:hanging="360"/></w:pPr>
    </w:lvl>
    <w:lvl w:ilvl="2">
      <w:start w:val="1"/>
      <w:numFmt w:val="lowerRoman"/>
      <w:lvlText w:val="%3."/>
      <w:lvlJc w:val="left"/>
      <w:pPr><w:ind w:left="2160" w:hanging="360"/></w:pPr>
    </w:lvl>
  </w:abstractNum>
  <w:num w:numId="1">
    <w:abstractNumId w:val="0"/>
  </w:num>
  <w:num w:numId="2">
    <w:abstractNumId w:val="1"/>
  </w:num>
</w:numbering>"#.to_string()
    }

    fn render_header_xml(ast: &filevo_spec::DocumentAST, spec: &filevo_spec::DocumentSpec) -> String {
        let text = if !spec.headers_footers.header_right_text.is_empty() {
            spec.headers_footers.header_right_text.clone()
        } else {
            ast.title.clone()
        };

        format!(
            r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:p>
    <w:pPr>
      <w:pStyle w:val="Header"/>
      <w:jc w:val="right"/>
      <w:spacing w:after="120"/>
    </w:pPr>
    <w:r>
      <w:rPr>
        <w:rFonts w:ascii="{font}" w:hAnsi="{font}"/>
        <w:sz w:val="18"/>
        <w:color w:val="64748B"/>
      </w:rPr>
      <w:t>{}</w:t>
    </w:r>
  </w:p>
</w:hdr>"#,
            escape_xml(&text),
            font = escape_xml(&spec.typography.body_font)
        )
    }

    fn render_footer_xml(ast: &filevo_spec::DocumentAST, spec: &filevo_spec::DocumentSpec) -> String {
        let left_text = if !spec.headers_footers.footer_left_text.is_empty() {
            spec.headers_footers.footer_left_text.clone()
        } else {
            ast.title.clone()
        };
        let page_num_xml = if spec.headers_footers.include_page_numbers {
            r#"<w:r><w:rPr><w:sz w:val="18"/><w:color w:val="64748B"/></w:rPr><w:t xml:space="preserve"> | Page </w:t></w:r><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:rPr><w:sz w:val="18"/><w:color w:val="64748B"/></w:rPr><w:t>1</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r><w:r><w:rPr><w:sz w:val="18"/><w:color w:val="64748B"/></w:rPr><w:t xml:space="preserve"> of </w:t></w:r><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> NUMPAGES </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:rPr><w:sz w:val="18"/><w:color w:val="64748B"/></w:rPr><w:t>1</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>"#
        } else {
            ""
        };

        format!(
            r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:p>
    <w:pPr>
      <w:pStyle w:val="Footer"/>
      <w:jc w:val="center"/>
      <w:spacing w:before="120"/>
    </w:pPr>
    <w:r>
      <w:rPr>
        <w:rFonts w:ascii="{font}" w:hAnsi="{font}"/>
        <w:sz w:val="18"/>
        <w:color w:val="64748B"/>
      </w:rPr>
      <w:t>{}</w:t>
    </w:r>
    {page_num_xml}
  </w:p>
</w:ftr>"#,
            escape_xml(&left_text),
            font = escape_xml(&spec.typography.body_font),
            page_num_xml = page_num_xml
        )
    }

    fn render_styles_xml(spec: &filevo_spec::DocumentSpec) -> String {
        let mut xml = String::with_capacity(8192);
        xml.push_str(r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault><w:rPr><w:rFonts w:ascii=""#);
        xml.push_str(&escape_xml(&spec.typography.body_font));
        xml.push_str(r#"" w:hAnsi=""#);
        xml.push_str(&escape_xml(&spec.typography.body_font));
        xml.push_str(&format!(r#""/><w:sz w:val="{}"/><w:color w:val=""#, spec.typography.body_size_half_points));
        xml.push_str(&escape_xml(&spec.typography.font_color));
        xml.push_str(r#""/></w:rPr></w:rPrDefault>
  </w:docDefaults>
"#);

        // Title style
        xml.push_str(&format!(
            r#"  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:rPr><w:rFonts w:ascii="{heading_font}" w:hAnsi="{heading_font}"/><w:b/><w:sz w:val="{title_sz}"/><w:color w:val="{title_color}"/></w:rPr></w:style>
"#,
            heading_font = escape_xml(&spec.typography.heading_font),
            title_sz = spec.headings.title_size_half_points,
            title_color = escape_xml(&spec.visual.neutral_dark),
        ));

        // Subtitle style
        xml.push_str(&format!(
            r#"  <w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:rPr><w:rFonts w:ascii="{heading_font}" w:hAnsi="{heading_font}"/><w:i/><w:sz w:val="24"/><w:color w:val="{sub_color}"/></w:rPr></w:style>
"#,
            heading_font = escape_xml(&spec.typography.heading_font),
            sub_color = escape_xml(&spec.visual.secondary_accent),
        ));

        for i in 1..=6 {
            let (color, sz) = if let Some(style) = spec.headings.style_for_level(i) {
                (style.color.as_str(), style.size_half_points)
            } else if i == 1 {
                (spec.headings.h1_color.as_str(), spec.headings.h1_size_half_points)
            } else if i == 2 {
                (spec.headings.h2_color.as_str(), spec.headings.h2_size_half_points)
            } else {
                (spec.headings.h2_color.as_str(), spec.headings.h2_size_half_points.saturating_sub((i as u32 - 2) * 2))
            };
            xml.push_str(&format!(
                r#"  <w:style w:type="paragraph" w:styleId="Heading{i}"><w:name w:val="heading {i}"/><w:pPr><w:keepNext/><w:widowControl/></w:pPr><w:rPr><w:rFonts w:ascii="{font}" w:hAnsi="{font}"/><w:b/><w:sz w:val="{sz}"/><w:color w:val="{color}"/></w:rPr></w:style>
"#,
                i = i,
                font = escape_xml(&spec.typography.heading_font),
                sz = sz,
                color = escape_xml(color),
            ));
        }

        // Code and Quote styles
        xml.push_str(&format!(
            r#"  <w:style w:type="paragraph" w:styleId="CodeBlock"><w:name w:val="Code Block"/><w:rPr><w:rFonts w:ascii="{code_font}" w:hAnsi="{code_font}"/><w:sz w:val="19"/><w:color w:val="1E293B"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="BlockQuote"><w:name w:val="Block Quote"/><w:rPr><w:rFonts w:ascii="{body_font}" w:hAnsi="{body_font}"/><w:i/><w:sz w:val="{body_sz}"/><w:color w:val="475569"/></w:rPr></w:style>
"#,
            code_font = escape_xml(&spec.typography.code_font),
            body_font = escape_xml(&spec.typography.body_font),
            body_sz = spec.typography.body_size_half_points,
        ));

        // Header and Footer styles
        xml.push_str(r#"  <w:style w:type="paragraph" w:styleId="Header"><w:name w:val="header"/><w:rPr><w:sz w:val="18"/><w:color w:val="64748B"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Footer"><w:name w:val="footer"/><w:rPr><w:sz w:val="18"/><w:color w:val="64748B"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="FootnoteText"><w:name w:val="footnote text"/><w:rPr><w:sz w:val="18"/><w:color w:val="475569"/></w:rPr></w:style>
  <w:style w:type="character" w:styleId="FootnoteReference"><w:name w:val="footnote reference"/><w:rPr><w:vertAlign w:val="superscript"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="EndnoteText"><w:name w:val="endnote text"/><w:rPr><w:sz w:val="18"/><w:color w:val="475569"/></w:rPr></w:style>
  <w:style w:type="character" w:styleId="EndnoteReference"><w:name w:val="endnote reference"/><w:rPr><w:vertAlign w:val="superscript"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="TOCHeading"><w:name w:val="TOC Heading"/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/></w:pPr><w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="TOC1"><w:name w:val="toc 1"/><w:pPr><w:spacing w:after="80"/><w:tabs><w:tab w:val="right" w:leader="dot" w:pos="9360"/></w:tabs></w:pPr><w:rPr><w:sz w:val="22"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="TOC2"><w:name w:val="toc 2"/><w:pPr><w:spacing w:after="60"/><w:ind w:left="288"/><w:tabs><w:tab w:val="right" w:leader="dot" w:pos="9360"/></w:tabs></w:pPr><w:rPr><w:sz w:val="20"/></w:rPr></w:style>
</w:styles>"#);

        xml
    }

    fn render_document_xml_from_spec(
        ast: &filevo_spec::DocumentAST,
        spec: &filevo_spec::DocumentSpec,
    ) -> String {
        let mut xml = String::with_capacity(32_768);
        xml.push_str(r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>"#);
        xml.push_str(r#"<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">"#);
        xml.push_str(r#"<w:body>"#);

        // Document Title
        xml.push_str(r#"<w:p><w:pPr><w:pStyle w:val="Title"/><w:jc w:val="center"/></w:pPr>"#);
        xml.push_str(&format!(
            r#"<w:r><w:rPr><w:b/><w:sz w:val="{}"/><w:color w:val="{}"/></w:rPr>"#,
            spec.headings.title_size_half_points,
            escape_xml(&spec.visual.neutral_dark)
        ));
        xml.push_str(&format!(r#"<w:t>{}</w:t></w:r></w:p>"#, escape_xml(&ast.title)));

        // Optional Subtitle
        if let Some(ref sub) = ast.subtitle {
            xml.push_str(r#"<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:after="240"/></w:pPr>"#);
            xml.push_str(&format!(
                r#"<w:r><w:rPr><w:i/><w:sz w:val="24"/><w:color w:val="{}"/></w:rPr><w:t>{}</w:t></w:r></w:p>"#,
                escape_xml(&spec.visual.secondary_accent),
                escape_xml(sub)
            ));
        }

        // Table of Contents if navigation spec calls for it
        if spec.navigation.include_toc {
            xml.push_str(r#"<w:p><w:pPr><w:pStyle w:val="TOCHeading"/><w:spacing w:before="240" w:after="120"/></w:pPr><w:r><w:rPr><w:b/><w:sz w:val="28"/><w:color w:val=""#);
            xml.push_str(&escape_xml(&spec.headings.h1_color));
            xml.push_str(r#""/></w:rPr><w:t>Table of Contents</w:t></w:r></w:p>"#);
            xml.push_str(r#"<w:p><w:pPr><w:pStyle w:val="TOC"/></w:pPr><w:fldSimple w:instr="TOC \o &quot;1-3&quot; \h \z \u"/></w:p>"#);
        }

        let align_val = match spec.paragraphs.alignment.as_str() {
            "Justified" => "both",
            "Center" => "center",
            _ => "left",
        };

        // Render Sections recursively to handle AST subsections
        let mut bookmark_id: usize = 1;
        let mut img_counter: usize = 0;
        Self::render_sections_ast(&ast.sections, spec, &mut xml, &mut bookmark_id, &mut img_counter, align_val);

        // References Section if AST contains references
        if !ast.references.is_empty() {
            xml.push_str(&format!(
                r#"<w:p><w:pPr><w:pStyle w:val="Heading1"/><w:keepNext/><w:spacing w:before="360" w:after="120"/></w:pPr><w:r><w:rPr><w:b/><w:sz w:val="{sz}"/><w:color w:val="{col}"/></w:rPr><w:t>References &amp; Literature Cited</w:t></w:r></w:p>"#,
                sz = spec.headings.h1_size_half_points,
                col = escape_xml(&spec.headings.h1_color),
            ));
            for ref_item in &ast.references {
                xml.push_str(r#"<w:p><w:pPr><w:ind w:left="360" w:hanging="360"/><w:spacing w:after="80"/></w:pPr>"#);
                xml.push_str(&format!(
                    r#"<w:r><w:rPr><w:sz w:val="20"/><w:color w:val="334155"/></w:rPr><w:t>• {}: {}</w:t></w:r></w:p>"#,
                    escape_xml(&ref_item.title),
                    escape_xml(&ref_item.url),
                ));
            }
        }

        // Bibliography if present in AST
        if !ast.bibliography.is_empty() {
            xml.push_str(&format!(
                r#"<w:p><w:pPr><w:pStyle w:val="Heading1"/><w:keepNext/><w:spacing w:before="360" w:after="120"/></w:pPr><w:r><w:rPr><w:b/><w:sz w:val="{sz}"/><w:color w:val="{col}"/></w:rPr><w:t>Bibliography</w:t></w:r></w:p>"#,
                sz = spec.headings.h1_size_half_points,
                col = escape_xml(&spec.headings.h1_color),
            ));
            for bib in &ast.bibliography {
                xml.push_str(r#"<w:p><w:pPr><w:ind w:left="360" w:hanging="360"/><w:spacing w:after="80"/></w:pPr>"#);
                xml.push_str(&format!(
                    r#"<w:r><w:rPr><w:b/><w:sz w:val="20"/></w:rPr><w:t>[{}] </w:t></w:r><w:r><w:rPr><w:sz w:val="20"/><w:color w:val="334155"/></w:rPr><w:t>{}</w:t></w:r></w:p>"#,
                    escape_xml(&bib.id),
                    escape_xml(&bib.citation)
                ));
            }
        }

        // Page Geometry Section Properties (with Header/Footer references and Orientation)
        let has_hf = spec.headers_footers.include_page_numbers || !spec.headers_footers.header_right_text.is_empty();
        let orient_attr = if spec.geometry.orientation == filevo_spec::PageOrientation::Landscape {
            r#" w:orient="landscape""#
        } else {
            ""
        };
        let diff_first_xml = if spec.headers_footers.different_first_page {
            r#"<w:titlePg/>"#
        } else {
            ""
        };
        let hf_refs_xml = if has_hf {
            r#"<w:headerReference w:type="default" r:id="rId3"/><w:footerReference w:type="default" r:id="rId4"/>"#
        } else {
            ""
        };

        xml.push_str(&format!(
            r#"<w:sectPr>{hf_refs_xml}{diff_first_xml}<w:pgSz w:w="{width}" w:h="{height}"{orient_attr}/><w:pgMar w:top="{top}" w:right="{right}" w:bottom="{bottom}" w:left="{left}"/></w:sectPr>"#,
            hf_refs_xml = hf_refs_xml,
            diff_first_xml = diff_first_xml,
            width = spec.geometry.width_twips,
            height = spec.geometry.height_twips,
            orient_attr = orient_attr,
            top = spec.geometry.top_margin_twips,
            right = spec.geometry.right_margin_twips,
            bottom = spec.geometry.bottom_margin_twips,
            left = spec.geometry.left_margin_twips,
        ));

        xml.push_str(r#"</w:body></w:document>"#);
        xml
    }

    fn render_sections_ast(
        sections: &[filevo_spec::SectionAST],
        spec: &filevo_spec::DocumentSpec,
        xml: &mut String,
        bookmark_id: &mut usize,
        img_counter: &mut usize,
        align_val: &str,
    ) {
        for sec in sections {
            let level = sec.level.clamp(1, 6);
            let style_val = format!("Heading{}", level);
            let (color_val, size_val, keep_next) = if let Some(style) = spec.headings.style_for_level(level) {
                (style.color.as_str(), style.size_half_points, style.keep_with_next)
            } else if level == 1 {
                (spec.headings.h1_color.as_str(), spec.headings.h1_size_half_points, true)
            } else if level == 2 {
                (spec.headings.h2_color.as_str(), spec.headings.h2_size_half_points, true)
            } else {
                (spec.headings.h2_color.as_str(), spec.headings.h2_size_half_points.saturating_sub((level as u32 - 2) * 2), true)
            };

            let page_break_attr = if sec.page_break_before { r#"<w:pageBreakBefore/>"# } else { "" };
            let keep_next_xml = if keep_next { r#"<w:keepNext/>"# } else { "" };
            let b_id = *bookmark_id;
            *bookmark_id += 1;
            let bm_name = format!("_TocSection_{}", b_id);

            xml.push_str(&format!(
                r#"<w:p><w:pPr><w:pStyle w:val="{style_val}"/>{keep_next_xml}<w:spacing w:before="{before}" w:after="{after}"/>{page_break_attr}</w:pPr><w:bookmarkStart w:id="{b_id}" w:name="{bm_name}"/><w:r><w:rPr><w:b/><w:sz w:val="{size_val}"/><w:color w:val="{color_val}"/></w:rPr><w:t>{}</w:t></w:r><w:bookmarkEnd w:id="{b_id}"/></w:p>"#,
                escape_xml(&sec.heading),
                style_val = style_val,
                keep_next_xml = keep_next_xml,
                before = spec.headings.h1_spacing_before_twips,
                after = spec.headings.h1_spacing_after_twips,
                page_break_attr = page_break_attr,
                b_id = b_id,
                bm_name = bm_name,
                size_val = size_val,
                color_val = color_val,
            ));

            for block in &sec.blocks {
                Self::render_block_ast(block, spec, xml, img_counter, align_val);
            }

            // Recurse into subsections
            if !sec.subsections.is_empty() {
                Self::render_sections_ast(&sec.subsections, spec, xml, bookmark_id, img_counter, align_val);
            }
        }
    }

    fn render_block_ast(
        block: &filevo_spec::BlockAST,
        spec: &filevo_spec::DocumentSpec,
        xml: &mut String,
        img_counter: &mut usize,
        align_val: &str,
    ) {
        match block {
            filevo_spec::BlockAST::Paragraph { text, is_bluf } => {
                let indent_xml = if spec.paragraphs.first_line_indent_twips > 0 {
                    format!(r#"<w:ind w:firstLine="{}"/>"#, spec.paragraphs.first_line_indent_twips)
                } else {
                    String::new()
                };

                let widow_xml = if spec.paragraphs.widow_orphan_control {
                    r#"<w:widowControl/>"#
                } else {
                    ""
                };

                xml.push_str(&format!(
                    r#"<w:p><w:pPr><w:jc w:val="{align_val}"/>{widow_xml}<w:spacing w:after="{after}" w:line="{line_twips}" w:lineRule="auto"/>{indent_xml}</w:pPr>"#,
                    align_val = align_val,
                    widow_xml = widow_xml,
                    after = spec.paragraphs.space_after_twips,
                    line_twips = spec.typography.line_spacing_twips,
                    indent_xml = indent_xml,
                ));

                if *is_bluf {
                    xml.push_str(&format!(
                        r#"<w:r><w:rPr><w:b/><w:sz w:val="{sz}"/><w:color w:val="{col}"/></w:rPr><w:t>BLUF: </w:t></w:r>"#,
                        sz = spec.typography.body_size_half_points,
                        col = escape_xml(&spec.visual.primary_accent),
                    ));
                }

                xml.push_str(&format!(
                    r#"<w:r><w:rPr><w:sz w:val="{sz}"/><w:color w:val="{col}"/></w:rPr><w:t>{}</w:t></w:r></w:p>"#,
                    escape_xml(text),
                    sz = spec.typography.body_size_half_points,
                    col = escape_xml(&spec.typography.font_color),
                ));
            }
            filevo_spec::BlockAST::List { items, ordered } => {
                let num_id = if *ordered { 2 } else { 1 };
                for item in items {
                    xml.push_str(&format!(
                        r#"<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num_id}"/></w:numPr><w:spacing w:after="80"/></w:pPr><w:r><w:rPr><w:sz w:val="{sz}"/><w:color w:val="{col}"/></w:rPr><w:t>{}</w:t></w:r></w:p>"#,
                        escape_xml(item),
                        num_id = num_id,
                        sz = spec.typography.body_size_half_points,
                        col = escape_xml(&spec.typography.font_color),
                    ));
                }
            }
            filevo_spec::BlockAST::NestedList { items, ordered } => {
                let default_num_id = if *ordered { 2 } else { 1 };
                for item in items {
                    xml.push_str(&format!(
                        r#"<w:p><w:pPr><w:numPr><w:ilvl w:val="{lvl}"/><w:numId w:val="{num_id}"/></w:numPr><w:spacing w:after="80"/></w:pPr><w:r><w:rPr><w:sz w:val="{sz}"/><w:color w:val="{col}"/></w:rPr><w:t>{}</w:t></w:r></w:p>"#,
                        escape_xml(&item.text),
                        lvl = item.level,
                        num_id = default_num_id,
                        sz = spec.typography.body_size_half_points,
                        col = escape_xml(&spec.typography.font_color),
                    ));
                }
            }
            filevo_spec::BlockAST::Table { headers, rows, caption } => {
                let borders_xml = if spec.tables.border_style_enum == filevo_spec::TableBorderStyle::HorizontalRulesOnly {
                    format!(
                        r#"<w:top w:val="single" w:sz="8" w:space="0" w:color="{col}"/><w:bottom w:val="single" w:sz="8" w:space="0" w:color="{col}"/><w:insideH w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/><w:left w:val="none"/><w:right w:val="none"/><w:insideV w:val="none"/>"#,
                        col = escape_xml(&spec.tables.border_color)
                    )
                } else {
                    format!(
                        r#"<w:top w:val="single" w:sz="4" w:space="0" w:color="{col}"/><w:bottom w:val="single" w:sz="4" w:space="0" w:color="{col}"/><w:left w:val="single" w:sz="4" w:space="0" w:color="{col}"/><w:right w:val="single" w:sz="4" w:space="0" w:color="{col}"/><w:insideH w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/><w:insideV w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>"#,
                        col = escape_xml(&spec.tables.border_color)
                    )
                };

                let cell_mar_xml = format!(
                    r#"<w:tblCellMar><w:top w:w="{pad_top}" w:type="dxa"/><w:bottom w:w="{pad_bot}" w:type="dxa"/><w:left w:w="{pad_left}" w:type="dxa"/><w:right w:w="{pad_right}" w:type="dxa"/></w:tblCellMar>"#,
                    pad_top = spec.tables.cell_padding_top_twips,
                    pad_bot = spec.tables.cell_padding_bottom_twips,
                    pad_left = spec.tables.cell_padding_left_twips,
                    pad_right = spec.tables.cell_padding_right_twips,
                );

                xml.push_str(&format!(
                    r#"<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/><w:tblBorders>{}</w:tblBorders>{}</w:tblPr>"#,
                    borders_xml,
                    cell_mar_xml
                ));

                let cant_split_xml = if spec.tables.cant_split { "<w:cantSplit/>" } else { "" };

                if !headers.is_empty() {
                    let repeat_hdr = if spec.tables.repeat_header_row { "<w:tblHeader/>" } else { "" };
                    xml.push_str(&format!(r#"<w:tr><w:trPr>{repeat_hdr}{cant_split_xml}</w:trPr>"#));
                    for h in headers {
                        xml.push_str(&format!(
                            r#"<w:tc><w:tcPr><w:shd w:val="clear" w:color="auto" w:fill="{fill}"/></w:tcPr><w:p><w:pPr><w:spacing w:before="80" w:after="80"/></w:pPr><w:r><w:rPr><w:b/><w:sz w:val="20"/><w:color w:val="{col}"/></w:rPr><w:t>{}</w:t></w:r></w:p></w:tc>"#,
                            escape_xml(h),
                            fill = escape_xml(&spec.tables.header_fill_color),
                            col = escape_xml(&spec.visual.neutral_dark),
                        ));
                    }
                    xml.push_str(r#"</w:tr>"#);
                }

                for (r_idx, row) in rows.iter().enumerate() {
                    let zebra_fill = if spec.tables.zebra_shading && r_idx % 2 == 1 {
                        format!(r#"<w:shd w:val="clear" w:color="auto" w:fill="{}"/>"#, escape_xml(&spec.tables.zebra_fill_color))
                    } else {
                        String::new()
                    };

                    xml.push_str(&format!(r#"<w:tr><w:trPr>{cant_split_xml}</w:trPr>"#));
                    for cell in row {
                        xml.push_str(&format!(
                            r#"<w:tc><w:tcPr>{zebra_fill}</w:tcPr><w:p><w:pPr><w:spacing w:before="60" w:after="60"/></w:pPr><w:r><w:rPr><w:sz w:val="20"/><w:color w:val="{col}"/></w:rPr><w:t>{}</w:t></w:r></w:p></w:tc>"#,
                            escape_xml(cell),
                            col = escape_xml(&spec.typography.font_color),
                        ));
                    }
                    xml.push_str(r#"</w:tr>"#);
                }
                xml.push_str(r#"</w:tbl>"#);

                if let Some(cap) = caption {
                    xml.push_str(r#"<w:p><w:pPr><w:spacing w:before="60" w:after="140"/></w:pPr>"#);
                    xml.push_str(&format!(
                        r#"<w:r><w:rPr><w:i/><w:sz w:val="18"/><w:color w:val="{col}"/></w:rPr><w:t>Table: {}</w:t></w:r></w:p>"#,
                        escape_xml(cap),
                        col = escape_xml(&spec.visual.secondary_accent),
                    ));
                }
            }
            filevo_spec::BlockAST::Image { caption, source, alt_text, width_inches, .. } => {
                *img_counter += 1;
                let img_id = *img_counter;
                let r_id = format!("rIdImg{img_id}");
                let cx = (*width_inches * 914400.0) as u64;
                let cy = ((*width_inches * 0.6) * 914400.0) as u64;
                let alt = alt_text.as_deref().or(caption.as_deref()).unwrap_or("Figure illustration");
                let img_name = format!("image{img_id}.png");

                xml.push_str(&format!(
                    r#"<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:before="180" w:after="80"/></w:pPr><w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/><wp:effectExtent l="0" t="0" r="0" b="0"/><wp:docPr id="{img_id}" name="{img_name}" descr="{alt_escaped}"/><wp:cNvGraphicFramePr><a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/></wp:cNvGraphicFramePr><a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:nvPicPr><pic:cNvPr id="{img_id}" name="{img_name}" descr="{alt_escaped}"/><pic:cNvPicPr><a:picLocks noChangeAspect="1" noChangeArrowheads="1"/></pic:cNvPicPr></pic:nvPicPr><pic:blipFill><a:blip r:embed="{r_id}" cstate="print"/><a:srcRect/><a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr bwMode="auto"><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>"#,
                    cx = cx,
                    cy = cy,
                    img_id = img_id,
                    img_name = img_name,
                    alt_escaped = escape_xml(alt),
                    r_id = r_id,
                ));

                if let Some(cap) = caption {
                    let src_suffix = if let Some(s) = source { format!(" [{}]", s) } else { String::new() };
                    xml.push_str(r#"<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:before="40" w:after="160"/></w:pPr>"#);
                    xml.push_str(&format!(
                        r#"<w:r><w:rPr><w:i/><w:sz w:val="18"/><w:color w:val="{col}"/></w:rPr><w:t>Figure {img_id}: {}{}</w:t></w:r></w:p>"#,
                        escape_xml(cap),
                        escape_xml(&src_suffix),
                        col = escape_xml(&spec.visual.secondary_accent),
                        img_id = img_id,
                    ));
                }
            }
            filevo_spec::BlockAST::Callout { title, content, .. } => {
                xml.push_str(&format!(
                    r#"<w:p><w:pPr><w:pBdr><w:left w:val="single" w:sz="24" w:space="15" w:color="{accent}"/></w:pBdr><w:shd w:val="clear" w:color="auto" w:fill="{fill}"/><w:spacing w:before="120" w:after="120"/><w:ind w:left="240" w:right="240"/></w:pPr>"#,
                    accent = escape_xml(&spec.visual.primary_accent),
                    fill = escape_xml(&spec.visual.neutral_light),
                ));
                xml.push_str(&format!(
                    r#"<w:r><w:rPr><w:b/><w:sz w:val="22"/><w:color w:val="{accent}"/></w:rPr><w:t>{}: </w:t></w:r>"#,
                    escape_xml(title),
                    accent = escape_xml(&spec.visual.primary_accent),
                ));
                xml.push_str(&format!(
                    r#"<w:r><w:rPr><w:sz w:val="22"/><w:color w:val="{col}"/></w:rPr><w:t>{}</w:t></w:r></w:p>"#,
                    escape_xml(content),
                    col = escape_xml(&spec.typography.font_color),
                ));
            }
            filevo_spec::BlockAST::CodeBlock { code, language } => {
                let lang_banner = if let Some(l) = language { format!(" // [{}]", l) } else { String::new() };
                xml.push_str(&format!(
                    r#"<w:p><w:pPr><w:pStyle w:val="CodeBlock"/><w:shd w:val="clear" w:color="auto" w:fill="F8FAFC"/><w:pBdr><w:left w:val="single" w:sz="18" w:space="10" w:color="94A3B8"/></w:pBdr><w:spacing w:before="100" w:after="100"/><w:ind w:left="240" w:right="240"/></w:pPr>"#
                ));
                xml.push_str(&format!(
                    r#"<w:r><w:rPr><w:rFonts w:ascii="{font}" w:hAnsi="{font}"/><w:sz w:val="18"/><w:color w:val="334155"/></w:rPr><w:t xml:space="preserve">{}{}</w:t></w:r></w:p>"#,
                    escape_xml(code),
                    escape_xml(&lang_banner),
                    font = escape_xml(&spec.typography.code_font),
                ));
            }
            filevo_spec::BlockAST::BlockQuote { text, citation } => {
                xml.push_str(&format!(
                    r#"<w:p><w:pPr><w:pStyle w:val="BlockQuote"/><w:pBdr><w:left w:val="single" w:sz="18" w:space="12" w:color="{accent}"/></w:pBdr><w:spacing w:before="120" w:after="120"/><w:ind w:left="360" w:right="360"/></w:pPr>"#,
                    accent = escape_xml(&spec.visual.secondary_accent),
                ));
                xml.push_str(&format!(
                    r#"<w:r><w:rPr><w:i/><w:sz w:val="{sz}"/><w:color w:val="475569"/></w:rPr><w:t>“{}”</w:t></w:r>"#,
                    escape_xml(text),
                    sz = spec.typography.body_size_half_points,
                ));
                if let Some(attr) = citation {
                    xml.push_str(&format!(
                        r#"<w:r><w:rPr><w:sz w:val="{sz}"/><w:color w:val="64748B"/></w:rPr><w:t xml:space="preserve"> — {}</w:t></w:r>"#,
                        escape_xml(attr),
                        sz = spec.typography.body_size_half_points - 2,
                    ));
                }
                xml.push_str(r#"</w:p>"#);
            }
            filevo_spec::BlockAST::PageBreak => {
                xml.push_str(r#"<w:p><w:r><w:br w:type="page"/></w:r></w:p>"#);
            }
            filevo_spec::BlockAST::SectionBreak { .. } => {
                xml.push_str(r#"<w:p><w:pPr><w:sectPr/></w:pPr></w:p>"#);
            }
            filevo_spec::BlockAST::Footnote { index, text } => {
                xml.push_str(&format!(
                    r#"<w:p><w:pPr><w:pStyle w:val="Normal"/><w:spacing w:after="80"/></w:pPr><w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr><w:footnoteReference w:id="{}"/></w:r><w:r><w:rPr><w:i/><w:sz w:val="18"/><w:color w:val="64748B"/></w:rPr><w:t xml:space="preserve"> [{}: {}]</w:t></w:r></w:p>"#,
                    index,
                    index,
                    escape_xml(text),
                ));
            }
        }
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
    DocxValidator::validate_package(path)
        .map(|_| ())
        .map_err(|e| DocxError::MalformedPackage(e.to_string()))
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

    #[test]
    fn test_render_package_from_ast_and_spec() {
        use filevo_decision::{DecisionEngine, DesignProfile};
        use filevo_spec::{BlockAST, DocumentAST, ReferenceItemAST, SpecCompiler};
        use std::collections::HashMap;

        let engine = DecisionEngine::new();
        let decisions = engine
            .evaluate("Technical Report on Distributed Systems", DesignProfile::TechnicalReport, &HashMap::new())
            .expect("Decision evaluation must succeed");
        let spec = SpecCompiler::compile(&decisions, DesignProfile::TechnicalReport)
            .expect("Spec compilation must succeed");

        let mut ast = DocumentAST::new("Distributed Consensus Architecture", "Distributed Computing", "Technical Report");
        ast.add_section(
            "Executive Overview",
            vec![
                BlockAST::Paragraph {
                    text: "Modern consensus protocols balance latency and fault tolerance across Byzantine environments.".into(),
                    is_bluf: true,
                },
                BlockAST::Callout {
                    title: "Architecture Invariant".into(),
                    content: "Quorum intersection guarantees linearizability under asynchronous networks.".into(),
                    kind: "info".into(),
                },
            ],
        );

        ast.add_section(
            "Comparative Performance",
            vec![
                BlockAST::List {
                    items: vec![
                        "Raft consensus protocol with leader leases".into(),
                        "Paxos consensus with multi-decree optimizations".into(),
                    ],
                    ordered: false,
                },
                BlockAST::Table {
                    headers: vec!["Protocol".into(), "Commit Latency".into(), "Throughput".into()],
                    rows: vec![
                        vec!["Multi-Paxos".into(), "1.2 ms".into(), "85k ops/sec".into()],
                        vec!["Raft".into(), "1.4 ms".into(), "78k ops/sec".into()],
                    ],
                    caption: Some("Consensus Protocol Latency Benchmark".into()),
                },
                BlockAST::Image {
                    path: "figures/fig1.png".into(),
                    caption: Some("State Transition Machine".into()),
                    source: Some("Distributed Systems Lab".into()),
                    alt_text: Some("State Transition Machine Diagram".into()),
                    width_inches: 5.5,
                    data: None,
                },
            ],
        );

        ast.add_reference(ReferenceItemAST {
            title: "In Search of an Understandable Consensus Algorithm".into(),
            url: "https://raft.github.io/raft.pdf".into(),
        });

        let tmp = tempfile::NamedTempFile::new().unwrap();
        let path = tmp.path().to_path_buf();

        DocxWriter::render_package(&ast, &spec, &path)
            .expect("Rendering package from AST and Spec must succeed");

        validate_docx_package(&path)
            .expect("Generated package must pass OpenXML package validation");

        let read_doc = DocxReader::read_from_file(&path).expect("Read docx must succeed");
        assert_eq!(read_doc.title, "Distributed Consensus Architecture");
        assert!(read_doc.sections.iter().any(|s| s.heading == "Executive Overview"));
        assert!(read_doc.sections.iter().any(|s| s.heading == "Comparative Performance"));
        assert!(read_doc.sections.iter().any(|s| s.heading == "References & Literature Cited"));
    }

    #[test]
    fn test_render_advanced_blocks_and_landscape_spec() {
        use filevo_decision::{DecisionEngine, DesignProfile};
        use filevo_spec::{
            BlockAST, DocumentAST, NestedListItemAST, PageOrientation, SpecCompiler,
        };
        use std::collections::HashMap;

        let engine = DecisionEngine::new();
        let mut overrides = HashMap::new();
        overrides.insert("page_geometry:orientation".into(), "Landscape".into());
        overrides.insert("headers_footers:include_page_numbers".into(), "true".into());

        let decisions = engine
            .evaluate("High Performance Computing Monograph", DesignProfile::AcademicMonograph, &overrides)
            .expect("Evaluation must succeed");
        let mut spec = SpecCompiler::compile(&decisions, DesignProfile::AcademicMonograph)
            .expect("Spec compilation must succeed");
        spec.headers_footers.header_right_text = "HPC Technical Report".into();
        spec.headers_footers.footer_left_text = "Confidential".into();

        assert_eq!(spec.geometry.orientation, PageOrientation::Landscape);
        assert!(spec.geometry.width_twips > spec.geometry.height_twips);

        let mut ast = DocumentAST::new("Parallel Reduction Matrix", "Compute", "Monograph");
        ast.add_footnote("First order linear cache locality.");
        ast.add_bibliography("ref1", "Hennessy & Patterson, Computer Architecture (6th ed).");

        ast.add_section(
            "Kernel Acceleration",
            vec![
                BlockAST::CodeBlock {
                    code: "__global__ void reduce(float *g_idata, float *g_odata) {}".into(),
                    language: Some("cuda".into()),
                },
                BlockAST::BlockQuote {
                    text: "Fast algorithms utilize low-latency registers.".into(),
                    citation: Some("Patterson et al.".into()),
                },
                BlockAST::NestedList {
                    items: vec![
                        NestedListItemAST { text: "Level 1 Cache hit".into(), level: 0 },
                        NestedListItemAST { text: "Level 2 Shared Banking".into(), level: 1 },
                        NestedListItemAST { text: "L2 Bank Conflict Free".into(), level: 2 },
                    ],
                    ordered: true,
                },
                BlockAST::Footnote { index: 1, text: "Assumes Volta architecture.".into() },
                BlockAST::PageBreak,
            ],
        );

        let tmp = tempfile::NamedTempFile::new().unwrap();
        let path = tmp.path().to_path_buf();

        DocxWriter::render_package(&ast, &spec, &path)
            .expect("Rendering advanced package must succeed");

        validate_docx_package(&path)
            .expect("Advanced package must validate cleanly against OpenXML rules");

        // Verify that header1.xml and footer1.xml exist and contain expected tokens
        let file = File::open(&path).unwrap();
        let mut archive = ZipArchive::new(file).unwrap();

        let mut header_content = String::new();
        archive.by_name("word/header1.xml").unwrap().read_to_string(&mut header_content).unwrap();
        assert!(header_content.contains("HPC Technical Report"));

        let mut footer_content = String::new();
        archive.by_name("word/footer1.xml").unwrap().read_to_string(&mut footer_content).unwrap();
        assert!(footer_content.contains("Confidential"));
        assert!(footer_content.contains("PAGE"));
        assert!(footer_content.contains("NUMPAGES"));

        let mut doc_content = String::new();
        archive.by_name("word/document.xml").unwrap().read_to_string(&mut doc_content).unwrap();
        assert!(doc_content.contains("w:orient=\"landscape\""));
        assert!(doc_content.contains("reduce(float *g_idata"));
        assert!(doc_content.contains("Level 2 Shared Banking"));
        assert!(doc_content.contains("Bibliography"));
    }

    #[test]
    fn test_openxml_conformance_and_negative_validation() {
        use filevo_decision::DesignProfile;
        use filevo_spec::SpecCompiler;

        let mut ast = filevo_spec::DocumentAST::new("Conformance Audit", "OpenXML", "TechnicalReport");
        ast.footnotes.push(filevo_spec::FootnoteItemAST {
            id: 1,
            text: "Empirical observation from 2026 testbench.".into(),
        });

        let sec1 = filevo_spec::SectionAST {
            heading: "Methodology".into(),
            level: 1,
            blocks: vec![
                filevo_spec::BlockAST::Paragraph {
                    text: "High-concurrency benchmark evaluation.".into(),
                    is_bluf: true,
                },
                filevo_spec::BlockAST::Footnote {
                    index: 1,
                    text: "Empirical observation from 2026 testbench.".into(),
                },
                filevo_spec::BlockAST::Table {
                    headers: vec!["Metric".into(), "Baseline".into(), "Measured".into()],
                    rows: vec![
                        vec!["Throughput (ops/s)".into(), "1,200".into(), "9,850".into()],
                        vec!["P99 Latency (ms)".into(), "45.2".into(), "2.1".into()],
                    ],
                    caption: Some("Performance Comparison".into()),
                },
            ],
            page_break_before: false,
            subsections: Vec::new(),
        };
        ast.sections.push(sec1);

        let spec = SpecCompiler::compile(&[], DesignProfile::TechnicalReport).unwrap();
        let tmp = tempfile::NamedTempFile::new().unwrap();
        let path = tmp.path().to_path_buf();

        DocxWriter::render_package(&ast, &spec, &path).expect("Package render must succeed");

        // Validate package with comprehensive validator
        let summary = DocxValidator::validate_package(&path).expect("Package must pass validation");
        assert!(summary.xml_parts_verified >= 7);
        assert!(summary.overrides_verified >= 8);
        assert!(summary.footnotes_verified >= 1);

        // Verify footnotes.xml and settings.xml
        let file = File::open(&path).unwrap();
        let mut archive = ZipArchive::new(file).unwrap();

        let mut fn_content = String::new();
        archive.by_name("word/footnotes.xml").unwrap().read_to_string(&mut fn_content).unwrap();
        assert!(fn_content.contains(r#"w:id="1""#));
        assert!(fn_content.contains("Empirical observation"));

        let mut settings_content = String::new();
        archive.by_name("word/settings.xml").unwrap().read_to_string(&mut settings_content).unwrap();
        assert!(settings_content.contains(r#"<w:updateFields w:val="true"/>"#));

        let mut doc_content = String::new();
        archive.by_name("word/document.xml").unwrap().read_to_string(&mut doc_content).unwrap();
        assert!(doc_content.contains(r#"<w:footnoteReference w:id="1"/>"#));
        assert!(doc_content.contains("<w:tblHeader/>"));
        assert!(doc_content.contains("<w:cantSplit/>"));
        assert!(doc_content.contains("w:keepNext"));
    }
}
