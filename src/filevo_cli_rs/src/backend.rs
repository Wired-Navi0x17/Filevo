//! Backend bridge.
//!
//! The TUI owns a single worker thread.  It talks to the existing Python
//! daemon over the existing UNIX socket, and invokes the existing one-shot
//! `filevo_cli.py` entry point for commands whose textual reports are produced
//! by Rich.  No document-generation, indexing, inference or RLCD logic is
//! duplicated here.

use crate::model::{
    Dashboard, Decision, DiskInfo, DocumentInfo, GpuInfo, ModelInfo, PolicyTelemetry,
    ReferenceInfo, Risk, SessionInfo, SystemMemory, Telemetry, TurnSnapshot, WebStatus, Role,
};
use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::HashMap;
use std::env;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Write};
use std::os::unix::net::UnixStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::mpsc::{self, Receiver, Sender};
use std::sync::{Arc, OnceLock};
use std::thread;
use std::time::{Duration, Instant};

const DAEMON_PROTOCOL: u32 = 2;
const MAX_CAPTURE_BYTES: u64 = 1_500_000;

#[derive(Debug)]
pub enum Request {
    Dashboard,
    Chat {
        task_id: u64,
        text: String,
        cancel: Arc<AtomicBool>,
    },
    Daemon {
        task_id: u64,
        action: String,
        payload: Value,
        cancel: Arc<AtomicBool>,
    },
    Python {
        task_id: u64,
        args: Vec<String>,
        cancel: Arc<AtomicBool>,
    },
}

#[derive(Debug)]
pub enum Event {
    Dashboard(Box<Dashboard>),
    DashboardError(String),
    ChatReply {
        task_id: u64,
        content: String,
        references: Vec<ReferenceInfo>,
        decision: Option<Decision>,
    },
    DaemonResult {
        task_id: u64,
        payload: Value,
    },
    CommandOutput {
        task_id: u64,
        output: String,
        success: bool,
    },
    Cancelled {
        task_id: u64,
    },
    Error {
        task_id: u64,
        message: String,
    },
}

pub struct BackendClient {
    tx: Sender<Request>,
    rx: Receiver<Event>,
}

impl BackendClient {
    pub fn spawn() -> Self {
        let (request_tx, request_rx) = mpsc::channel::<Request>();
        let (event_tx, event_rx) = mpsc::channel::<Event>();

        let _ = thread::Builder::new()
            .name("filevo-backend".to_string())
            .spawn(move || {
                while let Ok(request) = request_rx.recv() {
                    let event = handle_request(request);
                    if event_tx.send(event).is_err() {
                        break;
                    }
                }
            });

        Self {
            tx: request_tx,
            rx: event_rx,
        }
    }

    pub fn send(&self, request: Request) -> Result<(), String> {
        self.tx
            .send(request)
            .map_err(|_| "backend worker is no longer running".to_string())
    }

    pub fn try_recv(&self) -> Option<Event> {
        self.rx.try_recv().ok()
    }
}

