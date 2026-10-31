use std::cmp::Ordering;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DiscoveredFile {
    pub relative_path: String,
    pub filename: String,
    pub extension: String,
    pub size_bytes: u64,
}

impl DiscoveredFile {
    pub fn badge(&self) -> &'static str {
        file_kind_badge(&self.extension)
    }

    pub fn formatted_size(&self) -> String {
        format_size(self.size_bytes)
    }
}

pub fn file_kind_badge(ext: &str) -> &'static str {
    match ext.to_ascii_lowercase().as_str() {
        "docx" | "doc" => "DOCX",
        "md" | "markdown" => "MD",
        "rs" | "py" | "js" | "ts" | "c" | "cpp" | "h" | "go" | "sh" | "bash" | "fish"
        | "toml" | "json" | "yaml" | "yml" => "CODE",
        "csv" | "tsv" | "parquet" | "sqlite" | "db" => "DATA",
        "pdf" => "PDF",
        "txt" | "log" => "TEXT",
        "png" | "jpg" | "jpeg" | "svg" | "webp" => "IMG",
        _ => "FILE",
    }
}

pub fn format_size(size: u64) -> String {
    if size < 1024 {
        format!("{size} B")
    } else if size < 1024 * 1024 {
        format!("{:.1} KB", size as f64 / 1024.0)
    } else if size < 1024 * 1024 * 1024 {
        format!("{:.1} MB", size as f64 / (1024.0 * 1024.0))
    } else {
        format!("{:.1} GB", size as f64 / (1024.0 * 1024.0 * 1024.0))
    }
}

/// Recursively scans workspace files up to max_depth and max_files.
/// Skips common noisy directories (.git, target, node_modules, .venv, etc.).
pub fn discover_workspace_files(root: &Path, max_depth: usize, max_files: usize) -> Vec<DiscoveredFile> {
    let mut results = Vec::new();
    let mut stack: Vec<(PathBuf, usize)> = vec![(root.to_path_buf(), 0)];

    while let Some((current_dir, depth)) = stack.pop() {
        if results.len() >= max_files {
            break;
        }

        let entries = match fs::read_dir(&current_dir) {
            Ok(iter) => iter,
            Err(_) => continue,
        };

        for entry in entries.flatten() {
            if results.len() >= max_files {
                break;
            }

            let path = entry.path();
            let file_name = entry.file_name();
            let file_name_str = file_name.to_string_lossy();

            // Skip hidden directories and build/dependency caches
            if file_name_str.starts_with('.') && file_name_str != "." {
                continue;
            }

            let file_type = match entry.file_type() {
                Ok(ft) => ft,
                Err(_) => continue,
            };

            if file_type.is_dir() {
                if depth < max_depth && !should_skip_dir(&file_name_str) {
                    stack.push((path, depth + 1));
                }
            } else if file_type.is_file() {
                let Ok(relative) = path.strip_prefix(root) else {
                    continue;
                };

                let rel_str = relative
                    .components()
                    .map(|c| c.as_os_str().to_string_lossy().to_string())
                    .collect::<Vec<_>>()
                    .join("/");

                let extension = path
                    .extension()
                    .and_then(|ext| ext.to_str())
                    .unwrap_or("")
                    .to_string();

                let size_bytes = entry.metadata().map(|m| m.len()).unwrap_or(0);

                results.push(DiscoveredFile {
                    relative_path: rel_str,
                    filename: file_name_str.to_string(),
                    extension,
                    size_bytes,
                });
            }
        }
    }

    // Sort: .docx files first (Filevo document core), then by relative path
    results.sort_by(|a, b| {
        let a_docx = a.extension.eq_ignore_ascii_case("docx");
        let b_docx = b.extension.eq_ignore_ascii_case("docx");
        match (a_docx, b_docx) {
            (true, false) => Ordering::Less,
            (false, true) => Ordering::Greater,
            _ => a.relative_path.to_lowercase().cmp(&b.relative_path.to_lowercase()),
        }
    });

    results
}

fn should_skip_dir(name: &str) -> bool {
    matches!(
        name,
        "target"
            | "node_modules"
            | ".git"
            | ".venv"
            | "venv"
            | "__pycache__"
            | ".idea"
            | ".vscode"
            | ".next"
            | "dist"
            | "build"
            | ".trash"
            | ".gemini"
    )
}

