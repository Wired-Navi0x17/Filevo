//! Application state and keyboard semantics.
//!
//! All backend work is represented as an explicit `Request` handed to the
//! single worker thread.  The renderer only reads this state.

use crate::backend::{Event, Request};
use crate::fixtures::{demo_dashboard, demo_messages};
use crate::model::{Dashboard, Decision, INTENTS, Message, Risk, Role, format_epoch_hms};
use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use serde_json::Value;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::PathBuf;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};
use unicode_segmentation::UnicodeSegmentation;
use unicode_width::UnicodeWidthStr;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NavTab {
    Home,
    Create,
    Analyze,
    Train,
    Model,
    Settings,
    Help,
}

impl NavTab {
    pub const ALL: [NavTab; 7] = [
        NavTab::Home,
        NavTab::Create,
        NavTab::Analyze,
        NavTab::Train,
        NavTab::Model,
        NavTab::Settings,
        NavTab::Help,
    ];

    pub fn label(self) -> &'static str {
        match self {
            Self::Home => "HOME",
            Self::Create => "CREATE",
            Self::Analyze => "ANALYZE",
            Self::Train => "TRAIN",
            Self::Model => "MODEL",
            Self::Settings => "SETTINGS",
            Self::Help => "HELP",
        }
    }

    pub fn index(self) -> usize {
        Self::ALL.iter().position(|tab| *tab == self).unwrap_or(0)
    }

    pub fn from_index(index: usize) -> Option<Self> {
        Self::ALL.get(index).copied()
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Focus {
    Input,
    Navigation,
    Conversation,
    Documents,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum View {
    Home,
    Model,
    Settings,
    Help,
}

#[derive(Debug, Clone)]
pub enum BackendState {
    Demo,
    Connecting,
    Online,
    Offline(String),
}

impl BackendState {
    pub fn label(&self) -> &'static str {
        match self {
            Self::Demo => "Demo",
            Self::Connecting => "Connecting",
            Self::Online => "Live",
            Self::Offline(_) => "Offline",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ToastKind {
    Info,
    Success,
    Warning,
    Error,
}

#[derive(Debug, Clone)]
pub struct Toast {
    pub text: String,
    pub kind: ToastKind,
    pub created: Instant,
}

#[derive(Debug, Clone)]
pub enum TaskState {
    Idle,
    Running {
        label: String,
        started: Instant,
        cancelling: bool,
    },
}

impl TaskState {
    pub fn is_running(&self) -> bool {
        matches!(self, Self::Running { .. })
    }

    pub fn label(&self) -> Option<&str> {
        match self {
            Self::Idle => None,
            Self::Running { label, .. } => Some(label),
        }
    }

    pub fn elapsed(&self) -> Option<Duration> {
        match self {
            Self::Idle => None,
            Self::Running { started, .. } => Some(started.elapsed()),
        }
    }

    pub fn cancelling(&self) -> bool {
        matches!(
            self,
            Self::Running {
                cancelling: true,
                ..
            }
        )
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PendingKind {
    Chat,
    Create,
    Revise,
    ModelView,
    SettingsView,
    ConversationCommand,
}

#[derive(Debug, Clone)]
pub struct PendingTask {
    pub id: u64,
    pub kind: PendingKind,
}

#[derive(Debug, Clone)]
pub struct CommandSpec {
    pub name: &'static str,
    pub usage: &'static str,
    pub description: &'static str,
}

/// Mirrors the Python `COMMANDS` registry.  A unit test reads the Python
/// source to keep these names in sync; dispatch still goes through Python.
pub const COMMANDS: &[CommandSpec] = &[
    CommandSpec {
        name: "/help",
        usage: "/help",
        description: "Shows commands and keyboard shortcuts",
    },
    CommandSpec {
        name: "/create",
        usage: "/create <topic>",
        description: "Creates a calibrated DOCX document",
    },
    CommandSpec {
        name: "/revise",
        usage: "/revise <instruction>",
        description: "Revises and versions the active document",
    },
    CommandSpec {
        name: "/research",
        usage: "/research <topic>",
        description: "Researches live web sources",
    },
    CommandSpec {
        name: "/analyze",
        usage: "/analyze [path]",
        description: "Analyzes a document or codebase",
    },
    CommandSpec {
        name: "/train",
        usage: "/train [@file|dir|live]",
        description: "Ingests docs, builds datasets & trains policy",
    },
    CommandSpec {
        name: "/feedback",
        usage: "/feedback [+1.0|-0.5]",
        description: "Records feedback on the active generation",
    },
    CommandSpec {
        name: "/dataset",
        usage: "/dataset [dir]",
        description: "Builds a leakage-free DOCX dataset",
    },
    CommandSpec {
        name: "/benchmark",
        usage: "/benchmark",
        description: "Benchmarks candidate local models",
    },
    CommandSpec {
        name: "/model",
        usage: "/model",
        description: "Reports model and policy telemetry",
    },
    CommandSpec {
        name: "/settings",
        usage: "/settings",
        description: "Opens settings panel and command reference (Ctrl+P)",
    },
    CommandSpec {
        name: "/clear",
        usage: "/clear",
        description: "Clears the conversation view",
    },
    CommandSpec {
        name: "/copy",
        usage: "/copy",
        description: "Copies the last assistant response to clipboard (Ctrl+Y)",
    },
    CommandSpec {
        name: "/exit",
        usage: "/exit",
        description: "Exits Filevo (Ctrl+Q also works)",
    },
];

pub fn command_spec(name: &str) -> Option<&'static CommandSpec> {
    COMMANDS.iter().find(|spec| spec.name == name)
}

// ---------------------------------------------------------------------------
// Input editing
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CompletionKind {
    Command,
    File { at_index: usize },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CompletionItem {
    pub display: String,
    pub value: String,
    pub detail: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CompletionMenu {
    pub kind: CompletionKind,
    pub items: Vec<CompletionItem>,
    pub selected: usize,
}

#[derive(Debug, Clone, Default)]
pub struct InputState {
    graphemes: Vec<String>,
    cursor: usize,
    history: Vec<String>,
    history_index: Option<usize>,
    draft: String,
    pub completion: Option<CompletionMenu>,
}

impl InputState {
    pub fn text(&self) -> String {
        self.graphemes.concat()
    }

    pub fn set_text(&mut self, text: &str) {
        self.graphemes = text
            .graphemes(true)
            .filter(|g| *g != "\n" && *g != "\r")
            .map(str::to_string)
            .collect();
        self.cursor = self.graphemes.len();
        self.history_index = None;
        self.completion = None;
    }

    pub fn clear(&mut self) {
        self.graphemes.clear();
        self.cursor = 0;
        self.history_index = None;
        self.completion = None;
    }

    pub fn is_empty(&self) -> bool {
        self.graphemes.is_empty()
    }

    pub fn cursor(&self) -> usize {
        self.cursor
    }

    pub fn insert_str(&mut self, text: &str) {
        let normalised = text.replace("\r\n", " ").replace(['\n', '\r'], " ");
        for grapheme in normalised.graphemes(true) {
            if grapheme.chars().any(|c| c.is_control()) {
                continue;
            }
            self.graphemes.insert(self.cursor, grapheme.to_string());
            self.cursor += 1;
        }
        self.history_index = None;
        self.completion = None;
    }

    pub fn insert_char(&mut self, ch: char) {
        if ch.is_control() {
            return;
        }
        let mut buffer = [0u8; 4];
        self.insert_str(ch.encode_utf8(&mut buffer));
    }

    pub fn backspace(&mut self) {
        if self.cursor > 0 {
            self.cursor -= 1;
            self.graphemes.remove(self.cursor);
            self.history_index = None;
            self.completion = None;
        }
    }

    pub fn delete(&mut self) {
        if self.cursor < self.graphemes.len() {
            self.graphemes.remove(self.cursor);
            self.history_index = None;
            self.completion = None;
        }
    }

    pub fn move_left(&mut self) {
        self.cursor = self.cursor.saturating_sub(1);
    }

    pub fn move_right(&mut self) {
        if self.cursor < self.graphemes.len() {
            self.cursor += 1;
        }
    }

    pub fn home(&mut self) {
        self.cursor = 0;
    }

    pub fn end(&mut self) {
        self.cursor = self.graphemes.len();
    }

    pub fn history_up(&mut self) {
        if self.history.is_empty() {
            return;
        }
        match self.history_index {
            None => {
                self.draft = self.text();
                self.history_index = Some(self.history.len() - 1);
            }
            Some(index) if index > 0 => {
                self.history_index = Some(index - 1);
            }
            Some(_) => {}
        }
        if let Some(index) = self.history_index {
            self.graphemes = self.history[index]
                .graphemes(true)
                .map(str::to_string)
                .collect();
            self.cursor = self.graphemes.len();
            self.completion = None;
        }
    }

    pub fn history_down(&mut self) {
        let Some(index) = self.history_index else {
            return;
        };
        if index + 1 < self.history.len() {
            self.history_index = Some(index + 1);
            let text = &self.history[index + 1];
            self.graphemes = text.graphemes(true).map(str::to_string).collect();
            self.cursor = self.graphemes.len();
        } else {
            self.history_index = None;
            self.graphemes = self.draft.graphemes(true).map(str::to_string).collect();
            self.cursor = self.graphemes.len();
        }
        self.completion = None;
    }

    pub fn load_history(&mut self) {
        let path = history_path();
        let Ok(text) = fs::read_to_string(path) else {
            return;
        };
        self.history = text
            .lines()
            .map(str::trim)
            .filter(|line| !line.is_empty() && line.len() < 4096)
            .map(str::to_string)
            .collect();
        if self.history.len() > 250 {
            self.history.drain(0..self.history.len() - 250);
        }
    }

    pub fn remember(&mut self, text: &str) {
        let text = text.trim();
        if text.is_empty() {
            return;
        }
        if self.history.last().map(String::as_str) != Some(text) {
            self.history.push(text.to_string());
        }
        if self.history.len() > 250 {
            self.history.remove(0);
        }
        append_history(text);
    }

    pub fn delete_word_backward(&mut self) {
        if self.cursor == 0 {
            return;
        }
        let mut idx = self.cursor;
        while idx > 0 && self.graphemes[idx - 1].chars().all(char::is_whitespace) {
            idx -= 1;
        }
        while idx > 0 && !self.graphemes[idx - 1].chars().all(char::is_whitespace) {
            idx -= 1;
        }
        self.graphemes.drain(idx..self.cursor);
        self.cursor = idx;
        self.history_index = None;
        self.completion = None;
    }

    pub fn completion_selected(&self) -> Option<&CompletionItem> {
        self.completion
            .as_ref()
            .and_then(|menu| menu.items.get(menu.selected))
    }

    pub fn completion_next(&mut self) {
        if let Some(menu) = &mut self.completion {
            if !menu.items.is_empty() {
                menu.selected = (menu.selected + 1) % menu.items.len();
            }
        }
    }

    pub fn completion_prev(&mut self) {
        if let Some(menu) = &mut self.completion {
            if !menu.items.is_empty() {
                menu.selected = if menu.selected == 0 {
                    menu.items.len().saturating_sub(1)
                } else {
                    menu.selected - 1
                };
            }
        }
    }

    pub fn close_completion(&mut self) {
        self.completion = None;
    }

    /// Re-evaluates completions based on current text and cursor position.
    /// NEVER auto-expands or modifies user text! Only updates the completion menu.
    pub fn refresh_completion(&mut self, workspace_files: &[crate::files::DiscoveredFile]) {
        // 1. Check for active @file mention
        if let Some(mention) = crate::files::detect_file_mention(&self.graphemes, self.cursor) {
            let matches = crate::files::filter_files(workspace_files, &mention.query, 15);
            if matches.is_empty() {
                self.completion = Some(CompletionMenu {
                    kind: CompletionKind::File {
                        at_index: mention.at_index,
                    },
                    items: vec![CompletionItem {
                        display: "No matching files".to_string(),
                        value: String::new(),
                        detail: String::new(),
                    }],
                    selected: 0,
                });
            } else {
                let items: Vec<CompletionItem> = matches
                    .iter()
                    .map(|f| CompletionItem {
                        display: f.relative_path.clone(),
                        value: f.relative_path.clone(),
                        detail: format!("{} · {}", f.badge(), f.formatted_size()),
                    })
                    .collect();
                self.completion = Some(CompletionMenu {
                    kind: CompletionKind::File {
                        at_index: mention.at_index,
                    },
                    items,
                    selected: 0,
                });
            }
            return;
        }

        // 2. Check for slash command completion
        let full_text = self.text();
        if full_text.starts_with('/') {
            let cursor_prefix = if self.cursor <= self.graphemes.len() {
                self.graphemes[..self.cursor].concat()
            } else {
                full_text.clone()
            };

            // Only complete command if cursor is before any argument whitespace
            if !cursor_prefix.contains(char::is_whitespace) {
                let matches: Vec<&CommandSpec> = COMMANDS
                    .iter()
                    .filter(|cmd| cmd.name.starts_with(&cursor_prefix))
                    .collect();

                if !matches.is_empty() {
                    let items: Vec<CompletionItem> = matches
                        .iter()
                        .map(|cmd| CompletionItem {
                            display: cmd.name.to_string(),
                            value: cmd.name.to_string(),
                            detail: cmd.description.to_string(),
                        })
                        .collect();
                    self.completion = Some(CompletionMenu {
                        kind: CompletionKind::Command,
                        items,
                        selected: 0,
                    });
                    return;
                }
            }
        }

        // No active mention or command prefix
        self.completion = None;
    }

    /// Explicitly triggers completion upon user pressing Tab.
    /// Returns true if completion was applied or menu was opened.
    pub fn trigger_tab_completion(&mut self, workspace_files: &[crate::files::DiscoveredFile]) -> bool {
        if self.completion.is_some() {
            return self.apply_selected_completion();
        }

        self.refresh_completion(workspace_files);
        if let Some(menu) = &self.completion {
            let actionable: Vec<&CompletionItem> =
                menu.items.iter().filter(|it| !it.value.is_empty()).collect();
            if actionable.len() == 1 {
                return self.apply_selected_completion();
            }
            return !actionable.is_empty();
        }
        false
    }

    /// Applies the currently selected item in the completion menu.
    pub fn apply_selected_completion(&mut self) -> bool {
        let Some(menu) = self.completion.take() else {
            return false;
        };
        let Some(item) = menu.items.get(menu.selected) else {
            return false;
        };
        if item.value.is_empty() {
            return false;
        }

        match menu.kind {
            CompletionKind::Command => {
                self.set_text(&format!("{} ", item.value));
                true
            }
            CompletionKind::File { at_index } => {
                let insertion = crate::files::format_file_mention_insertion(&item.value);
                let insert_graphemes: Vec<String> = insertion
                    .graphemes(true)
                    .map(str::to_string)
                    .collect();

                let end = self.cursor.min(self.graphemes.len());
                self.graphemes
                    .splice(at_index..end, insert_graphemes.iter().cloned());
                self.cursor = at_index + insert_graphemes.len();
                self.history_index = None;
                true
            }
        }
    }

    /// Returns the visible substring and the cursor offset in terminal cells.
    /// Trimming happens from the left so the cursor is always visible.
    pub fn visible_window(&self, available_cells: usize) -> (String, usize) {
        let available = available_cells.max(1);
        let cursor_width: usize = self.graphemes[..self.cursor]
            .iter()
            .map(|g| UnicodeWidthStr::width(g.as_str()))
            .sum();
        let mut start = 0usize;
        while start < self.cursor {
            let prefix_width: usize = self.graphemes[..start]
                .iter()
                .map(|g| UnicodeWidthStr::width(g.as_str()))
                .sum();
            if cursor_width.saturating_sub(prefix_width) < available {
                break;
            }
            start += 1;
        }
        let visible = self.graphemes[start..].concat();
        let cursor_cells = cursor_width
            .saturating_sub(
                self.graphemes[..start]
                    .iter()
                    .map(|g| UnicodeWidthStr::width(g.as_str()))
                    .sum::<usize>(),
            )
            .min(available.saturating_sub(1));
        (visible, cursor_cells)
    }
}

fn history_path() -> PathBuf {
    std::env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".filevo")
        .join("history_rs")
}

fn append_history(text: &str) {
    let path = history_path();
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(file, "{text}");
    }
}

// ---------------------------------------------------------------------------
// Application state
// ---------------------------------------------------------------------------

#[derive(Debug)]
pub enum AppAction {
    None,
    Quit,
    Send(Request),
    OpenUrl(String),
    RequestDashboard,
}

pub struct App {
    pub demo: bool,
    pub focus: Focus,
    pub view: View,
    pub active_tab: NavTab,
    pub nav_selected: NavTab,
    pub messages: Vec<Message>,
    pub next_message_id: u64,
    pub conversation_revision: u64,
    pub scroll_top: usize,
    pub follow_tail: bool,
    pub last_top: usize,
    pub last_max_top: usize,
    pub last_viewport: usize,
    pub input: InputState,
    pub dashboard: Dashboard,
    pub backend: BackendState,
    pub task: TaskState,
    pub task_id: Option<u64>,
    pub task_seq: u64,
    pub cancel_token: Option<Arc<AtomicBool>>,
    pub pending: Option<PendingTask>,
    pub toast: Option<Toast>,
    pub doc_selected: usize,
    pub ref_selected: usize,
    pub should_quit: bool,
    pub tick: u64,
    pub last_dashboard_refresh: Option<Instant>,
    pub dashboard_in_flight: bool,
    pub model_output: Option<String>,
    pub status_output: Option<String>,
    pub detail_loading: bool,
    pub detail_error: Option<String>,
    pub detail_scroll: usize,
    pub detail_max_scroll: usize,
    pub detail_viewport: usize,
    pub history_loaded: bool,
    pub last_backend_error: Option<String>,
    pub was_online: bool,
    pub last_layout: crate::ui::layout::LayoutRects,
    pub workspace_files: Vec<crate::files::DiscoveredFile>,
}

impl App {
    pub fn new(demo: bool) -> Self {
        let mut input = InputState::default();
        input.load_history();
        let (dashboard, messages, backend) = if demo {
            (demo_dashboard(), demo_messages(), BackendState::Demo)
        } else {
            (Dashboard::default(), Vec::new(), BackendState::Connecting)
        };
        let next_message_id = messages.iter().map(|m| m.id).max().unwrap_or(0) + 1;
        let follow_tail = !demo;
        let workspace_files =
            crate::files::discover_workspace_files(std::path::Path::new("."), 6, 500);
        Self {
            demo,
            focus: Focus::Input,
            view: View::Home,
            active_tab: NavTab::Home,
            nav_selected: NavTab::Home,
            messages,
            next_message_id,
            conversation_revision: 1,
            scroll_top: 0,
            follow_tail,
            last_top: 0,
            last_max_top: 0,
            last_viewport: 0,
            input,
            dashboard,
            backend,
            task: TaskState::Idle,
            task_id: None,
            task_seq: 0,
            cancel_token: None,
            pending: None,
            toast: None,
            doc_selected: 0,
            ref_selected: 0,
            should_quit: false,
            tick: 0,
            last_dashboard_refresh: None,
            dashboard_in_flight: false,
            model_output: None,
            status_output: None,
            detail_loading: false,
            detail_error: None,
            detail_scroll: 0,
            detail_max_scroll: 0,
            detail_viewport: 0,
            history_loaded: demo,
            last_backend_error: None,
            was_online: false,
            last_layout: crate::ui::layout::LayoutRects::default(),
            workspace_files,
        }
    }

    pub fn refresh_workspace_files(&mut self) {
        self.workspace_files =
            crate::files::discover_workspace_files(std::path::Path::new("."), 6, 500);
    }

    pub fn on_tick(&mut self) {
        self.tick = self.tick.wrapping_add(1);
    }

    pub fn toast(&mut self, text: impl Into<String>, kind: ToastKind) {
        self.toast = Some(Toast {
            text: text.into(),
            kind,
            created: Instant::now(),
        });
    }

    pub fn active_toast(&self) -> Option<&Toast> {
        self.toast
            .as_ref()
            .filter(|toast| toast.created.elapsed() < Duration::from_secs(4))
    }

    pub fn toast_active(&self) -> bool {
        self.active_toast().is_some()
    }

    fn add_message(&mut self, message: Message, scroll_follows: bool) {
        self.messages.push(message);
        self.next_message_id += 1;
        self.conversation_revision = self.conversation_revision.wrapping_add(1);
        if scroll_follows && !self.follow_tail {
            self.toast("New reply below · End to jump", ToastKind::Info);
        }
    }

    fn simple_message(&mut self, role: Role, text: impl Into<String>) {
        let id = self.next_message_id;
        let timestamp = chrono::Local::now().format("%H:%M:%S").to_string();
        self.add_message(Message::new(id, role, text, timestamp), true);
    }

    fn error_message(&mut self, text: impl Into<String>) {
        let id = self.next_message_id;
        let timestamp = chrono::Local::now().format("%H:%M:%S").to_string();
        self.add_message(Message::error(id, text, timestamp), true);
    }

    pub fn clear_conversation(&mut self) {
        self.messages.clear();
        self.conversation_revision = self.conversation_revision.wrapping_add(1);
        self.scroll_top = 0;
        self.follow_tail = true;
        self.history_loaded = true;
    }

    pub fn copy_last_response(&mut self) {
        let last_reply = self
            .messages
            .iter()
            .rev()
            .find(|m| m.role == Role::Assistant)
            .map(|m| m.content.clone());

        if let Some(content) = last_reply {
            let mut copied = false;
            // 1. Try wl-copy (Wayland)
            if let Ok(mut child) = std::process::Command::new("wl-copy")
                .stdin(std::process::Stdio::piped())
                .spawn()
            {
                if let Some(mut stdin) = child.stdin.take() {
                    use std::io::Write;
                    let _ = stdin.write_all(content.as_bytes());
                }
                if let Ok(status) = child.wait() {
                    if status.success() {
                        copied = true;
                    }
                }
            }
            // 2. Try xclip (X11)
            if !copied {
                if let Ok(mut child) = std::process::Command::new("xclip")
                    .arg("-selection")
                    .arg("clipboard")
                    .stdin(std::process::Stdio::piped())
                    .spawn()
                {
                    if let Some(mut stdin) = child.stdin.take() {
                        use std::io::Write;
                        let _ = stdin.write_all(content.as_bytes());
                    }
                    if let Ok(status) = child.wait() {
                        if status.success() {
                            copied = true;
                        }
                    }
                }
            }
            // 3. Emit OSC 52 ANSI escape sequence as standard terminal clipboard bridge
            use std::io::Write;
            let b64 = {
                const B64_CHARS: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
                let bytes = content.as_bytes();
                let mut out = String::new();
                for chunk in bytes.chunks(3) {
                    let b0 = chunk[0];
                    let b1 = if chunk.len() > 1 { chunk[1] } else { 0 };
                    let b2 = if chunk.len() > 2 { chunk[2] } else { 0 };
                    out.push(B64_CHARS[(b0 >> 2) as usize] as char);
                    out.push(B64_CHARS[(((b0 & 0x03) << 4) | (b1 >> 4)) as usize] as char);
                    if chunk.len() > 1 {
                        out.push(B64_CHARS[(((b1 & 0x0f) << 2) | (b2 >> 6)) as usize] as char);
                    } else {
                        out.push('=');
                    }
                    if chunk.len() > 2 {
                        out.push(B64_CHARS[(b2 & 0x3f) as usize] as char);
                    } else {
                        out.push('=');
                    }
                }
                out
            };
            let osc52 = format!("\x1b]52;c;{b64}\x07");
            let _ = std::io::stdout().write_all(osc52.as_bytes());
            let _ = std::io::stdout().flush();

            self.toast("Copied reply to clipboard · Hold Shift to select text", ToastKind::Success);
        } else {
            self.toast("No assistant message to copy yet", ToastKind::Info);
        }
    }

    pub fn open_output_directory(&mut self) {
        let home = std::env::var("HOME").unwrap_or_else(|_| "/home/l41n-pr0t0".to_string());
        let output_dir = std::path::PathBuf::from(home).join(".filevo/output");
        let _ = std::fs::create_dir_all(&output_dir);
        let spawned = std::process::Command::new("dolphin")
            .arg(&output_dir)
            .spawn()
            .or_else(|_| {
                std::process::Command::new("xdg-open")
                    .arg(&output_dir)
                    .spawn()
            });
        match spawned {
            Ok(_) => {
                self.toast(
                    format!("Opened in Dolphin: {}", output_dir.display()),
                    ToastKind::Success,
                );
            }
            Err(err) => {
                self.toast(
                    format!("Failed to open file manager: {err}"),
                    ToastKind::Error,
                );
            }
        }
    }

    // ------------------------------------------------------------- mouse

    pub fn on_mouse(&mut self, event: crossterm::event::MouseEvent) -> AppAction {
        use crossterm::event::{MouseButton, MouseEventKind};
        match event.kind {
            MouseEventKind::ScrollUp => {
                self.on_mouse_scroll(event.column, event.row, -3)
            }
            MouseEventKind::ScrollDown => {
                self.on_mouse_scroll(event.column, event.row, 3)
            }
            MouseEventKind::Down(MouseButton::Left) => {
                self.on_mouse_click(event.column, event.row)
            }
            _ => AppAction::None,
        }
    }

    fn on_mouse_scroll(&mut self, col: u16, row: u16, delta: i32) -> AppAction {
        let layout = self.last_layout;
        // Detail view scroll if active
        if self.view != View::Home {
            if delta < 0 {
                self.scroll_detail_up(delta.unsigned_abs() as usize);
            } else {
                self.scroll_detail_down(delta.unsigned_abs() as usize);
            }
            return AppAction::None;
        }

        // Documents panel scroll
        if row >= layout.documents.y
            && row < layout.documents.y + layout.documents.height
            && col >= layout.documents.x
            && col < layout.documents.x + layout.documents.width
        {
            if delta < 0 {
                self.doc_selected = self.doc_selected.saturating_sub(1);
            } else {
                let max = self.dashboard.documents.len().saturating_sub(1);
                self.doc_selected = (self.doc_selected + 1).min(max);
            }
            return AppAction::None;
        }

        // Conversation scroll
        if delta < 0 {
            self.scroll_conversation_up(delta.unsigned_abs() as usize);
        } else {
            self.scroll_conversation_down(delta.unsigned_abs() as usize);
        }
        AppAction::None
    }

    fn on_mouse_click(&mut self, col: u16, row: u16) -> AppAction {
        let layout = self.last_layout;

        // In detail view, clicking top header returns to Home
        if self.view != View::Home && row < 3 {
            self.view = View::Home;
            self.active_tab = NavTab::Home;
            return AppAction::None;
        }

        // Navigation bar click
        if row >= layout.nav.y
            && row < layout.nav.y + layout.nav.height
            && col >= layout.nav.x
            && col < layout.nav.x + layout.nav.width
        {
            if let Some(tab) = nav_tab_at(col, layout.nav) {
                return self.activate_nav(tab);
            }
        }

        // Model & Session panel click
        if row >= layout.model.y
            && row < layout.model.y + layout.model.height
            && col >= layout.model.x
            && col < layout.model.x + layout.model.width
        {
            return self.activate_nav(NavTab::Model);
        }

        // Input prompt click
        if row >= layout.prompt.y && row < layout.prompt.y + layout.prompt.height {
            self.focus = Focus::Input;
            return AppAction::None;
        }

        // Conversation click
        if row >= layout.conversation.y
            && row < layout.conversation.y + layout.conversation.height
            && col >= layout.conversation.x
            && col < layout.conversation.x + layout.conversation.width
        {
            self.focus = Focus::Conversation;
            return AppAction::None;
        }

        // Documents panel click
        if row >= layout.documents.y
            && row < layout.documents.y + layout.documents.height
            && col >= layout.documents.x
            && col < layout.documents.x + layout.documents.width
        {
            self.focus = Focus::Documents;
            let rel_row = row.saturating_sub(layout.documents.y + 1) as usize;
            if rel_row < self.dashboard.documents.len() {
                self.doc_selected = rel_row;
                self.attach_selected_document();
            }
            return AppAction::None;
        }

        AppAction::None
    }

    // ------------------------------------------------------------- keyboard

    pub fn on_key(&mut self, key: KeyEvent) -> AppAction {
        let ctrl = key.modifiers.contains(KeyModifiers::CONTROL);
        let alt = key.modifiers.contains(KeyModifiers::ALT);
        let shift = key.modifiers.contains(KeyModifiers::SHIFT);

        if ctrl && matches!(key.code, KeyCode::Char('q') | KeyCode::Char('Q')) {
            self.should_quit = true;
            return AppAction::Quit;
        }
        if ctrl && matches!(key.code, KeyCode::Char('p') | KeyCode::Char('P')) {
            return self.activate_nav(NavTab::Settings);
        }
        if ctrl && matches!(key.code, KeyCode::Char('c') | KeyCode::Char('C')) {
            self.cancel_task();
            return AppAction::None;
        }
        if ctrl && matches!(key.code, KeyCode::Char('y') | KeyCode::Char('Y')) {
            self.copy_last_response();
            return AppAction::None;
        }
        if ctrl && matches!(key.code, KeyCode::Char('o') | KeyCode::Char('O')) {
            self.open_output_directory();
            return AppAction::None;
        }
        if ctrl && matches!(key.code, KeyCode::Char('r') | KeyCode::Char('R')) {
            return AppAction::RequestDashboard;
        }
        if key.code == KeyCode::F(1) {
            self.activate_nav(NavTab::Help);
            return AppAction::None;
        }
        if key.code == KeyCode::F(6) {
            self.cycle_focus(!shift);
            return AppAction::None;
        }
        if alt {
            if let KeyCode::Char(ch) = key.code {
                if let Some(digit) = ch.to_digit(10) {
                    if (1..=8).contains(&digit) {
                        if let Some(tab) = NavTab::from_index((digit - 1) as usize) {
                            self.activate_nav(tab);
                        }
                        return AppAction::None;
                    }
                }
            }
        }

        if ctrl && matches!(key.code, KeyCode::Tab | KeyCode::BackTab) {
            self.cycle_focus(!matches!(key.code, KeyCode::BackTab) && !shift);
            return AppAction::None;
        }

        if key.code == KeyCode::Esc {
            if self.focus == Focus::Input {
                if self.input.completion.is_some() {
                    self.input.close_completion();
                    return AppAction::None;
                }
                self.focus = Focus::Navigation;
                self.nav_selected = self.active_tab;
            } else {
                self.focus = Focus::Input;
            }
            return AppAction::None;
        }

        match self.focus {
            Focus::Input => self.handle_input_key(key),
            Focus::Navigation => self.handle_navigation_key(key),
            Focus::Conversation => self.handle_conversation_key(key),
            Focus::Documents => self.handle_documents_key(key),
        }
    }

    fn handle_input_key(&mut self, key: KeyEvent) -> AppAction {
        // If completion popup is currently open, handle completion navigation keys
        if self.input.completion.is_some() {
            match key.code {
                KeyCode::Esc => {
                    self.input.close_completion();
                    return AppAction::None;
                }
                KeyCode::Up | KeyCode::BackTab => {
                    self.input.completion_prev();
                    return AppAction::None;
                }
                KeyCode::Down => {
                    self.input.completion_next();
                    return AppAction::None;
                }
                KeyCode::Tab | KeyCode::Enter => {
                    if self.input.apply_selected_completion() {
                        return AppAction::None;
                    }
                }
                _ => {}
            }
        }

        match key.code {
            KeyCode::Enter => self.submit(),
            KeyCode::Tab => {
                if !self.input.trigger_tab_completion(&self.workspace_files) {
                    self.toast("No completions available", ToastKind::Info);
                }
                AppAction::None
            }
            KeyCode::Backspace => {
                if key.modifiers.contains(KeyModifiers::CONTROL) {
                    self.input.delete_word_backward();
                } else {
                    self.input.backspace();
                }
                self.input.refresh_completion(&self.workspace_files);
                AppAction::None
            }
            KeyCode::Char('h') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.input.backspace();
                self.input.refresh_completion(&self.workspace_files);
                AppAction::None
            }
            KeyCode::Char('w') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.input.delete_word_backward();
                self.input.refresh_completion(&self.workspace_files);
                AppAction::None
            }
            KeyCode::Delete => {
                self.input.delete();
                self.input.refresh_completion(&self.workspace_files);
                AppAction::None
            }
            KeyCode::Left => {
                self.input.move_left();
                self.input.refresh_completion(&self.workspace_files);
                AppAction::None
            }
            KeyCode::Right => {
                self.input.move_right();
                self.input.refresh_completion(&self.workspace_files);
                AppAction::None
            }
            KeyCode::Home => {
                self.input.home();
                self.input.refresh_completion(&self.workspace_files);
                AppAction::None
            }
            KeyCode::End => {
                self.input.end();
                self.input.refresh_completion(&self.workspace_files);
                AppAction::None
            }
            KeyCode::Up => {
                self.input.history_up();
                AppAction::None
            }
            KeyCode::Down => {
                self.input.history_down();
                AppAction::None
            }
            KeyCode::PageUp => {
                if self.view == View::Home {
                    self.scroll_conversation_up(self.last_viewport.saturating_sub(2).max(1));
                } else {
                    self.scroll_detail_up(self.detail_viewport.saturating_sub(2).max(1));
                }
                AppAction::None
            }
            KeyCode::PageDown => {
                if self.view == View::Home {
                    self.scroll_conversation_down(self.last_viewport.saturating_sub(2).max(1));
                } else {
                    self.scroll_detail_down(self.detail_viewport.saturating_sub(2).max(1));
                }
                AppAction::None
            }
            KeyCode::Char('a') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.input.home();
                self.input.refresh_completion(&self.workspace_files);
                AppAction::None
            }
            KeyCode::Char('e') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.input.end();
                self.input.refresh_completion(&self.workspace_files);
                AppAction::None
            }
            KeyCode::Char('u') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.input.set_text("");
                self.input.refresh_completion(&self.workspace_files);
                AppAction::None
            }
            KeyCode::Char(ch)
                if !key.modifiers.contains(KeyModifiers::CONTROL)
                    && !key.modifiers.contains(KeyModifiers::ALT) =>
            {
                if ch == '@' {
                    self.refresh_workspace_files();
                }
                self.input.insert_char(ch);
                self.input.refresh_completion(&self.workspace_files);
                AppAction::None
            }
            _ => AppAction::None,
        }
    }

    fn handle_navigation_key(&mut self, key: KeyEvent) -> AppAction {
        match key.code {
            KeyCode::Left | KeyCode::Up => {
                let index = self
                    .nav_selected
                    .index()
                    .checked_sub(1)
                    .unwrap_or(NavTab::ALL.len() - 1);
                self.nav_selected = NavTab::from_index(index).unwrap_or(NavTab::Home);
                AppAction::None
            }
            KeyCode::Right | KeyCode::Down => {
                let index = (self.nav_selected.index() + 1) % NavTab::ALL.len();
                self.nav_selected = NavTab::from_index(index).unwrap_or(NavTab::Home);
                AppAction::None
            }
            KeyCode::Enter | KeyCode::Char(' ') => {
                self.activate_nav(self.nav_selected);
                self.focus = Focus::Input;
                AppAction::None
            }
            KeyCode::Tab => {
                self.focus = Focus::Input;
                AppAction::None
            }
            KeyCode::Char(ch)
                if !key
                    .modifiers
                    .intersects(KeyModifiers::CONTROL | KeyModifiers::ALT) =>
            {
                self.focus = Focus::Input;
                self.input.insert_char(ch);
                AppAction::None
            }
            _ => AppAction::None,
        }
    }

    fn handle_conversation_key(&mut self, key: KeyEvent) -> AppAction {
        match key.code {
            KeyCode::Up => {
                self.scroll_conversation_up(1);
                AppAction::None
            }
            KeyCode::Down => {
                self.scroll_conversation_down(1);
                AppAction::None
            }
            KeyCode::PageUp => {
                self.scroll_conversation_up(self.last_viewport.saturating_sub(2).max(1));
                AppAction::None
            }
            KeyCode::PageDown => {
                self.scroll_conversation_down(self.last_viewport.saturating_sub(2).max(1));
                AppAction::None
            }
            KeyCode::Home => {
                self.scroll_conversation_to_top();
                AppAction::None
            }
            KeyCode::End => {
                self.scroll_conversation_to_bottom();
                AppAction::None
            }
            KeyCode::Enter => {
                self.focus = Focus::Input;
                AppAction::None
            }
            KeyCode::Tab => {
                self.focus = Focus::Input;
                AppAction::None
            }
            KeyCode::Char(ch)
                if !key
                    .modifiers
                    .intersects(KeyModifiers::CONTROL | KeyModifiers::ALT) =>
            {
                self.focus = Focus::Input;
                self.input.insert_char(ch);
                AppAction::None
            }
            _ => AppAction::None,
        }
    }

    fn handle_documents_key(&mut self, key: KeyEvent) -> AppAction {
        let count = self.dashboard.documents.len();
        match key.code {
            KeyCode::Up if count > 0 => {
                self.doc_selected = self.doc_selected.checked_sub(1).unwrap_or(count - 1);
                AppAction::None
            }
            KeyCode::Down if count > 0 => {
                self.doc_selected = (self.doc_selected + 1) % count;
                AppAction::None
            }
            KeyCode::Enter => {
                self.attach_selected_document();
                AppAction::None
            }
            KeyCode::Tab => {
                self.focus = Focus::Input;
                AppAction::None
            }
            _ => AppAction::None,
        }
    }



    pub fn cycle_focus(&mut self, forward: bool) {
        const ORDER: [Focus; 3] = [
            Focus::Input,
            Focus::Navigation,
            Focus::Conversation,
        ];
        let current = ORDER
            .iter()
            .position(|focus| *focus == self.focus)
            .unwrap_or(0);
        let next = if forward {
            (current + 1) % ORDER.len()
        } else {
            (current + ORDER.len() - 1) % ORDER.len()
        };
        self.focus = ORDER[next];
        if self.focus == Focus::Navigation {
            self.nav_selected = self.active_tab;
        }
    }

    pub fn activate_nav(&mut self, tab: NavTab) -> AppAction {
        self.active_tab = tab;
        self.nav_selected = tab;
        self.focus = Focus::Input;
        match tab {
            NavTab::Home => {
                self.view = View::Home;
                AppAction::None
            }
            NavTab::Create => {
                self.view = View::Home;
                self.input.set_text("/create ");
                self.toast("Describe the document to create", ToastKind::Info);
                AppAction::None
            }
            NavTab::Analyze => {
                self.view = View::Home;
                self.input.set_text("/analyze ");
                self.toast(
                    "Enter a document, directory or codebase path",
                    ToastKind::Info,
                );
                AppAction::None
            }

            NavTab::Train => {
                self.view = View::Home;
                if self.input.text().trim() == "/train" {
                    self.submit()
                } else {
                    self.input.set_text("/train");
                    self.toast("Click TRAIN again or press Enter to run", ToastKind::Info);
                    AppAction::None
                }
            }
            NavTab::Model => {
                self.view = View::Model;
                self.detail_scroll = 0;
                self.detail_error = None;
                if self.demo {
                    self.detail_loading = false;
                    self.toast("Demo model telemetry", ToastKind::Info);
                    AppAction::None
                } else {
                    self.detail_loading = true;
                    let (task_id, cancel) =
                        self.begin_task(PendingKind::ModelView, "Reading model telemetry");
                    AppAction::Send(Request::Python {
                        task_id,
                        args: vec!["model".to_string()],
                        cancel,
                    })
                }
            }
            NavTab::Settings => {
                self.view = View::Settings;
                self.detail_scroll = 0;
                self.detail_error = None;
                if self.demo {
                    self.detail_loading = false;
                    self.toast("Demo settings", ToastKind::Info);
                    AppAction::None
                } else {
                    self.detail_loading = true;
                    let (task_id, cancel) =
                        self.begin_task(PendingKind::SettingsView, "Reading system settings");
                    AppAction::Send(Request::Python {
                        task_id,
                        args: vec!["settings".to_string()],
                        cancel,
                    })
                }
            }
            NavTab::Help => {
                self.view = View::Help;
                self.detail_scroll = 0;
                AppAction::None
            }
        }
    }

    // ------------------------------------------------------------- submit

    pub fn submit(&mut self) -> AppAction {
        if self.task.is_running() {
            self.toast("Backend busy · Ctrl+C to cancel", ToastKind::Warning);
            return AppAction::None;
        }
        let text = self.input.text();
        let text = text.trim().to_string();
        if text.is_empty() {
            return AppAction::None;
        }
        self.input.remember(&text);
        self.input.clear();
        self.input.close_completion();
        self.active_tab = NavTab::Home;

        if text.starts_with('/') {
            let mut parts = text.splitn(2, char::is_whitespace);
            let command = parts.next().unwrap_or("");
            let argument = parts.next().unwrap_or("").trim().to_string();
            return self.handle_command(command, &argument);
        }

        let id = self.next_message_id;
        let timestamp = chrono::Local::now().format("%H:%M:%S").to_string();
        self.add_message(Message::new(id, Role::User, text.clone(), timestamp), false);
        if self.demo {
            self.simple_message(
                Role::System,
                "Demo mode uses the reference fixtures and does not execute backend actions. Launch without --demo for live inference.",
            );
            return AppAction::None;
        }
        if self.view != View::Home {
            self.view = View::Home;
        }
        let (task_id, cancel) = self.begin_task(PendingKind::Chat, "Filevo is thinking");
        AppAction::Send(Request::Chat {
            task_id,
            text,
            cancel,
        })
    }

    fn handle_command(&mut self, command: &str, argument: &str) -> AppAction {
        let id = self.next_message_id;
        let timestamp = chrono::Local::now().format("%H:%M:%S").to_string();
        self.add_message(
            Message::new(
                id,
                Role::User,
                format!(
                    "{command}{}",
                    if argument.is_empty() {
                        String::new()
                    } else {
                        format!(" {argument}")
                    }
                ),
                timestamp,
            ),
            false,
        );

        match command {
            "/help" => {
                self.view = View::Help;
                self.active_tab = NavTab::Help;
                self.detail_scroll = 0;
                self.toast(
                    "Help opened · HOME returns to conversation",
                    ToastKind::Info,
                );
                AppAction::None
            }
            "/clear" => {
                self.clear_conversation();
                self.view = View::Home;
                self.active_tab = NavTab::Home;
                self.toast(
                    "Conversation view cleared · backend memory retained",
                    ToastKind::Info,
                );
                AppAction::None
            }
            "/copy" => {
                self.copy_last_response();
                AppAction::None
            }
            "/exit" | "/quit" | "/q" => {
                self.should_quit = true;
                AppAction::Quit
            }
            "/create" => {
                if argument.is_empty() {
                    self.error_message("Usage: /create <topic or request>");
                    return AppAction::None;
                }
                self.view = View::Home;
                if self.demo {
                    self.demo_action_blocked("document generation");
                    return AppAction::None;
                }
                let (task_id, cancel) = self.begin_task(PendingKind::Create, "Creating document");
                AppAction::Send(Request::Daemon {
                    task_id,
                    action: "create".to_string(),
                    payload: serde_json::json!({ "request": argument }),
                    cancel,
                })
            }
            "/revise" => {
                if argument.is_empty() {
                    self.error_message("Usage: /revise <instruction>");
                    return AppAction::None;
                }
                self.view = View::Home;
                if self.demo {
                    self.demo_action_blocked("document revision");
                    return AppAction::None;
                }
                let (task_id, cancel) = self.begin_task(PendingKind::Revise, "Revising document");
                AppAction::Send(Request::Daemon {
                    task_id,
                    action: "revise".to_string(),
                    payload: serde_json::json!({ "instruction": argument }),
                    cancel,
                })
            }
            "/research" => {
                if argument.is_empty() {
                    self.error_message("Usage: /research <topic>");
                    return AppAction::None;
                }
                self.run_conversation_command(
                    vec!["research".to_string(), argument.to_string()],
                    "Researching live sources",
                )
            }
            "/analyze" => {
                let path = if argument.is_empty() { "." } else { argument };
                self.run_conversation_command(
                    vec!["analyze".to_string(), path.to_string()],
                    "Analyzing document or codebase",
                )
            }
            "/index" => {
                let argument = if argument.is_empty() { "." } else { argument };
                let mut args = vec!["train".to_string()];
                args.extend(argument.split_whitespace().map(str::to_string));
                self.toast("/index unified into /train", ToastKind::Info);
                self.run_conversation_command(
                    args,
                    "Running unified ingestion and training",
                )
            }
            "/train" => {
                let argument = if argument.is_empty() {
                    "corpus"
                } else {
                    argument
                };
                let mut args = vec!["train".to_string()];
                args.extend(argument.split_whitespace().map(str::to_string));
                self.run_conversation_command(args, "Running training workflow")
            }
            "/feedback" => {
                let reward = if argument.is_empty() {
                    "+1.0"
                } else {
                    argument
                };
                self.run_conversation_command(
                    vec!["feedback".to_string(), reward.to_string()],
                    "Recording feedback",
                )
            }
            "/dataset" => {
                let path = if argument.is_empty() { "." } else { argument };
                self.run_conversation_command(
                    vec!["dataset".to_string(), path.to_string()],
                    "Building training dataset",
                )
            }
            "/benchmark" => self.run_conversation_command(
                vec!["benchmark".to_string()],
                "Benchmarking local models",
            ),
            "/model" => {
                self.view = View::Model;
                self.active_tab = NavTab::Model;
                self.detail_scroll = 0;
                self.detail_error = None;
                if self.demo {
                    self.detail_loading = false;
                    self.toast("Demo model telemetry", ToastKind::Info);
                    return AppAction::None;
                }
                self.detail_loading = true;
                let (task_id, cancel) =
                    self.begin_task(PendingKind::ModelView, "Reading model telemetry");
                AppAction::Send(Request::Python {
                    task_id,
                    args: vec!["model".to_string()],
                    cancel,
                })
            }
            "/settings" => {
                self.view = View::Settings;
                self.active_tab = NavTab::Settings;
                self.detail_scroll = 0;
                self.detail_error = None;
                if self.demo {
                    self.detail_loading = false;
                    self.toast("Demo settings", ToastKind::Info);
                    return AppAction::None;
                }
                self.detail_loading = true;
                let (task_id, cancel) =
                    self.begin_task(PendingKind::SettingsView, "Reading system settings");
                AppAction::Send(Request::Python {
                    task_id,
                    args: vec!["settings".to_string()],
                    cancel,
                })
            }
            "/open" | "/browse" | "/files" => {
                self.open_output_directory();
                AppAction::None
            }
            _ => {
                self.error_message(format!(
                    "Unknown command: {command}\nType /help for available commands."
                ));
                AppAction::None
            }
        }
    }

    fn run_conversation_command(&mut self, args: Vec<String>, label: &str) -> AppAction {
        self.view = View::Home;
        if self.demo {
            self.demo_action_blocked(label);
            return AppAction::None;
        }
        let (task_id, cancel) = self.begin_task(PendingKind::ConversationCommand, label);
        AppAction::Send(Request::Python {
            task_id,
            args,
            cancel,
        })
    }

    fn demo_action_blocked(&mut self, action: &str) {
        self.simple_message(
            Role::System,
            format!(
                "Demo mode: {action} is disabled. These panels show the reference fixtures; launch without --demo for live backend actions."
            ),
        );
    }

    fn begin_task(&mut self, kind: PendingKind, label: &str) -> (u64, Arc<AtomicBool>) {
        self.task_seq = self.task_seq.wrapping_add(1);
        let id = self.task_seq;
        let cancel = Arc::new(AtomicBool::new(false));
        self.task_id = Some(id);
        self.cancel_token = Some(cancel.clone());
        self.pending = Some(PendingTask { id, kind });
        self.task = TaskState::Running {
            label: label.to_string(),
            started: Instant::now(),
            cancelling: false,
        };
        (id, cancel)
    }

    pub fn cancel_task(&mut self) {
        if let TaskState::Running { cancelling, .. } = &mut self.task {
            if !*cancelling {
                *cancelling = true;
                if let Some(token) = &self.cancel_token {
                    token.store(true, Ordering::Relaxed);
                }
                self.toast("Cancelling…", ToastKind::Warning);
            }
        } else {
            self.toast("Nothing is running · Ctrl+Q exits", ToastKind::Info);
        }
    }

    pub fn request_failed(&mut self, message: impl Into<String>) {
        let message = message.into();
        self.finish_task();
        self.error_message(format!("Backend error: {message}"));
        self.last_backend_error = Some(message);
    }

    // ------------------------------------------------------------- events

    pub fn apply_event(&mut self, event: Event) {
        match event {
            Event::Dashboard(dashboard) => self.apply_dashboard(*dashboard),
            Event::DashboardError(message) => self.apply_dashboard_error(message),
            Event::ChatReply {
                task_id,
                content,
                references,
                decision,
            } => {
                if !self.matches_task(task_id) {
                    return;
                }
                self.finish_task();
                let id = self.next_message_id;
                let timestamp = chrono::Local::now().format("%H:%M:%S").to_string();
                self.add_message(Message::new(id, Role::Assistant, content, timestamp), true);
                if let Some(decision) = decision {
                    self.apply_decision(decision);
                }
                if !references.is_empty() {
                    self.dashboard.references = references;
                    self.dashboard.telemetry.web.live_references =
                        self.dashboard.references.len() as u64;
                    self.dashboard.telemetry.web.last_result = "live".to_string();
                }
                self.last_dashboard_refresh = None;
                self.toast("Reply received", ToastKind::Success);
            }
            Event::DaemonResult { task_id, payload } => {
                if !self.matches_task(task_id) {
                    return;
                }
                let kind = self.pending.as_ref().map(|pending| pending.kind);
                self.finish_task();
                let message = match kind {
                    Some(PendingKind::Create) => {
                        format_daemon_document("Document created", &payload)
                    }
                    Some(PendingKind::Revise) => {
                        format_daemon_document("Document revised", &payload)
                    }
                    _ => "Backend operation completed.".to_string(),
                };
                self.simple_message(Role::Assistant, message);
                self.view = View::Home;
                self.last_dashboard_refresh = None;
                self.toast("Document updated", ToastKind::Success);
            }
            Event::CommandOutput {
                task_id,
                output,
                success,
            } => {
                if !self.matches_task(task_id) {
                    return;
                }
                let kind = self.pending.as_ref().map(|pending| pending.kind);
                self.finish_task();
                if matches!(kind, Some(PendingKind::ModelView)) {
                    self.detail_loading = false;
                    self.detail_error = if success {
                        None
                    } else {
                        Some("The /model command reported a failure".to_string())
                    };
                    self.model_output = Some(output);
                    self.last_dashboard_refresh = None;
                } else if matches!(kind, Some(PendingKind::SettingsView)) {
                    self.detail_loading = false;
                    self.detail_error = if success {
                        None
                    } else {
                        Some("The /settings command reported a failure".to_string())
                    };
                    self.status_output = Some(output);
                    self.last_dashboard_refresh = None;
                } else if output.trim().is_empty() {
                    self.simple_message(
                        Role::System,
                        if success {
                            "Command completed with no output."
                        } else {
                            "Command failed with no output. Check ~/.filevo/daemon.log."
                        },
                    );
                } else if success {
                    self.simple_message(Role::Assistant, output);
                } else {
                    self.error_message(format!("Command failed:\n\n{output}"));
                }
                self.view = if matches!(kind, Some(PendingKind::ModelView)) {
                    View::Model
                } else if matches!(kind, Some(PendingKind::SettingsView)) {
                    View::Settings
                } else {
                    View::Home
                };
                self.active_tab = match self.view {
                    View::Home => NavTab::Home,
                    View::Model => NavTab::Model,
                    View::Settings => NavTab::Settings,
                    View::Help => NavTab::Help,
                };
                self.toast(
                    if success {
                        "Command completed"
                    } else {
                        "Command failed"
                    },
                    if success {
                        ToastKind::Success
                    } else {
                        ToastKind::Error
                    },
                );
            }
            Event::Cancelled { task_id } => {
                if !self.matches_task(task_id) {
                    return;
                }
                let kind = self.pending.as_ref().map(|pending| pending.kind);
                self.finish_task();
                if matches!(kind, Some(PendingKind::ModelView | PendingKind::SettingsView)) {
                    self.detail_loading = false;
                    self.detail_error = Some("Cancelled".to_string());
                } else {
                    self.simple_message(Role::System, "Operation cancelled.");
                }
                self.toast("Cancelled", ToastKind::Warning);
            }
            Event::Error { task_id, message } => {
                if !self.matches_task(task_id) {
                    return;
                }
                let kind = self.pending.as_ref().map(|pending| pending.kind);
                self.finish_task();
                if matches!(kind, Some(PendingKind::ModelView | PendingKind::SettingsView)) {
                    self.detail_loading = false;
                    self.detail_error = Some(message.clone());
                }
                self.error_message(format!("Backend error: {message}"));
                self.last_backend_error = Some(message);
                if self.task_id.is_none() {
                    self.last_dashboard_refresh = None;
                }
            }
        }
    }

    fn matches_task(&self, task_id: u64) -> bool {
        self.task_id == Some(task_id)
    }

    fn finish_task(&mut self) {
        self.task = TaskState::Idle;
        self.task_id = None;
        self.cancel_token = None;
        self.pending = None;
    }

    fn apply_dashboard(&mut self, dashboard: Dashboard) {
        let first_online = !self.was_online;
        self.dashboard = dashboard;
        self.backend = BackendState::Online;
        self.dashboard_in_flight = false;
        self.last_dashboard_refresh = Some(Instant::now());
        self.last_backend_error = None;
        if !self.history_loaded {
            // Fresh session on every launch: do not restore stale conversation turns from prior sessions
            self.history_loaded = true;
        }
        if !self.dashboard.documents.is_empty() {
            self.doc_selected = self.doc_selected.min(self.dashboard.documents.len() - 1);
        } else {
            self.doc_selected = 0;
        }
        if !self.dashboard.references.is_empty() {
            self.ref_selected = self.ref_selected.min(self.dashboard.references.len() - 1);
        } else {
            self.ref_selected = 0;
        }
        if first_online {
            self.was_online = true;
            self.toast("Backend connected", ToastKind::Success);
        }
    }

    fn apply_dashboard_error(&mut self, message: String) {
        self.backend = BackendState::Offline(message.clone());
        self.dashboard_in_flight = false;
        self.last_dashboard_refresh = Some(Instant::now());
        if self.last_backend_error.as_deref() != Some(message.as_str()) {
            self.last_backend_error = Some(message.clone());
            if self.messages.is_empty() {
                self.error_message(format!(
                    "Backend unavailable: {message}\n\nThe interface remains responsive. Check ~/.filevo/daemon.log, then press Ctrl+R to retry."
                ));
            } else {
                self.toast("Backend offline · Ctrl+R to retry", ToastKind::Error);
            }
        }
    }

    fn apply_decision(&mut self, decision: Decision) {
        self.dashboard.decision = decision;
    }

    pub fn should_refresh_dashboard(&self) -> bool {
        if self.demo
            || self.dashboard_in_flight
            || self.task.is_running()
            || !matches!(self.view, View::Home | View::Model | View::Settings)
        {
            return false;
        }
        match self.last_dashboard_refresh {
            None => true,
            Some(last) => last.elapsed() >= Duration::from_secs(12),
        }
    }

    pub fn mark_dashboard_requested(&mut self) {
        self.dashboard_in_flight = true;
    }

    pub fn mark_backend_connecting(&mut self) {
        if matches!(self.backend, BackendState::Offline(_)) {
            self.backend = BackendState::Connecting;
        }
    }

    pub fn refresh_requested(&mut self) -> bool {
        if self.demo {
            self.toast("Demo mode has no live backend", ToastKind::Info);
            return false;
        }
        if self.dashboard_in_flight || self.task.is_running() {
            self.toast("Backend is busy", ToastKind::Warning);
            return false;
        }
        self.last_dashboard_refresh = None;
        true
    }

    // ------------------------------------------------------------- scrolling

    pub fn note_conversation_metrics(&mut self, top: usize, max_top: usize, viewport: usize) {
        self.last_top = top;
        self.last_max_top = max_top;
        self.last_viewport = viewport;
        if self.follow_tail {
            self.scroll_top = top;
        } else if self.scroll_top > max_top {
            self.scroll_top = max_top;
        }
    }

    pub fn note_detail_metrics(&mut self, max_scroll: usize, viewport: usize) {
        self.detail_max_scroll = max_scroll;
        self.detail_viewport = viewport;
        if self.detail_scroll > max_scroll {
            self.detail_scroll = max_scroll;
        }
    }

    pub fn scroll_conversation_up(&mut self, lines: usize) {
        if self.follow_tail {
            self.follow_tail = false;
            self.scroll_top = self.last_top.saturating_sub(lines);
        } else {
            self.scroll_top = self.scroll_top.saturating_sub(lines);
        }
    }

    pub fn scroll_conversation_down(&mut self, lines: usize) {
        let target = self.scroll_top.saturating_add(lines).min(self.last_max_top);
        self.scroll_top = target;
        if target >= self.last_max_top {
            self.follow_tail = true;
        }
    }

    pub fn scroll_conversation_to_top(&mut self) {
        self.follow_tail = false;
        self.scroll_top = 0;
    }

    pub fn scroll_conversation_to_bottom(&mut self) {
        self.follow_tail = true;
        self.scroll_top = self.last_max_top;
    }

    pub fn scroll_detail_up(&mut self, lines: usize) {
        self.detail_scroll = self.detail_scroll.saturating_sub(lines);
    }

    pub fn scroll_detail_down(&mut self, lines: usize) {
        self.detail_scroll = self
            .detail_scroll
            .saturating_add(lines)
            .min(self.detail_max_scroll);
    }

    // ------------------------------------------------------------- documents

    pub fn attach_selected_document(&mut self) {
        let Some(document) = self.dashboard.documents.get(self.doc_selected) else {
            self.toast("No generated documents available", ToastKind::Info);
            return;
        };
        let path = document.path.clone();
        let name = document.name.clone();
        let prefix = if self.input.is_empty() { "" } else { " " };
        self.input.insert_str(&format!("{prefix}@{path} "));
        self.focus = Focus::Input;
        self.toast(format!("Attached {name} to the input"), ToastKind::Success);
    }

    pub fn visible_window(&self, available: usize) -> (String, usize) {
        self.input.visible_window(available)
    }

    pub fn task_label(&self) -> Option<String> {
        self.task.label().map(str::to_string)
    }

    pub fn decision_for_display(&self) -> &Decision {
        &self.dashboard.decision
    }

    pub fn reference_count(&self) -> usize {
        self.dashboard.references.len()
    }

    pub fn demo_notice(&self) -> bool {
        self.demo
    }
}

