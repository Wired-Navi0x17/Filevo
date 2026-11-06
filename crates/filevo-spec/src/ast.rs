//! DocumentAST: What the document contains (Content Tree).
//!
//! Completely independent from visual styling or layout decisions.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct DocumentAST {
    pub title: String,
    pub subtitle: Option<String>,
    pub topic: String,
    pub genre: String,
    pub authors: Vec<String>,
    pub date: String,
    pub sections: Vec<SectionAST>,
    pub references: Vec<ReferenceItemAST>,
    #[serde(default)]
    pub footnotes: Vec<FootnoteItemAST>,
    #[serde(default)]
    pub bibliography: Vec<BibliographyItemAST>,
}

impl DocumentAST {
    pub fn new(title: impl Into<String>, topic: impl Into<String>, genre: impl Into<String>) -> Self {
        Self {
            title: title.into(),
            subtitle: None,
            topic: topic.into(),
            genre: genre.into(),
            authors: vec!["Filevo Autonomous Document Intelligence".into()],
            date: "November 2026".into(),
            sections: Vec::new(),
            references: Vec::new(),
            footnotes: Vec::new(),
            bibliography: Vec::new(),
        }
    }

    pub fn add_section(&mut self, heading: impl Into<String>, blocks: Vec<BlockAST>) {
        let level = 1;
        self.sections.push(SectionAST {
            heading: heading.into(),
            level,
            blocks,
            page_break_before: false,
            subsections: Vec::new(),
        });
    }

    pub fn add_section_with_level(&mut self, heading: impl Into<String>, level: usize, blocks: Vec<BlockAST>) {
        self.sections.push(SectionAST {
            heading: heading.into(),
            level,
            blocks,
            page_break_before: false,
            subsections: Vec::new(),
        });
    }

    pub fn add_reference(&mut self, item: ReferenceItemAST) {
        self.references.push(item);
    }

    pub fn add_footnote(&mut self, text: impl Into<String>) -> usize {
        let id = self.footnotes.len() + 1;
        self.footnotes.push(FootnoteItemAST {
            id,
            text: text.into(),
        });
        id
    }

    pub fn add_bibliography(&mut self, id: impl Into<String>, citation: impl Into<String>) {
        self.bibliography.push(BibliographyItemAST {
            id: id.into(),
            citation: citation.into(),
        });
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SectionAST {
    pub heading: String,
    pub level: usize,
    pub blocks: Vec<BlockAST>,
    pub page_break_before: bool,
    #[serde(default)]
    pub subsections: Vec<SectionAST>,
}

impl SectionAST {
    pub fn add_subsection(&mut self, heading: impl Into<String>, level: usize, blocks: Vec<BlockAST>) {
        self.subsections.push(SectionAST {
            heading: heading.into(),
            level,
            blocks,
            page_break_before: false,
            subsections: Vec::new(),
        });
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "type")]
pub enum BlockAST {
    Paragraph {
        text: String,
        is_bluf: bool,
    },
    List {
        items: Vec<String>,
        ordered: bool,
    },
    NestedList {
        items: Vec<NestedListItemAST>,
        ordered: bool,
    },
    Table {
        headers: Vec<String>,
        rows: Vec<Vec<String>>,
        caption: Option<String>,
    },
    Image {
        path: String,
        caption: Option<String>,
        source: Option<String>,
        #[serde(default)]
        alt_text: Option<String>,
        width_inches: f32,
        #[serde(default)]
        data: Option<Vec<u8>>,
    },
    Callout {
        title: String,
        content: String,
        kind: String,
    },
    BlockQuote {
        text: String,
        citation: Option<String>,
    },
    CodeBlock {
        code: String,
        language: Option<String>,
    },
    Footnote {
        index: usize,
        text: String,
    },
    PageBreak,
    SectionBreak {
        continuous: bool,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct NestedListItemAST {
    pub text: String,
    pub level: u8,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ReferenceItemAST {
    pub title: String,
    pub url: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FootnoteItemAST {
    pub id: usize,
    pub text: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct BibliographyItemAST {
    pub id: String,
    pub citation: String,
}