fn handle_request(request: Request) -> Event {
    match request {
        Request::Dashboard => match fetch_dashboard() {
            Ok(dashboard) => Event::Dashboard(Box::new(dashboard)),
            Err(error) => Event::DashboardError(error),
        },
        Request::Chat {
            task_id,
            text,
            cancel,
        } => {
            let response = daemon_request(&json!({"action": "chat", "text": text}), &cancel, None);
            match response {
                Ok(value) => {
                    if let Some(message) = daemon_error(&value) {
                        return Event::Error { task_id, message };
                    }
                    let kind = value
                        .get("type")
                        .and_then(Value::as_str)
                        .unwrap_or("chat_reply");
                    let content = match kind {
                        "chat_reply" => value
                            .get("response")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        "revision" => {
                            let message = value
                                .get("message")
                                .and_then(Value::as_str)
                                .unwrap_or("Document revised.");
                            match value.get("active_doc").and_then(Value::as_str) {
                                Some(path) if !path.is_empty() => {
                                    format!("{message}\n\nRevised document: {path}")
                                }
                                _ => message.to_string(),
                            }
                        }
                        "document_creation" => {
                            let topic = value
                                .get("topic")
                                .and_then(Value::as_str)
                                .unwrap_or("the requested topic");
                            match value.get("active_doc").and_then(Value::as_str) {
                                Some(path) if !path.is_empty() => {
                                    format!("Document created for {topic}.\n\nOutput: {path}")
                                }
                                _ => format!("Document created for {topic}."),
                            }
                        }
                        "analysis" => "The Python engine routed this request to document analysis. Use /analyze <path> to see the full report in this view.".to_string(),
                        "indexing" => "The Python engine routed this request to knowledge indexing. Use /index [path] to see the full report in this view.".to_string(),
                        other => format!(
                            "Backend returned an unsupported response type: {other}"
                        ),
                    };

                    if content.trim().is_empty() {
                        return Event::Error {
                            task_id,
                            message:
                                "The model returned an empty response. Check the model weights and daemon log."
                                    .to_string(),
                        };
                    }

                    let references = parse_references(value.get("references"));
                    let decision = parse_chat_decision(value.get("decision"));
                    Event::ChatReply {
                        task_id,
                        content,
                        references,
                        decision,
                    }
                }
                Err(RequestError::Cancelled) => Event::Cancelled { task_id },
                Err(RequestError::Message(message)) => Event::Error { task_id, message },
            }
        }
        Request::Daemon {
            task_id,
            action,
            payload,
            cancel,
        } => {
            let mut request = payload;
            if let Some(object) = request.as_object_mut() {
                object.insert("action".to_string(), Value::String(action));
            }
            match daemon_request(&request, &cancel, None) {
                Ok(value) => {
                    if let Some(message) = daemon_error(&value) {
                        Event::Error { task_id, message }
                    } else {
                        Event::DaemonResult { task_id, payload: value }
                    }
                }
                Err(RequestError::Cancelled) => Event::Cancelled { task_id },
                Err(RequestError::Message(message)) => Event::Error { task_id, message },
            }
        }
        Request::Python {
            task_id,
            args,
            cancel,
        } => match run_python_capture(&args, &cancel) {
            Ok((output, success)) => Event::CommandOutput {
                task_id,
                output,
                success,
            },
            Err(RequestError::Cancelled) => Event::Cancelled { task_id },
            Err(RequestError::Message(message)) => Event::Error { task_id, message },
        },
    }
}

fn daemon_error(value: &Value) -> Option<String> {
    if value.get("status").and_then(Value::as_str) == Some("error") {
        Some(
            value
                .get("message")
                .and_then(Value::as_str)
                .unwrap_or("The Filevo backend reported an unknown error.")
                .to_string(),
        )
    } else {
        None
    }
}

// ---------------------------------------------------------------------------
// Worker plumbing
// ---------------------------------------------------------------------------

#[derive(Debug)]
enum RequestError {
    Cancelled,
    Message(String),
}

fn handle_error(error: RequestError) -> String {
    match error {
        RequestError::Cancelled => "Cancelled".to_string(),
        RequestError::Message(message) => message,
    }
}

fn fetch_dashboard() -> Result<Dashboard, String> {
    let cancel = AtomicBool::new(false);
    let value = daemon_request(&json!({"action": "dashboard"}), &cancel, Some(Duration::from_secs(45)))
        .map_err(handle_error)?;
    if let Some(message) = daemon_error(&value) {
        return Err(message);
    }
    parse_dashboard(value)
}

fn run_python_capture(
    args: &[String],
    cancel: &AtomicBool,
) -> Result<(String, bool), RequestError> {
    let (python, mut command_args) = python_launcher();
    command_args.extend(args.iter().cloned());

    let temp_dir = if Path::new("/tmp/opencode").is_dir() {
        PathBuf::from("/tmp/opencode")
    } else {
        env::temp_dir()
    };
    static COUNTER: AtomicU64 = AtomicU64::new(0);
    let serial = COUNTER.fetch_add(1, Ordering::Relaxed);
    let base = format!("filevo_cli_{}_{}", std::process::id(), serial);
    let stdout_path = temp_dir.join(format!("{base}.out"));
    let stderr_path = temp_dir.join(format!("{base}.err"));

    let stdout_file = File::create(&stdout_path)
        .map_err(|e| RequestError::Message(format!("could not create capture file: {e}")))?;
    let stderr_file = File::create(&stderr_path)
        .map_err(|e| RequestError::Message(format!("could not create capture file: {e}")))?;

    let mut command = Command::new(&python);
    command
        .args(&command_args)
        .env("FILEVO_BOOTSTRAPPED", "1")
        .env("LD_LIBRARY_PATH", nix_library_path())
        .env("NO_COLOR", "1")
        .env("TERM", "dumb")
        .stdin(Stdio::null())
        .stdout(Stdio::from(stdout_file))
        .stderr(Stdio::from(stderr_file));

    let mut child = command.spawn().map_err(|e| {
        RequestError::Message(format!(
            "could not start the Python backend ({python}): {e}"
        ))
    })?;

    let status = wait_for_child(&mut child, cancel)?;

    let stdout = read_capture(&stdout_path);
    let stderr = read_capture(&stderr_path);
    let _ = fs::remove_file(&stdout_path);
    let _ = fs::remove_file(&stderr_path);

    let mut combined = String::new();
    if !stdout.trim().is_empty() {
        combined.push_str(&stdout);
    }
    if !stderr.trim().is_empty() {
        if !combined.is_empty() {
            combined.push_str("\n\n");
        }
        combined.push_str(&stderr);
    }
    let cleaned = normalise_capture(&combined);
    let success = status.map(|s| s.success()).unwrap_or(false);
    Ok((cleaned, success))
}