fn format_daemon_document(heading: &str, payload: &Value) -> String {
    let path = payload
        .get("active_doc")
        .and_then(Value::as_str)
        .unwrap_or("");
    let topic = payload.get("topic").and_then(Value::as_str).unwrap_or("");
    let archetype = payload
        .get("archetype")
        .and_then(Value::as_str)
        .unwrap_or("");
    let mut lines = Vec::new();
    if path.is_empty() {
        lines.push(format!(
            "{heading}, but the backend did not return an output path."
        ));
    } else {
        lines.push(format!("{heading}: {path}"));
    }
    if !topic.is_empty() {
        lines.push(format!("Topic: {topic}"));
    }
    if !archetype.is_empty() {
        lines.push(format!("Archetype: {archetype}"));
    }
    lines.join("\n")
}

/// A display helper for tests and the compact model view.
pub fn intent_values(decision: &Decision) -> Vec<(&'static str, Option<f64>)> {
    INTENTS
        .iter()
        .enumerate()
        .map(|(index, name)| (*name, decision.values[index]))
        .collect()
}

pub fn risk_colour(risk: Risk) -> &'static str {
    match risk {
        Risk::Low => "healthy",
        Risk::Medium => "warning",
        Risk::High => "error",
        Risk::Unknown => "muted",
    }
}

