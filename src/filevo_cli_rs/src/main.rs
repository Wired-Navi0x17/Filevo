//! Filevo native terminal interface.
//!
//! Two entry paths share the same Python backend:
//! - no arguments (or `--demo`): the Ratatui dashboard and conversation UI;
//! - `filevo-cli <command> …`: the existing one-shot CLI subcommands.
//!
//! The TUI owns a single backend worker thread.  Rendering never performs
//! socket or subprocess work, so resizing, scrolling and typing stay responsive
//! while a 1.7B-parameter model or an index job is running.

mod app;
mod backend;
pub mod files;
mod fixtures;
mod model;
mod ui;

use app::{App, AppAction, BackendState};
use backend::{BackendClient, Request};
use crossterm::event::{
    self, DisableBracketedPaste, DisableMouseCapture, EnableBracketedPaste, EnableMouseCapture, Event,
    KeyEventKind,
};
use crossterm::execute;
use ratatui::DefaultTerminal;
use std::env;
use std::io;
use std::process::{Command, Stdio};
use std::time::Duration;

const VERSION: &str = "2.0.0";

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    let demo_env = env::var("FILEVO_DEMO")
        .map(|value| value == "1" || value.eq_ignore_ascii_case("true"))
        .unwrap_or(false);

    if args.is_empty() {
        std::process::exit(run_tui(demo_env));
    }

    let command = args[0].as_str();
    match command {
        "--demo" | "demo" => std::process::exit(run_tui(true)),
        "--tui" | "tui" => std::process::exit(run_tui(demo_env)),
        "--help" | "-h" | "help" => {
            print_help();
            std::process::exit(0);
        }
        "--version" | "-v" | "version" => {
            println!("filevo-cli {VERSION}");
            std::process::exit(0);
        }
        _ => {}
    }

    let rest: Vec<String> = args[1..].to_vec();
    let python_args: Vec<String> = match command {
        "create" | "chat" | "revise" | "research" => {
            vec![command.to_string(), rest.join(" ")]
        }
        "analyze" | "index" | "dataset" => vec![
            command.to_string(),
            rest.first().cloned().unwrap_or_else(|| ".".to_string()),
        ],
        "train" => {
            let mut values = vec!["train".to_string()];
            if rest.is_empty() {
                values.push("corpus".to_string());
            } else {
                values.extend(rest);
            }
            values
        }
        "feedback" => vec![
            "feedback".to_string(),
            rest.first().cloned().unwrap_or_else(|| "+1.0".to_string()),
        ],
        "wordcraft" => {
            let mut values = vec!["wordcraft".to_string()];
            values.extend(rest);
            values
        }
        "benchmark" | "model" | "status" => vec![command.to_string()],
        other if other.starts_with('-') => {
            eprintln!("Unknown option: {other}");
            eprintln!("Run `filevo-cli --help` for usage.");
            std::process::exit(2);
        }
        _ => {
            // Natural-language fallback, matching the historical CLI.
            vec!["chat".to_string(), args.join(" ")]
        }
    };

    match backend::run_python_inherit(&python_args) {
        Ok(code) => std::process::exit(code),
        Err(error) => {
            eprintln!("filevo: {error}");
            std::process::exit(1);
        }
    }
}

fn print_help() {
    println!("Filevo {VERSION} — conversational document intelligence");
    println!();
    println!("Usage:");
    println!("  filevo-cli                 Launch the interactive terminal dashboard");
    println!("  filevo-cli --demo          Launch with the reference fixtures only");
    println!("  filevo-cli <command> ...   Run a one-shot backend command");
    println!();
    println!("Commands:");
    println!("  create \"<topic>\"           Create a calibrated .docx document");
    println!("  revise \"<instruction>\"     Revise the active document");
    println!("  research \"<topic>\"         Ground a response in live web sources");
    println!("  chat \"<message>\"           Send a natural-language message");
    println!("  analyze [path]             Analyze a document or codebase");
    println!("  train [@file|dir|live]     Ingest docs, build datasets & train policy");
    println!("  feedback [+1.0|-0.5]       Record feedback on the last generation");
    println!("  dataset [dir]              Build a leakage-free training dataset");
    println!("  benchmark                  Benchmark candidate local models");
    println!("  model                      Print model and policy telemetry");
    println!("  status                     Print system and memory status");
    println!();
    println!("Interactive keys:");
    println!("  Enter send · Tab complete · PgUp/PgDn scroll · F1 help");
    println!("  F6 focus · Ctrl+R refresh · Ctrl+C cancel · Ctrl+Q quit");
    println!("  Alt+1 … Alt+7 jump to HOME CREATE ANALYZE TRAIN MODEL SETTINGS HELP");
    println!();
    println!("Environment:");
    println!("  FILEVO_DEMO=1   Use the reference fixtures (never live backend data)");
    println!("  FILEVO_ASCII=1  Disable Unicode artwork and braille landscape");
    println!("  NO_COLOR=1      Disable colour while keeping the layout");
}