/// Filter workspace files matching a user search query.
/// Returns ranked matches up to limit.
pub fn filter_files<'a>(files: &'a [DiscoveredFile], query: &str, limit: usize) -> Vec<&'a DiscoveredFile> {
    let clean_query = query.trim().to_lowercase();
    if clean_query.is_empty() {
        return files.iter().take(limit).collect();
    }

    let mut scored: Vec<(u8, &'a DiscoveredFile)> = Vec::new();

    for file in files {
        let fn_lower = file.filename.to_lowercase();
        let path_lower = file.relative_path.to_lowercase();

        let rank = if fn_lower.starts_with(&clean_query) {
            0
        } else if path_lower.starts_with(&clean_query) {
            1
        } else if fn_lower.contains(&clean_query) {
            2
        } else if path_lower.contains(&clean_query) {
            3
        } else {
            continue;
        };

        scored.push((rank, file));
    }

    scored.sort_by(|(r1, f1), (r2, f2)| {
        r1.cmp(r2).then_with(|| {
            f1.relative_path
                .to_lowercase()
                .cmp(&f2.relative_path.to_lowercase())
        })
    });

    scored.into_iter().take(limit).map(|(_, f)| f).collect()
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ActiveMention {
    pub at_index: usize,
    pub query: String,
    pub has_quote: bool,
    pub quote_char: Option<char>,
}

/// Detects if cursor is currently within an active `@filepath` mention.
/// Supports both unquoted `@file` and quoted `@"file with spaces"` syntax.
pub fn detect_file_mention(graphemes: &[String], cursor: usize) -> Option<ActiveMention> {
    if cursor == 0 || cursor > graphemes.len() {
        return None;
    }

    let mut at_pos = None;
    for i in (0..cursor).rev() {
        if graphemes[i] == "@" {
            // Check preceding character
            if i > 0 {
                let prev = &graphemes[i - 1];
                let is_delimiter = prev.chars().all(|c| {
                    c.is_whitespace()
                        || matches!(
                            c,
                            '(' | '[' | '{' | '"' | '\'' | '=' | ',' | ':' | ';' | '/' | '<' | '>'
                        )
                });
                if !is_delimiter {
                    // Preceded by alphanumeric or token char (e.g. user@domain.com) -> ignore
                    return None;
                }
            }
            at_pos = Some(i);
            break;
        }
    }

    let at_idx = at_pos?;
    let slice = &graphemes[at_idx + 1..cursor];

    if slice.is_empty() {
        return Some(ActiveMention {
            at_index: at_idx,
            query: String::new(),
            has_quote: false,
            quote_char: None,
        });
    }

    let first = &slice[0];
    if first == "\"" || first == "'" {
        let quote = first.chars().next()?;
        // Check if there is already a closing quote before cursor
        let rest = &slice[1..];
        if rest.iter().any(|g| g == first) {
            // Already closed before cursor
            return None;
        }
        let query = rest.concat();
        Some(ActiveMention {
            at_index: at_idx,
            query,
            has_quote: true,
            quote_char: Some(quote),
        })
    } else {
        // Unquoted: cannot contain whitespace
        if slice.iter().any(|g| g.chars().any(char::is_whitespace)) {
            return None;
        }
        let query = slice.concat();
        Some(ActiveMention {
            at_index: at_idx,
            query,
            has_quote: false,
            quote_char: None,
        })
    }
}

/// Formats the selected file path for insertion into prompt.
/// Wraps in quotes if the path contains spaces.
pub fn format_file_mention_insertion(path: &str) -> String {
    if path.contains(char::is_whitespace) {
        format!("@\"{path}\" ")
    } else {
        format!("@{path} ")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use unicode_segmentation::UnicodeSegmentation;

    fn to_graphemes(s: &str) -> Vec<String> {
        s.graphemes(true).map(str::to_string).collect()
    }

    #[test]
    fn test_detect_mention_simple() {
        let g = to_graphemes("@");
        let m = detect_file_mention(&g, 1).unwrap();
        assert_eq!(m.at_index, 0);
        assert_eq!(m.query, "");
        assert!(!m.has_quote);

        let g = to_graphemes("/train @rep");
        let m = detect_file_mention(&g, 11).unwrap();
        assert_eq!(m.at_index, 7);
        assert_eq!(m.query, "rep");
        assert!(!m.has_quote);
    }

    #[test]
    fn test_detect_mention_quoted_with_spaces() {
        let g = to_graphemes("inspect @\"folder with spaces/doc");
        let m = detect_file_mention(&g, g.len()).unwrap();
        assert_eq!(m.at_index, 8);
        assert_eq!(m.query, "folder with spaces/doc");
        assert!(m.has_quote);
        assert_eq!(m.quote_char, Some('"'));
    }

    #[test]
    fn test_detect_mention_ignores_email() {
        let g = to_graphemes("contact user@example.com for help");
        assert!(detect_file_mention(&g, 17).is_none());
    }

    #[test]
    fn test_detect_mention_unquoted_space_ends() {
        let g = to_graphemes("/train @sample docx");
        assert!(detect_file_mention(&g, g.len()).is_none());
    }

    #[test]
    fn test_detect_mention_unicode() {
        let g = to_graphemes("@résumé.txt");
        let m = detect_file_mention(&g, g.len()).unwrap();
        assert_eq!(m.at_index, 0);
        assert_eq!(m.query, "résumé.txt");
    }

    #[test]
    fn test_filter_files_ranking() {
        let files = vec![
            DiscoveredFile {
                relative_path: "nested/report.docx".to_string(),
                filename: "report.docx".to_string(),
                extension: "docx".to_string(),
                size_bytes: 1024,
            },
            DiscoveredFile {
                relative_path: "annual_report.pdf".to_string(),
                filename: "annual_report.pdf".to_string(),
                extension: "pdf".to_string(),
                size_bytes: 2048,
            },
            DiscoveredFile {
                relative_path: "readme.md".to_string(),
                filename: "readme.md".to_string(),
                extension: "md".to_string(),
                size_bytes: 512,
            },
        ];

        let res = filter_files(&files, "rep", 10);
        assert_eq!(res.len(), 2);
        // Filename starting with rep should rank first
        assert_eq!(res[0].filename, "report.docx");
        assert_eq!(res[1].filename, "annual_report.pdf");
    }

    #[test]
    fn test_format_file_mention_insertion() {
        assert_eq!(format_file_mention_insertion("doc.docx"), "@doc.docx ");
        assert_eq!(
            format_file_mention_insertion("folder with spaces/doc.docx"),
            "@\"folder with spaces/doc.docx\" "
        );
    }
}
