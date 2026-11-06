//! Filevo Document Specification & AST Crate.
//!
//! Provides DocumentAST (what the document contains), DocumentSpec (how it looks),
//! compiler, and invariant validation.

pub mod ast;
pub mod compiler;
pub mod spec;
pub mod validator;

pub use ast::{
    BibliographyItemAST, BlockAST, DocumentAST, FootnoteItemAST, NestedListItemAST,
    ReferenceItemAST, SectionAST,
};
pub use compiler::{CompileError, SpecCompiler};
pub use spec::{
    CaptionPosition, CellVerticalAlignment, DocumentSpec, FigureSpec, HeaderFooterSpec,
    HeadingHierarchySpec, HeadingLevelStyle, HorizontalAlignment, ImageAlignment, LayoutDensity,
    LineSpacingMode, NavigationSpec, PageGeometrySpec, PageOrientation, PaperFormat,
    ParagraphFormattingSpec, TableBorderStyle, TableSpec, TypographySpec, VisualIdentitySpec,
};
pub use validator::{SpecValidator, ValidationError};

#[cfg(test)]
mod tests {
    use super::*;
    use filevo_decision::{DecisionEngine, DesignProfile};
    use std::collections::HashMap;

    #[test]
    fn test_ast_construction() {
        let mut ast = DocumentAST::new("Plant Root Systems", "botany", "Technical Report");
        ast.add_section(
            "Executive Summary",
            vec![BlockAST::Paragraph {
                text: "Root systems determine resource acquisition.".into(),
                is_bluf: true,
            }],
        );
        assert_eq!(ast.title, "Plant Root Systems");
        assert_eq!(ast.sections.len(), 1);
        assert_eq!(ast.sections[0].heading, "Executive Summary");
    }

    #[test]
    fn test_spec_compilation_from_decisions() {
        let engine = DecisionEngine::new();
        let decisions = engine
            .evaluate("Technical Report on Microservices", DesignProfile::TechnicalReport, &HashMap::new())
            .expect("Decision evaluation must succeed");

        let spec = SpecCompiler::compile(&decisions, DesignProfile::TechnicalReport)
            .expect("Spec compilation must succeed");

        assert_eq!(spec.geometry.paper_size, "Letter");
        assert_eq!(spec.typography.body_font, "Aptos");
        assert_eq!(spec.typography.heading_font, "Aptos Display");
        assert_eq!(spec.paragraphs.alignment, "Left");
        assert_eq!(spec.visual.primary_accent, "2E75B6");
    }

    #[test]
    fn test_geometry_invariant_validation() {
        let mut spec = SpecCompiler::compile(&[], DesignProfile::TechnicalReport).unwrap();
        // Artificially expand margins so they exceed paper width
        spec.geometry.left_margin_twips = 6000;
        spec.geometry.right_margin_twips = 6000;
        // Total margin = 12000, width = 12240 -> printable width = 240 (< 3600 required)
        let res = SpecValidator::validate(&spec);
        assert!(matches!(res, Err(ValidationError::InvalidGeometry(_))));
    }
}