fn wait_for_child(child: &mut Child, cancel: &AtomicBool) -> Result<Option<std::process::ExitStatus>, RequestError> {
    loop {
        if cancel.load(Ordering::Relaxed) {
            let _ = child.kill();
            let _ = child.wait();
            return Err(RequestError::Cancelled);
        }
        match child.try_wait() {
            Ok(Some(status)) => return Ok(Some(status)),
            Ok(None) => thread::sleep(Duration::from_millis(80)),
            Err(error) => {
                return Err(RequestError::Message(format!(
                    "could not wait for the Python backend: {error}"
                )));
            }
        }
    }
}

fn read_capture(path: &Path) -> String {
    match fs::metadata(path) {
        Ok(meta) if meta.len() > MAX_CAPTURE_BYTES => {
            let bytes = fs::read(path).unwrap_or_default();
            let start = bytes.len().saturating_sub(MAX_CAPTURE_BYTES as usize);
            let mut text = String::from_utf8_lossy(&bytes[start..]).to_string();
            text.push_str("\n\n[output truncated]");
            text
        }
        _ => fs::read_to_string(path).unwrap_or_default(),
    }
}

pub fn normalise_capture(raw: &str) -> String {
    let clean = strip_ansi(raw);
    let clean = clean.replace("\r\n", "\n").replace('\r', "\n");
    let mut lines: Vec<&str> = clean.lines().collect();
    while lines.first().map(|l| l.trim().is_empty()).unwrap_or(false) {
        lines.remove(0);
    }
    while lines.last().map(|l| l.trim().is_empty()).unwrap_or(false) {
        lines.pop();
    }
    lines.join("\n")
}

/// Removes CSI, OSC and short ESC sequences.  Kept dependency-free because it
/// only needs to sanitise Rich's captured, non-interactive output.
pub fn strip_ansi(input: &str) -> String {
    let mut out = String::with_capacity(input.len());
    let mut chars = input.chars().peekable();
    while let Some(ch) = chars.next() {
        if ch != '\x1b' {
            out.push(ch);
            continue;
        }
        match chars.next() {
            Some('[') => {
                // CSI: parameters/intermediates until a final byte @..~
                for next in chars.by_ref() {
                    if ('@'..='~').contains(&next) {
                        break;
                    }
                }
            }
            Some(']') => {
                // OSC: terminated by BEL or ST (ESC \)
                let mut previous = '\0';
                for next in chars.by_ref() {
                    if next == '\x07' || (previous == '\x1b' && next == '\\') {
                        break;
                    }
                    previous = next;
                }
            }
            Some('(' | ')' | '#' | '%') => {
                let _ = chars.next();
            }
            Some(_) | None => {}
        }
    }
    out
}

// ---------------------------------------------------------------------------
// Daemon transport
// ---------------------------------------------------------------------------

fn home_dir() -> PathBuf {
    env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}

fn socket_path() -> PathBuf {
    home_dir().join(".filevo").join("filevo.sock")
}

fn pid_path() -> PathBuf {
    home_dir().join(".filevo").join("daemon.pid")
}

