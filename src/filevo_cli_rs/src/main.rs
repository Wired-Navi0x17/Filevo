//! Filevo High-Performance Rust Native CLI Interface.
//!
//! Provides a responsive, colorized interactive terminal REPL with:
//! - Antigravity/OpenCode dark theme aesthetics and ANSI truecolor formatting
//! - Bottom-docked status box and prompt window matching reference layout
//! - Two-track dispatch: deterministic slash commands + natural language model bridge
//! - Persistent command history (~/.filevo/history_rs)
//! - Direct argument execution (`filevo create ...`, `filevo status`, etc.)
//! - Subprocess bridge to Python document intelligence & RLCD engine

use std::env;
use std::fs::{self, OpenOptions};
use std::io::{self, BufRead, BufReader, Write};
use std::os::unix::net::UnixStream;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::Duration;
use serde_json::{json, Value};

// -------------------------------------------------------------------------
// ANSI Color Codes (Tokyo Night / Antigravity Dark Theme)
// -------------------------------------------------------------------------
const RESET: &str = "\x1b[0m";
const BOLD: &str = "\x1b[1m";
const DIM: &str = "\x1b[2m";
const CYAN: &str = "\x1b[38;2;122;162;247m";
const AMBER: &str = "\x1b[38;2;224;175;104m";
const RED: &str = "\x1b[38;2;247;118;142m";
const SLATE: &str = "\x1b[38;2;86;95;137m";

const BANNER: &str = r#"╭─ FILEVO v1.0.0 (Rust Engine Edition) ────────────────────────────────────────╮
│   ███████╗██╗██╗     ███████╗██╗   ██╗ ██████╗                               │
│   ██╔════╝██║██║     ██╔════╝██║   ██║██╔═══██╗                              │
│   █████╗  ██║██║     █████╗  ██║   ██║██║   ██║                              │
│   ██╔══╝  ██║██║     ██╔══╝  ╚██╗ ██╔╝██║   ██║                              │
│   ██║     ██║███████╗███████╗ ╚████╔╝ ╚██████╔╝                              │
│   ╚═╝     ╚═╝╚══════╝╚══════╝  ╚═══╝   ╚═════╝                               │
│   High-Performance Rust CLI • Conversational Document Intelligence & RLCD     │
│   Model: SmolLM2-1.7B-Instruct • PyTorch CUDA RTX 4090 • Live Web Grounding   │
╰──────── Type commands (/help) or chat naturally. Use @file for attachments. ─╯"#;

fn find_workspace_root() -> PathBuf {
    let mut cur = env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    loop {
        if cur.join("src").join("doc_gen").exists() {
            return cur;
        }
        if !cur.pop() {
            break;
        }
    }
    // Fallback default workspace path
    PathBuf::from("/home/l41n-pr0t0/Workspace/University/Semester 3/CS2227 - AI and ML/CIE")
}

fn get_python_launcher() -> (PathBuf, Vec<String>) {
    let root = find_workspace_root();
    let venv_py = root.join(".venv").join("bin").join("python3");
    let script = root.join("src").join("doc_gen").join("filevo_cli.py");
    let py = if venv_py.exists() { venv_py } else { PathBuf::from("python3") };
    (py, vec![script.to_string_lossy().to_string()])
}

fn get_daemon_launcher() -> (PathBuf, Vec<String>) {
    let root = find_workspace_root();
    let venv_py = root.join(".venv").join("bin").join("python3");
    let script = root.join("src").join("doc_gen").join("filevo_daemon.py");
    let py = if venv_py.exists() { venv_py } else { PathBuf::from("python3") };
    (py, vec![script.to_string_lossy().to_string()])
}

fn get_socket_path() -> PathBuf {
    let home = env::var("HOME").unwrap_or_else(|_| ".".into());
    Path::new(&home).join(".filevo").join("filevo.sock")
}

fn connect_daemon() -> Option<UnixStream> {
    let sock = get_socket_path();
    UnixStream::connect(&sock).ok()
}