pub fn nav_tab_at(x: u16, nav_area: ratatui::layout::Rect) -> Option<NavTab> {
    crate::ui::navigation::nav_tab_at(x, nav_area)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn key(code: KeyCode) -> KeyEvent {
        KeyEvent::new(code, KeyModifiers::NONE)
    }

    #[test]
    fn command_registry_matches_python_registry() {
        let python = std::fs::read_to_string(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../doc_gen/filevo_cli.py"
        ))
        .expect("python CLI should be readable");
        for spec in COMMANDS {
            assert!(
                python.contains(&format!("\"{}\"", spec.name)),
                "{} missing from Python COMMANDS",
                spec.name
            );
        }
        assert!(!COMMANDS.iter().any(|spec| spec.name == "/prd"));
        assert!(!python.contains("\"/prd\""));
        assert!(!COMMANDS.iter().any(|spec| spec.name == "/index"));
        let commands_block = python
            .split("COMMANDS = {")
            .nth(1)
            .and_then(|s| s.split('}').next())
            .unwrap_or("");
        assert!(!commands_block.contains("\"/index\""));
    }

    #[test]
    fn editing_happens_at_the_cursor() {
        let mut input = InputState::default();
        input.insert_str("hello");
        input.move_left();
        input.move_left();
        input.insert_str("XY");
        assert_eq!(input.text(), "helXYlo");
        input.backspace();
        assert_eq!(input.text(), "helXlo");
    }

    #[test]
    fn unicode_cursor_window_stays_inside_width() {
        let mut input = InputState::default();
        input.insert_str("a界面bc");
        input.home();
        input.move_right();
        input.move_right();
        let (_text, cells) = input.visible_window(4);
        assert!(cells < 4);
    }

    #[test]
    fn tab_completion_opens_and_applies() {
        let mut input = InputState::default();
        input.set_text("/cr");
        assert!(input.trigger_tab_completion(&[]));
        assert_eq!(input.text(), "/create ");
        assert!(input.completion.is_none());

        input.set_text("/c");
        assert!(input.trigger_tab_completion(&[]));
        assert!(input.completion_selected().is_some());
        input.completion_next();
        assert_eq!(
            input.completion_selected().map(|c| c.value.as_str()),
            Some("/clear")
        );
        assert!(input.apply_selected_completion());
        assert_eq!(input.text(), "/clear ");

        // When typing '/', all visible commands are shown in menu without modifying buffer
        input.set_text("/");
        input.refresh_completion(&[]);
        assert!(input.completion.is_some());
        let menu = input.completion.as_ref().unwrap();
        assert_eq!(menu.items.len(), COMMANDS.len());
        assert_eq!(input.text(), "/");
    }

    #[test]
    fn backspace_on_slash_command_does_not_lock_or_expand() {
        let mut input = InputState::default();
        // Type /he
        input.set_text("/he");
        input.refresh_completion(&[]);
        assert!(input.completion.is_some());
        assert_eq!(input.text(), "/he");

        // Backspace should delete 'e', becoming /h (NOT auto-expanding to /help!)
        input.backspace();
        input.refresh_completion(&[]);
        assert_eq!(input.text(), "/h");
        assert!(input.completion.is_some());

        // Backspace again should delete 'h', becoming /
        input.backspace();
        input.refresh_completion(&[]);
        assert_eq!(input.text(), "/");
        assert!(input.completion.is_some());

        // Backspace again should delete '/', becoming empty and closing menu
        input.backspace();
        input.refresh_completion(&[]);
        assert_eq!(input.text(), "");
        assert!(input.completion.is_none());
    }

    #[test]
    fn file_completion_matches_and_inserts() {
        let files = vec![
            crate::files::DiscoveredFile {
                relative_path: "report.docx".to_string(),
                filename: "report.docx".to_string(),
                extension: "docx".to_string(),
                size_bytes: 2048,
            },
            crate::files::DiscoveredFile {
                relative_path: "folder with spaces/notes.txt".to_string(),
                filename: "notes.txt".to_string(),
                extension: "txt".to_string(),
                size_bytes: 1024,
            },
        ];

        let mut input = InputState::default();
        input.set_text("/train @rep");
        input.refresh_completion(&files);
        assert!(input.completion.is_some());
        assert_eq!(
            input.completion_selected().map(|c| c.value.as_str()),
            Some("report.docx")
        );
        assert!(input.apply_selected_completion());
        assert_eq!(input.text(), "/train @report.docx ");

        // Test file with spaces wraps in quotes
        input.set_text("/train @note");
        input.refresh_completion(&files);
        assert!(input.completion.is_some());
        assert!(input.apply_selected_completion());
        assert_eq!(
            input.text(),
            "/train @\"folder with spaces/notes.txt\" "
        );
    }

    #[test]
    fn delete_word_backward_cleans_prompt() {
        let mut input = InputState::default();
        input.set_text("/train @sample.docx");
        input.delete_word_backward();
        assert_eq!(input.text(), "/train ");
        input.delete_word_backward();
        assert_eq!(input.text(), "");
    }

    #[test]
    fn nav_activation_prefills_commands() {
        let mut app = App::new(true);
        app.activate_nav(NavTab::Create);
        assert_eq!(app.input.text(), "/create ");
        assert_eq!(app.active_tab, NavTab::Create);
        app.activate_nav(NavTab::Model);
        assert_eq!(app.view, View::Model);
    }

    #[test]
    fn demo_mode_never_pretends_to_run_backend_actions() {
        let mut app = App::new(true);
        app.input.set_text("/create A report");
        let action = app.submit();
        assert!(matches!(action, AppAction::None));
        assert!(app.messages.iter().any(|message| {
            message.role == Role::System && message.content.contains("Demo mode")
        }));
        assert_eq!(app.active_tab, NavTab::Home);
    }

    #[test]
    fn unknown_command_is_reported_locally() {
        let mut app = App::new(false);
        app.input.set_text("/prd something");
        let action = app.submit();
        assert!(matches!(action, AppAction::None));
        assert!(
            app.messages
                .last()
                .map(|m| m.is_error && m.content.contains("Unknown command"))
                .unwrap_or(false)
        );
    }

    #[test]
    fn scrolling_up_preserves_position_when_new_message_arrives() {
        let mut app = App::new(true);
        app.note_conversation_metrics(10, 20, 5);
        app.follow_tail = false;
        app.scroll_top = 8;
        let before = app.scroll_top;
        app.simple_message(Role::Assistant, "new reply");
        assert_eq!(app.scroll_top, before);
        assert!(!app.follow_tail);
    }

    #[test]
    fn scrolled_to_bottom_follows_new_messages() {
        let mut app = App::new(true);
        app.note_conversation_metrics(20, 20, 5);
        assert!(!app.follow_tail, "demo starts at the top of the log");
        app.scroll_conversation_down(100);
        assert!(app.follow_tail);
        app.simple_message(Role::Assistant, "new reply");
        assert!(app.follow_tail);
    }
}