fn workspace_root() -> PathBuf {
    if let Ok(root) = env::var("FILEVO_WORKSPACE") {
        let root = PathBuf::from(root);
        if root.join("src").join("doc_gen").is_dir() {
            return root;
        }
    }
    let mut current = env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    loop {
        if current.join("src").join("doc_gen").is_dir() {
            return current;
        }
        if !current.pop() {
            break;
        }
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}

fn python_launcher() -> (PathBuf, Vec<String>) {
    let root = workspace_root();
    let venv_python = root.join(".venv").join("bin").join("python3");
    let script = root.join("src").join("doc_gen").join("filevo_cli.py");
    let python = if venv_python.is_file() {
        venv_python
    } else {
        PathBuf::from("python3")
    };
    (python, vec![script.to_string_lossy().to_string()])
}

fn daemon_launcher() -> (PathBuf, Vec<String>) {
    let root = workspace_root();
    let venv_python = root.join(".venv").join("bin").join("python3");
    let script = root.join("src").join("doc_gen").join("filevo_daemon.py");
    let python = if venv_python.is_file() {
        venv_python
    } else {
        PathBuf::from("python3")
    };
    (python, vec![script.to_string_lossy().to_string()])
}

/// NixOS needs both libstdc++ and the CUDA driver visible to the dynamic
/// loader *before* Python starts.  Setting LD_LIBRARY_PATH inside Python is too
/// late, so every child process is launched with this environment.
fn nix_library_path() -> String {
    static CACHED: OnceLock<String> = OnceLock::new();
    CACHED
        .get_or_init(|| {
            let mut paths: Vec<PathBuf> = Vec::new();

            if let Some(existing) = env::var_os("LD_LIBRARY_PATH") {
                for part in env::split_paths(&existing) {
                    if part.is_dir() {
                        paths.push(part);
                    }
                }
            }

            for known in [
                "/nix/store/z0n70pxyzi87why1bcq81zgd7b924nfj-gcc-15.2.0-lib/lib",
                "/nix/store/ss98wc4qpvf7f3p0xkv9f4hyhli5i1g5-nvidia-x11-595.71.05/lib",
                "/nix/store/1y0c7mfa4ak2js3mlxwwxz5j74gbhnld-ld-library-path/share/nix-ld/lib",
                "/run/opengl-driver/lib",
                "/run/current-system/sw/lib",
                "/usr/lib64",
                "/usr/lib",
                "/lib64",
                "/lib",
            ] {
                let path = PathBuf::from(known);
                if path.is_dir() {
                    paths.push(path);
                }
            }

            // Discover versioned Nix store paths when the pinned paths above
            // no longer exist after a system update.
            if let Ok(entries) = fs::read_dir("/nix/store") {
                let mut nix_paths: Vec<PathBuf> = entries
                    .flatten()
                    .filter_map(|entry| {
                        let name = entry.file_name().to_string_lossy().to_string();
                        let base = entry.path();
                        if name.contains("-gcc-") && name.ends_with("-lib") {
                            Some(base.join("lib"))
                        } else if name.contains("-nvidia-x11-") {
                            Some(base.join("lib"))
                        } else if name.contains("-ld-library-path") {
                            Some(base.join("share").join("nix-ld").join("lib"))
                        } else {
                            None
                        }
                    })
                    .filter(|path| path.is_dir())
                    .collect();
                nix_paths.sort();
                nix_paths.truncate(24);
                paths.extend(nix_paths);
            }

            let mut seen: Vec<PathBuf> = Vec::new();
            for path in paths {
                if !seen.contains(&path) {
                    seen.push(path);
                }
            }
            env::join_paths(seen)
                .map(|os| os.to_string_lossy().to_string())
                .unwrap_or_default()
        })
        .clone()
}

fn connect_daemon() -> Option<UnixStream> {
    UnixStream::connect(socket_path()).ok()
}

fn ensure_daemon(cancel: &AtomicBool) -> Result<UnixStream, RequestError> {
    if let Some(mut stream) = connect_daemon() {
        match ping(&mut stream) {
            Ok(protocol) if protocol >= DAEMON_PROTOCOL => return Ok(stream),
            Ok(_) | Err(_) => {
                drop(stream);
                restart_stale_daemon();
            }
        }
    }

    let (python, args) = daemon_launcher();
    if !Path::new(&args[0]).is_file() {
        return Err(RequestError::Message(format!(
            "Filevo backend script not found at {}",
            args[0]
        )));
    }

    let log_path = home_dir().join(".filevo").join("daemon.log");
    if let Some(parent) = log_path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    let log_file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .map_err(|e| RequestError::Message(format!("could not open daemon log: {e}")))?;
    let stderr = log_file
        .try_clone()
        .map_err(|e| RequestError::Message(format!("could not clone daemon log handle: {e}")))?;

    let mut command = Command::new(&python);
    command
        .args(&args)
        .env("FILEVO_BOOTSTRAPPED", "1")
        .env("LD_LIBRARY_PATH", nix_library_path())
        .stdin(Stdio::null())
        .stdout(Stdio::from(log_file))
        .stderr(Stdio::from(stderr));

    let mut child = command.spawn().map_err(|e| {
        RequestError::Message(format!(
            "could not start the Filevo daemon ({python}): {e}"
        ))
    })?;

    let deadline = Instant::now() + Duration::from_secs(20);
    while Instant::now() < deadline {
        if cancel.load(Ordering::Relaxed) {
            let _ = child.kill();
            return Err(RequestError::Cancelled);
        }
        if let Ok(Some(status)) = child.try_wait() {
            return Err(RequestError::Message(format!(
                "Filevo daemon exited during startup ({status}). See {}.",
                log_path.display()
            )));
        }
        if let Some(mut stream) = connect_daemon() {
            match ping(&mut stream) {
                Ok(protocol) if protocol >= DAEMON_PROTOCOL => return Ok(stream),
                _ => {
                    let _ = child.kill();
                    return Err(RequestError::Message(
                        "Filevo daemon started but does not speak dashboard protocol 2. Restart the daemon."
                            .to_string(),
                    ));
                }
            }
        }
        thread::sleep(Duration::from_millis(100));
    }

    let _ = child.kill();
    Err(RequestError::Message(format!(
        "Timed out waiting for the Filevo daemon. See {}.",
        log_path.display()
    )))
}

fn restart_stale_daemon() {
    let Ok(pid_text) = fs::read_to_string(pid_path()) else {
        let _ = fs::remove_file(socket_path());
        return;
    };
    let Ok(pid) = pid_text.trim().parse::<u32>() else {
        let _ = fs::remove_file(socket_path());
        return;
    };
    let cmdline_path = PathBuf::from(format!("/proc/{pid}/cmdline"));
    let Ok(cmdline) = fs::read(&cmdline_path) else {
        let _ = fs::remove_file(socket_path());
        return;
    };
    let cmdline = String::from_utf8_lossy(&cmdline);
    if !cmdline.contains("filevo_daemon.py") {
        // Never kill a process we cannot positively identify.
        let _ = fs::remove_file(socket_path());
        return;
    }
    let _ = Command::new("kill")
        .arg("-TERM")
        .arg(pid.to_string())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();
    let deadline = Instant::now() + Duration::from_secs(2);
    while Instant::now() < deadline {
        if UnixStream::connect(socket_path()).is_err() {
            break;
        }
        thread::sleep(Duration::from_millis(80));
    }
    let _ = fs::remove_file(socket_path());
}

fn ping(stream: &mut UnixStream) -> Result<u32, String> {
    stream
        .set_read_timeout(Some(Duration::from_secs(5)))
        .map_err(|e| e.to_string())?;
    stream
        .set_write_timeout(Some(Duration::from_secs(5)))
        .map_err(|e| e.to_string())?;
    let payload = b"{\"action\":\"ping\"}\n";
    stream.write_all(payload).map_err(|e| e.to_string())?;
    stream.flush().map_err(|e| e.to_string())?;
    let mut raw = Vec::new();
    let mut buffer = [0u8; 4096];
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        if Instant::now() >= deadline {
            return Err("daemon ping timed out".to_string());
        }
        match stream.read(&mut buffer) {
            Ok(0) => return Err("daemon closed the ping connection".to_string()),
            Ok(n) => {
                raw.extend_from_slice(&buffer[..n]);
                if raw.contains(&b'\n') {
                    break;
                }
            }
            Err(error)
                if matches!(
                    error.kind(),
                    io::ErrorKind::WouldBlock | io::ErrorKind::TimedOut | io::ErrorKind::Interrupted
                ) =>
            {
                continue;
            }
            Err(error) => return Err(error.to_string()),
        }
    }
    let value: Value =
        serde_json::from_slice(&raw).map_err(|e| format!("invalid daemon ping response: {e}"))?;
    value
        .get("protocol")
        .and_then(Value::as_u64)
        .map(|v| v as u32)
        .ok_or_else(|| "daemon did not advertise a dashboard protocol".to_string())
}