fn get_nixos_ld_paths() -> String {
    let mut paths = Vec::new();
    for p in &["/run/opengl-driver/lib", "/run/current-system/sw/lib"] {
        if Path::new(p).is_dir() {
            paths.push(p.to_string());
        }
    }
    if let Ok(entries) = std::fs::read_dir("/nix/store") {
        for entry in entries.flatten() {
            let name = entry.file_name().to_string_lossy().to_string();
            if (name.contains("-gcc-") && name.ends_with("-lib"))
                || name.contains("-nvidia-x11-")
                || name.contains("-ld-library-path")
            {
                let lib_path = entry.path().join("lib");
                if lib_path.is_dir() {
                    paths.push(lib_path.to_string_lossy().to_string());
                }
                let share_path = entry.path().join("share/nix-ld/lib");
                if share_path.is_dir() {
                    paths.push(share_path.to_string_lossy().to_string());
                }
            }
        }
    }
    let cur_ld = env::var("LD_LIBRARY_PATH").unwrap_or_default();
    if !paths.is_empty() {
        let extra = paths.join(":");
        if cur_ld.is_empty() { extra } else { format!("{}:{}", extra, cur_ld) }
    } else {
        cur_ld
    }
}

fn ensure_daemon() -> Result<UnixStream, String> {
    if let Some(stream) = connect_daemon() {
        return Ok(stream);
    }

    let (py, args) = get_daemon_launcher();
    let ld_path = get_nixos_ld_paths();

    let mut cmd = Command::new(&py);
    cmd.args(&args);
    cmd.env("LD_LIBRARY_PATH", ld_path);
    cmd.env("FILEVO_BOOTSTRAPPED", "1");
    cmd.stdout(Stdio::null());
    cmd.stderr(Stdio::null());
    cmd.stdin(Stdio::null());

    if let Ok(_child) = cmd.spawn() {
        for _ in 0..25 {
            std::thread::sleep(Duration::from_millis(100));
            if let Some(stream) = connect_daemon() {
                return Ok(stream);
            }
        }
    }

    Err("Could not connect to Filevo persistent daemon".to_string())
}

fn send_ipc_request(req: Value) -> Result<Value, String> {
    let mut stream = ensure_daemon()?;
    let mut payload = serde_json::to_string(&req).map_err(|e| e.to_string())?;
    payload.push('\n');
    stream.write_all(payload.as_bytes()).map_err(|e| e.to_string())?;
    stream.flush().map_err(|e| e.to_string())?;

    let mut reader = BufReader::new(stream);
    let mut line = String::new();
    reader.read_line(&mut line).map_err(|e| e.to_string())?;
    serde_json::from_str(&line).map_err(|e| format!("Invalid JSON response: {e}"))
}

fn run_python_backend(args: &[&str]) -> bool {
    let (py, base_args) = get_python_launcher();
    let ld_path = get_nixos_ld_paths();

    let mut cmd = Command::new(&py);
    cmd.args(&base_args);
    cmd.args(args);
    cmd.env("LD_LIBRARY_PATH", ld_path);
    cmd.env("FILEVO_BOOTSTRAPPED", "1");
    cmd.stdout(Stdio::inherit());
    cmd.stderr(Stdio::inherit());
    cmd.stdin(Stdio::inherit());

    match cmd.status() {
        Ok(status) => status.success(),
        Err(e) => {
            eprintln!("{RED}✗ Failed to execute Filevo Python backend: {e}{RESET}");
            false
        }
    }
}

fn render_bottom_prompt_box() {
    println!("{SLATE}│ {AMBER}Plan{RESET}{SLATE} · {CYAN}SmolLM2-1.7B-Instruct{RESET}{SLATE} · Personal / Filevo (Rust Frontend){RESET}");
    println!("{SLATE}│ /CIE:main · 16.4k (5%) · {DIM}ctrl+c cancel · tab complete · /help{RESET}");
}

fn print_help() {
    println!("\n{BOLD}{CYAN}Available Filevo Commands (Rust CLI Native):{RESET}");
    println!("  {BOLD}{AMBER}/help{RESET}        {SLATE}│{RESET} Displays all available commands and keyboard shortcuts");
    println!("  {BOLD}{AMBER}/create{RESET}      {SLATE}│{RESET} Creates a calibrated DOCX document (/create <topic>)");
    println!("  {BOLD}{AMBER}/revise{RESET}      {SLATE}│{RESET} Revises and versions active document (/revise <instruction>)");
    println!("  {BOLD}{AMBER}/research{RESET}    {SLATE}│{RESET} Researches a topic across web and live sources (/research <topic>)");
    println!("  {BOLD}{AMBER}/analyze{RESET}     {SLATE}│{RESET} Analyzes a document, collection, or codebase (/analyze <path>)");
    println!("  {BOLD}{AMBER}/index{RESET}       {SLATE}│{RESET} Indexes DOCX files into persistent metadata cache (/index [path])");
    println!("  {BOLD}{AMBER}/train{RESET}       {SLATE}│{RESET} Runs learning workflow or live streaming (/train [args])");
    println!("  {BOLD}{AMBER}/feedback{RESET}    {SLATE}│{RESET} Records feedback on active generation (/feedback [+1.0|-0.5])");
    println!("  {BOLD}{AMBER}/dataset{RESET}     {SLATE}│{RESET} Builds leakage-free DOCX training dataset (/dataset [dir])");
    println!("  {BOLD}{AMBER}/benchmark{RESET}   {SLATE}│{RESET} Benchmarks candidate local models on 16GB VRAM (/benchmark)");
    println!("  {BOLD}{AMBER}/model{RESET}       {SLATE}│{RESET} Reports active model, policy weights, and probabilities");
    println!("  {BOLD}{AMBER}/status{RESET}      {SLATE}│{RESET} Reports system, knowledge base, and memory status");
    println!("  {BOLD}{AMBER}/clear{RESET}       {SLATE}│{RESET} Clears terminal screen and redraws Antigravity banner");
    println!("  {BOLD}{AMBER}/exit{RESET}        {SLATE}│{RESET} Exits the application");
    println!("\n{DIM}Natural Language: Type free text or mention files with @filename.{RESET}\n");
}