fn run_tui(demo: bool) -> i32 {
    let mut terminal = ratatui::init();
    let _ = execute!(
        terminal.backend_mut(),
        EnableBracketedPaste,
        EnableMouseCapture
    );
    let result = event_loop(&mut terminal, demo);
    let _ = execute!(
        terminal.backend_mut(),
        DisableBracketedPaste,
        DisableMouseCapture
    );
    ratatui::restore();
    match result {
        Ok(()) => 0,
        Err(error) => {
            eprintln!("filevo: {error}");
            1
        }
    }
}

fn event_loop(terminal: &mut DefaultTerminal, demo: bool) -> Result<(), String> {
    let mut app = App::new(demo);
    let client = if demo {
        None
    } else {
        Some(BackendClient::spawn())
    };

    if let Some(client) = &client {
        // Clear previous conversation turns on every launch so each start is a clean fresh session
        let _ = client.send(Request::Daemon {
            task_id: 0,
            action: "clear_session".to_string(),
            payload: serde_json::json!({}),
            cancel: std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false)),
        });
        match client.send(Request::Dashboard) {
            Ok(()) => app.mark_dashboard_requested(),
            Err(error) => app.toast(
                format!("Backend worker unavailable: {error}"),
                app::ToastKind::Error,
            ),
        }
    }

    loop {
        app.on_tick();
        if let Some(client) = &client {
            while let Some(event) = client.try_recv() {
                app.apply_event(event);
            }
        }

        if let Some(client) = &client {
            if app.should_refresh_dashboard() {
                if client.send(Request::Dashboard).is_ok() {
                    app.mark_dashboard_requested();
                } else {
                    app.toast("Backend worker stopped", app::ToastKind::Error);
                }
            }
        }

        terminal
            .draw(|frame| ui::draw(frame, &mut app))
            .map_err(|error| format!("could not draw the interface: {error}"))?;

        if app.should_quit {
            break;
        }

        if event::poll(Duration::from_millis(60))
            .map_err(|error| format!("terminal event error: {error}"))?
        {
            match event::read().map_err(|error| format!("terminal event error: {error}"))? {
                Event::Key(key)
                    if matches!(key.kind, KeyEventKind::Press | KeyEventKind::Repeat) =>
                {
                    let action = app.on_key(key);
                    handle_action(&mut app, client.as_ref(), action);
                }
                Event::Mouse(mouse) => {
                    let action = app.on_mouse(mouse);
                    handle_action(&mut app, client.as_ref(), action);
                }
                Event::Paste(text) => {
                    app.input.insert_str(&text);
                }
                Event::Resize(_, _) => {}
                Event::FocusGained | Event::FocusLost => {}
                _ => {}
            }
        }

        if app.should_quit {
            break;
        }
    }

    if let Some(client) = &client {
        while let Some(event) = client.try_recv() {
            app.apply_event(event);
        }
    }
    Ok(())
}

fn handle_action(app: &mut App, client: Option<&BackendClient>, action: AppAction) {
    match action {
        AppAction::None => {}
        AppAction::Quit => app.should_quit = true,
        AppAction::Send(request) => {
            let Some(client) = client else {
                app.toast(
                    "Demo mode is read-only · launch without --demo",
                    app::ToastKind::Warning,
                );
                return;
            };
            if let Err(error) = client.send(request) {
                app.request_failed(error);
            }
        }
        AppAction::RequestDashboard => {
            if !app.refresh_requested() {
                return;
            }
            let Some(client) = client else {
                return;
            };
            if client.send(Request::Dashboard).is_ok() {
                app.mark_dashboard_requested();
            } else {
                app.toast("Backend worker stopped", app::ToastKind::Error);
            }
        }
        AppAction::OpenUrl(url) => {
            if let Err(error) = open_url(&url) {
                app.toast(
                    format!("Could not open reference: {error}"),
                    app::ToastKind::Error,
                );
            }
        }
    }
    if matches!(app.backend, BackendState::Offline(_)) {
        app.mark_backend_connecting();
    }
}

fn open_url(url: &str) -> Result<(), String> {
    if !(url.starts_with("https://") || url.starts_with("http://")) {
        return Err("only http(s) reference links are opened".to_string());
    }
    Command::new("xdg-open")
        .arg(url)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map(|_| ())
        .map_err(|error| match error.kind() {
            io::ErrorKind::NotFound => "xdg-open is not installed".to_string(),
            _ => error.to_string(),
        })
}