fn daemon_request(
    request: &Value,
    cancel: &AtomicBool,
    overall_timeout: Option<Duration>,
) -> Result<Value, RequestError> {
    let mut stream = ensure_daemon(cancel)?;
    stream
        .set_read_timeout(Some(Duration::from_millis(200)))
        .map_err(|e| RequestError::Message(e.to_string()))?;
    stream
        .set_write_timeout(Some(Duration::from_secs(10)))
        .map_err(|e| RequestError::Message(e.to_string()))?;

    let mut payload =
        serde_json::to_vec(request).map_err(|e| RequestError::Message(e.to_string()))?;
    payload.push(b'\n');
    stream
        .write_all(&payload)
        .map_err(|e| RequestError::Message(format!("could not write to daemon: {e}")))?;
    stream
        .flush()
        .map_err(|e| RequestError::Message(format!("could not flush daemon request: {e}")))?;

    let mut raw = Vec::new();
    let mut buffer = [0u8; 16384];
    let deadline = overall_timeout.map(|timeout| Instant::now() + timeout);

    loop {
        if cancel.load(Ordering::Relaxed) {
            return Err(RequestError::Cancelled);
        }
        if let Some(deadline) = deadline {
            if Instant::now() >= deadline {
                return Err(RequestError::Message(
                    "the Filevo daemon did not answer in time".to_string(),
                ));
            }
        }
        match stream.read(&mut buffer) {
            Ok(0) => {
                return Err(RequestError::Message(
                    "the Filevo daemon closed the connection before replying".to_string(),
                ));
            }
            Ok(n) => {
                raw.extend_from_slice(&buffer[..n]);
                if raw.contains(&b'\n') {
                    break;
                }
            }
            Err(error)
                if matches!(
                    error.kind(),
                    io::ErrorKind::WouldBlock | io::ErrorKind::TimedOut | io::ErrorKind::Interrupted
                ) =>
            {
                continue;
            }
            Err(error) => {
                return Err(RequestError::Message(format!(
                    "could not read from daemon: {error}"
                )));
            }
        }
    }

    let first_line = raw.split(|byte| *byte == b'\n').next().unwrap_or(&[]);
    serde_json::from_slice(first_line).map_err(|e| {
        RequestError::Message(format!("invalid JSON from Filevo daemon: {e}"))
    })
}