fn append_history(line: &str) {
    if let Ok(home) = env::var("HOME") {
        let hist_dir = Path::new(&home).join(".filevo");
        let _ = fs::create_dir_all(&hist_dir);
        let hist_file = hist_dir.join("history_rs");
        if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(hist_file) {
            let _ = writeln!(f, "{}", line);
        }
    }
}

fn clear_screen() {
    print!("\x1b[2J\x1b[H");
    let _ = io::stdout().flush();
    println!("{}\n", BANNER);
}

fn run_repl() {
    clear_screen();
    let stdin = io::stdin();
    let mut reader = stdin.lock();

    loop {
        render_bottom_prompt_box();
        print!("{BOLD}{CYAN}filevo>{RESET} ");
        let _ = io::stdout().flush();

        let mut line = String::new();
        match reader.read_line(&mut line) {
            Ok(0) => {
                println!("\n{BOLD}{CYAN}Goodbye! 👋{RESET}\n");
                break;
            }
            Ok(_) => {
                let input = line.trim();
                if input.is_empty() {
                    continue;
                }
                append_history(input);

                if input.starts_with('/') {
                    let parts: Vec<&str> = input.splitn(2, ' ').collect();
                    let cmd = parts[0];
                    let arg = if parts.len() > 1 { parts[1].trim() } else { "" };

                    match cmd {
                        "/help" => print_help(),
                        "/clear" => clear_screen(),
                        "/exit" | "/quit" | "/q" => {
                            println!("\n{BOLD}{CYAN}Goodbye! 👋{RESET}\n");
                            break;
                        }
                        "/create" => {
                            if arg.is_empty() {
                                println!("{AMBER}Please specify a topic. Example: /create Microservices Architecture{RESET}");
                            } else {
                                if let Ok(resp) = send_ipc_request(json!({"action": "create", "request": arg})) {
                                    if let Some(doc) = resp.get("active_doc").and_then(|v| v.as_str()) {
                                        println!("\n{AMBER}✓ Document Created:{RESET} {doc}");
                                    }
                                } else {
                                    run_python_backend(&["create", arg]);
                                }
                            }
                        }
                        "/revise" => {
                            if arg.is_empty() {
                                println!("{AMBER}Please specify revision instructions. Example: /revise make it more formal{RESET}");
                            } else {
                                if let Ok(resp) = send_ipc_request(json!({"action": "revise", "instruction": arg})) {
                                    if let Some(doc) = resp.get("active_doc").and_then(|v| v.as_str()) {
                                        println!("\n{AMBER}✓ Document Revised:{RESET} {doc}");
                                    }
                                } else {
                                    run_python_backend(&["revise", arg]);
                                }
                            }
                        }
                        "/research" => {
                            if arg.is_empty() {
                                println!("{AMBER}Please specify a topic. Example: /research Quantum Computing{RESET}");
                            } else {
                                run_python_backend(&["research", arg]);
                            }
                        }
                        "/analyze" => {
                            let path = if arg.is_empty() { "." } else { arg };
                            run_python_backend(&["analyze", path]);
                        }
                        "/index" => {
                            let path = if arg.is_empty() { "." } else { arg };
                            run_python_backend(&["index", path]);
                        }
                        "/train" => {
                            if arg.is_empty() {
                                run_python_backend(&["train", "corpus"]);
                            } else {
                                let train_parts: Vec<&str> = arg.split_whitespace().collect();
                                let mut full_args = vec!["train"];
                                full_args.extend(train_parts);
                                run_python_backend(&full_args);
                            }
                        }
                        "/feedback" => {
                            let reward = if arg.is_empty() { "+1.0" } else { arg };
                            let _ = send_ipc_request(json!({"action": "feedback", "reward": reward}));
                            run_python_backend(&["feedback", reward]);
                        }
                        "/dataset" => {
                            let path = if arg.is_empty() { "." } else { arg };
                            run_python_backend(&["dataset", path]);
                        }
                        "/benchmark" => {
                            run_python_backend(&["benchmark"]);
                        }
                        "/model" => {
                            run_python_backend(&["model"]);
                        }
                        "/status" => {
                            run_python_backend(&["status"]);
                        }
                        _ => {
                            println!("{RED}✗ Unknown command: {cmd}{RESET}");
                            println!("{DIM}Type /help for available commands.{RESET}\n");
                        }
                    }
                } else {
                    // Route natural language input through persistent daemon IPC
                    match send_ipc_request(json!({"action": "chat", "text": input})) {
                        Ok(resp) => {
                            let r_type = resp.get("type").and_then(|v| v.as_str()).unwrap_or("");
                            if r_type == "chat_reply" {
                                let text = resp.get("response").and_then(|v| v.as_str()).unwrap_or("");
                                println!("\n{CYAN}> {RESET}{BOLD}Filevo{RESET}   , _ ,    {}", text.replace("\n", "\n                      "));
                                println!("             (o,o)    ");
                                println!("             / ' \" \\  ");
                                println!("              -\"-\"-   \n");
                            } else if r_type == "revision" {
                                let msg = resp.get("message").and_then(|v| v.as_str()).unwrap_or("Document revised");
                                println!("\n{CYAN}> {RESET}{BOLD}Filevo{RESET}   , _ ,    {}", msg);
                                println!("             (o,o)    ");
                                println!("             / ' \" \\  ");
                                println!("              -\"-\"-   \n");
                                if let Some(doc) = resp.get("active_doc").and_then(|v| v.as_str()) {
                                    println!("{AMBER}✓ Revised Document:{RESET} {doc}");
                                }
                            } else if r_type == "document_creation" {
                                if let Some(doc) = resp.get("active_doc").and_then(|v| v.as_str()) {
                                    println!("\n{AMBER}✓ Document Created:{RESET} {doc}");
                                }
                            }
                        }
                        Err(_) => {
                            run_python_backend(&["chat", input]);
                        }
                    }
                }
                println!();
            }
            Err(_) => break,
        }
    }
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() > 1 {
        // Direct execution mode: filevo-cli <command> [args...]
        let cmd = &args[1];
        let sub_args: Vec<&str> = args[2..].iter().map(|s| s.as_str()).collect();

        match cmd.as_str() {
            "help" | "--help" | "-h" => print_help(),
            "version" | "--version" | "-v" => println!("filevo-cli 1.0.0 (Rust Edition)"),
            "create" => {
                let topic = sub_args.join(" ");
                run_python_backend(&["create", &topic]);
            }
            "chat" => {
                let msg = sub_args.join(" ");
                run_python_backend(&["chat", &msg]);
            }
            "revise" => {
                let inst = sub_args.join(" ");
                run_python_backend(&["revise", &inst]);
            }
            "research" => {
                let topic = sub_args.join(" ");
                run_python_backend(&["research", &topic]);
            }
            "analyze" => {
                let path = sub_args.first().copied().unwrap_or(".");
                run_python_backend(&["analyze", path]);
            }
            "index" => {
                let path = sub_args.first().copied().unwrap_or(".");
                run_python_backend(&["index", path]);
            }
            "train" => {
                let mut full_args = vec!["train"];
                full_args.extend(sub_args);
                run_python_backend(&full_args);
            }
            "feedback" => {
                let reward = sub_args.first().copied().unwrap_or("+1.0");
                run_python_backend(&["feedback", reward]);
            }
            "dataset" => {
                let path = sub_args.first().copied().unwrap_or(".");
                run_python_backend(&["dataset", path]);
            }
            "benchmark" => {
                run_python_backend(&["benchmark"]);
            }
            "model" => {
                run_python_backend(&["model"]);
            }
            "status" => {
                run_python_backend(&["status"]);
            }
            _ => {
                // Natural language routing
                let input_line = args[1..].join(" ");
                run_python_backend(&["chat", &input_line]);
            }
        }
    } else {
        // Interactive REPL Mode
        run_repl();
    }
}