// ---------------------------------------------------------------------------
// JSON -> domain conversion
// ---------------------------------------------------------------------------

#[derive(Debug, Deserialize, Default)]
struct RawDashboard {
    #[serde(default)]
    generated_at: Option<f64>,
    #[serde(default)]
    model: RawModel,
    #[serde(default)]
    session: RawSession,
    #[serde(default)]
    decision: RawDecision,
    #[serde(default)]
    references: Vec<RawReference>,
    #[serde(default)]
    documents: Vec<RawDocument>,
    #[serde(default)]
    turns: Vec<RawTurn>,
    #[serde(default)]
    telemetry: RawTelemetry,
    #[serde(default)]
    policy: RawPolicy,
    #[serde(default)]
    errors: Vec<String>,
}

#[derive(Debug, Deserialize, Default)]
struct RawModel {
    #[serde(default)]
    id: String,
    #[serde(default)]
    short: String,
    #[serde(default)]
    device: String,
    #[serde(default)]
    loaded: bool,
    #[serde(default)]
    load_error: Option<String>,
    #[serde(default)]
    context_tokens: Option<u64>,
}

#[derive(Debug, Deserialize, Default)]
struct RawSession {
    #[serde(default)]
    files_indexed: u64,
    #[serde(default)]
    docs_created: u64,
    #[serde(default)]
    policy_status: String,
    #[serde(default)]
    policy_episodes: u64,
    #[serde(default)]
    policy_baseline: f64,
    #[serde(default)]
    memory_used: u64,
    #[serde(default)]
    memory_limit: u64,
}

#[derive(Debug, Deserialize, Default)]
struct RawDecision {
    #[serde(default)]
    available: bool,
    #[serde(default)]
    probabilities: HashMap<String, f64>,
    #[serde(default)]
    confidence: Option<f64>,
    #[serde(default)]
    entropy: Option<f64>,
    #[serde(default)]
    risk: Option<String>,
    #[serde(default)]
    source: String,
}

#[derive(Debug, Deserialize, Default)]
struct RawReference {
    #[serde(default)]
    url: String,
    #[serde(default)]
    title: String,
    #[serde(default)]
    domain: String,
}

#[derive(Debug, Deserialize, Default)]
struct RawDocument {
    #[serde(default)]
    name: String,
    #[serde(default)]
    path: String,
    #[serde(default)]
    size: u64,
    #[serde(default)]
    modified: Option<f64>,
}

#[derive(Debug, Deserialize, Default)]
struct RawTurn {
    #[serde(default)]
    role: String,
    #[serde(default)]
    content: String,
    #[serde(default)]
    timestamp: f64,
}

#[derive(Debug, Deserialize, Default)]
struct RawTelemetry {
    #[serde(default)]
    gpu: Option<RawGpu>,
    #[serde(default)]
    disk: Option<RawDisk>,
    #[serde(default)]
    system_memory: Option<RawMemory>,
    #[serde(default)]
    model_ready: bool,
    #[serde(default)]
    web: RawWeb,
}

#[derive(Debug, Deserialize, Default)]
struct RawGpu {
    #[serde(default)]
    name: String,
    #[serde(default)]
    utilization: f64,
    #[serde(default)]
    memory_used_mb: f64,
    #[serde(default)]
    memory_total_mb: f64,
}

#[derive(Debug, Deserialize, Default)]
struct RawDisk {
    #[serde(default)]
    path: String,
    #[serde(default)]
    used: u64,
    #[serde(default)]
    total: u64,
    #[serde(default)]
    free: u64,
}

#[derive(Debug, Deserialize, Default)]
struct RawMemory {
    #[serde(default)]
    used: u64,
    #[serde(default)]
    total: u64,
}

#[derive(Debug, Deserialize, Default)]
struct RawWeb {
    #[serde(default)]
    enabled: bool,
    #[serde(default)]
    live_references: u64,
    #[serde(default)]
    last_result: String,
}

#[derive(Debug, Deserialize, Default)]
struct RawPolicy {
    #[serde(default)]
    episodes: u64,
    #[serde(default)]
    baseline: f64,
    #[serde(default)]
    temperature: f64,
    #[serde(default)]
    archetype_distribution: HashMap<String, f64>,
    #[serde(default)]
    font_distribution: HashMap<String, f64>,
}

fn parse_dashboard(value: Value) -> Result<Dashboard, String> {
    let raw: RawDashboard =
        serde_json::from_value(value).map_err(|e| format!("invalid dashboard payload: {e}"))?;

    let decision = Decision::from_map(
        raw.decision.available,
        &raw.decision.probabilities,
        raw.decision.confidence,
        raw.decision.entropy,
        raw.decision.risk.as_deref(),
        raw.decision.source,
    );

    let references = raw
        .references
        .into_iter()
        .filter_map(|reference| {
            if reference.url.trim().is_empty() && reference.title.trim().is_empty() {
                return None;
            }
            Some(ReferenceInfo {
                url: reference.url,
                title: if reference.title.trim().is_empty() {
                    reference.domain.clone()
                } else {
                    reference.title
                },
                domain: if reference.domain.trim().is_empty() {
                    "unknown".to_string()
                } else {
                    reference.domain
                },
            })
        })
        .collect();

    let documents = raw
        .documents
        .into_iter()
        .map(|document| DocumentInfo {
            name: document.name,
            path: document.path,
            size_bytes: document.size,
            modified: document.modified.map(|value| value as i64),
        })
        .collect();

    let mut archetypes: Vec<(String, f64)> = raw.policy.archetype_distribution.into_iter().collect();
    archetypes.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    let mut fonts: Vec<(String, f64)> = raw.policy.font_distribution.into_iter().collect();
    fonts.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

    let turns = raw
        .turns
        .into_iter()
        .filter_map(|turn| {
            let role = match turn.role.as_str() {
                "user" => Role::User,
                "assistant" => Role::Assistant,
                _ => return None,
            };
            Some(TurnSnapshot {
                role,
                content: turn.content,
                timestamp: turn.timestamp,
            })
        })
        .collect();

    Ok(Dashboard {
        model: ModelInfo {
            id: raw.model.id,
            short: raw.model.short,
            device: raw.model.device,
            loaded: raw.model.loaded,
            load_error: raw.model.load_error,
            context_tokens: raw.model.context_tokens,
        },
        session: SessionInfo {
            files_indexed: raw.session.files_indexed,
            docs_created: raw.session.docs_created,
            policy_status: raw.session.policy_status,
            policy_episodes: raw.session.policy_episodes,
            policy_baseline: raw.session.policy_baseline,
            memory_used: raw.session.memory_used,
            memory_limit: raw.session.memory_limit,
        },
        decision,
        references,
        documents,
        telemetry: Telemetry {
            gpu: raw.telemetry.gpu.map(|gpu| GpuInfo {
                name: gpu.name,
                utilization: gpu.utilization,
                memory_used_mb: gpu.memory_used_mb,
                memory_total_mb: gpu.memory_total_mb,
            }),
            disk: raw.telemetry.disk.map(|disk| DiskInfo {
                path: disk.path,
                used: disk.used,
                total: disk.total,
                free: disk.free,
            }),
            system_memory: raw.telemetry.system_memory.map(|memory| SystemMemory {
                used: memory.used,
                total: memory.total,
            }),
            model_ready: raw.telemetry.model_ready,
            web: WebStatus {
                enabled: raw.telemetry.web.enabled,
                live_references: raw.telemetry.web.live_references,
                last_result: raw.telemetry.web.last_result,
            },
        },
        policy: PolicyTelemetry {
            episodes: raw.policy.episodes,
            baseline: raw.policy.baseline,
            temperature: raw.policy.temperature,
            archetypes,
            fonts,
        },
        turns,
        errors: raw.errors,
        generated_at: raw.generated_at.map(|value| value as i64),
    })
}

fn parse_references(value: Option<&Value>) -> Vec<ReferenceInfo> {
    let Some(Value::Array(items)) = value else {
        return Vec::new();
    };
    items
        .iter()
        .filter_map(|item| match item {
            Value::String(url) => {
                let domain = url
                    .split("://")
                    .nth(1)
                    .unwrap_or(url)
                    .split('/')
                    .next()
                    .unwrap_or("")
                    .trim_start_matches("www.")
                    .to_string();
                Some(ReferenceInfo {
                    url: url.clone(),
                    title: if domain.is_empty() {
                        url.clone()
                    } else {
                        domain.clone()
                    },
                    domain,
                })
            }
            Value::Object(map) => {
                let url = map
                    .get("url")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string();
                let domain = map
                    .get("domain")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string();
                let title = map
                    .get("title")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string();
                if url.is_empty() && title.is_empty() {
                    return None;
                }
                Some(ReferenceInfo {
                    title: if title.is_empty() {
                        domain.clone()
                    } else {
                        title
                    },
                    domain,
                    url,
                })
            }
            _ => None,
        })
        .collect()
}

fn parse_chat_decision(value: Option<&Value>) -> Option<Decision> {
    let object = value?.as_object()?;
    let probabilities = object
        .get("probabilities")
        .and_then(Value::as_object)
        .map(|map| {
            map.iter()
                .filter_map(|(key, value)| value.as_f64().map(|v| (key.clone(), v)))
                .collect::<HashMap<String, f64>>()
        })
        .unwrap_or_default();
    if probabilities.is_empty() {
        return None;
    }
    let confidence = object.get("confidence").and_then(Value::as_f64);
    let entropy = object.get("entropy").and_then(Value::as_f64);
    let risk = object.get("risk").and_then(Value::as_str);
    Some(Decision::from_map(
        true,
        &probabilities,
        confidence,
        entropy,
        risk,
        "last_intent_evaluation",
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ansi_stripping_handles_colour_and_osc() {
        let input = "\x1b[38;2;0;213;238mhello\x1b[0m \x1b]0;title\x07world";
        assert_eq!(strip_ansi(input), "hello world");
    }

    #[test]
    fn dashboard_payload_is_parsed_without_inventing_values() {
        let payload = json!({
            "status": "ok",
            "generated_at": 1_793_280_000.0,
            "model": {"id": "org/Model", "short": "Model", "device": "cuda", "loaded": false, "context_tokens": null},
            "session": {"files_indexed": 2, "docs_created": 1, "policy_status": "Trained", "memory_used": 3, "memory_limit": 8},
            "decision": {
                "available": false,
                "probabilities": {"CONVERSATION": 0.71},
                "confidence": 0.713,
                "entropy": 0.58,
                "risk": "LOW",
                "source": "backend_default_prior"
            },
            "references": [{"url": "https://example.com/a-b", "title": "a b", "domain": "example.com"}],
            "documents": [{"name": "a.docx", "path": "/tmp/a.docx", "size": 1234, "modified": 1_700_000_000.0}],
            "turns": [{"role": "user", "content": "hi", "timestamp": 1.0}],
            "telemetry": {
                "gpu": null,
                "disk": {"path": "/home", "used": 10, "total": 100, "free": 90},
                "system_memory": null,
                "model_ready": false,
                "web": {"enabled": true, "live_references": 0, "last_result": "idle"}
            },
            "policy": {"episodes": 3, "baseline": 0.5, "temperature": 1.0, "archetype_distribution": {"A": 0.7}, "font_distribution": {}},
            "errors": []
        });
        let dashboard = parse_dashboard(payload).expect("dashboard should parse");
        assert_eq!(dashboard.model.short, "Model");
        assert!(!dashboard.decision.available);
        assert!(dashboard.decision.validate().is_err());
        assert_eq!(dashboard.references[0].domain, "example.com");
        assert_eq!(dashboard.documents[0].size_bytes, 1234);
        assert_eq!(dashboard.policy.archetypes[0].0, "A");
    }

    #[test]
    fn chat_decision_is_live() {
        let payload = json!({
            "probabilities": {
                "DOCUMENT_CREATION": 0.12,
                "CONVERSATION": 0.71,
                "DOCUMENT_ANALYSIS": 0.08,
                "KNOWLEDGE_INDEXING": 0.05,
                "POLICY_TRAIN": 0.04
            },
            "confidence": 0.71,
            "entropy": 0.58,
            "risk": "LOW"
        });
        let decision = parse_chat_decision(Some(&payload)).expect("decision");
        assert!(decision.validate().is_ok());
        assert_eq!(decision.risk, Risk::Low);
    }

    #[test]
    fn normalisation_removes_carriage_returns() {
        assert_eq!(normalise_capture("\r\nhello\r\n\r\n"), "hello");
    }
}
