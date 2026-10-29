//! Development-only visual fixtures.
//!
//! These values recreate the supplied reference screenshot.  They are never
//! loaded unless the user explicitly passes `--demo` or sets
//! `FILEVO_DEMO=1`; the production path always comes from the Python daemon.

use crate::model::{
    Dashboard, Decision, DiskInfo, DocumentInfo, GpuInfo, Message, ModelInfo, PolicyTelemetry,
    ReferenceInfo, Risk, Role, SessionInfo, SystemMemory, Telemetry, WebStatus, INTENTS,
};
use chrono::{Local, TimeZone};

pub fn demo_dashboard() -> Dashboard {
    let local = |year, month, day, hour, minute| {
        Local
            .with_ymd_and_hms(year, month, day, hour, minute, 0)
            .single()
            .map(|dt| dt.timestamp())
            .unwrap_or(0)
    };

    let values = [0.12, 0.71, 0.08, 0.05, 0.04];
    let mut decision_values = [None; 5];
    for (index, value) in values.iter().enumerate() {
        decision_values[index] = Some(*value);
    }

    Dashboard {
        model: ModelInfo {
            id: "HuggingFaceTB/SmolLM2-1.7B-Instruct".to_string(),
            short: "SmolLM2-1.7B-Instruct".to_string(),
            device: "cuda".to_string(),
            loaded: true,
            load_error: None,
            context_tokens: Some(16_400),
        },
        session: SessionInfo {
            files_indexed: 12,
            docs_created: 3,
            policy_status: "Trained".to_string(),
            policy_episodes: 17,
            policy_baseline: 0.653,
            memory_used: 8,
            memory_limit: 20,
        },
        decision: Decision {
            available: true,
            values: decision_values,
            confidence: Some(0.713),
            entropy: Some(0.58),
            risk: Risk::Low,
            source: "demo_fixture".to_string(),
        },
        references: vec![
            ReferenceInfo {
                url: "https://towardsdatascience.com/understanding-overfitting".to_string(),
                title: "Understanding Overfitting in ML".to_string(),
                domain: "towardsdatascience.com".to_string(),
            },
            ReferenceInfo {
                url: "https://machinelearningmastery.com/overfitting-vs-generalization"
                    .to_string(),
                title: "Overfitting vs. Generalization".to_string(),
                domain: "machinelearningmastery.com".to_string(),
            },
            ReferenceInfo {
                url: "https://cs231n.github.io/neural-networks-3/".to_string(),
                title: "Bias-Variance Tradeoff".to_string(),
                domain: "cs231n.github.io".to_string(),
            },
            ReferenceInfo {
                url: "https://keras.io/guides/overfit-and-underfit/".to_string(),
                title: "Why Models Overfit".to_string(),
                domain: "keras.io".to_string(),
            },
        ],
        documents: vec![
            DocumentInfo {
                name: "IoT_Cricket_Scoring_System.docx".to_string(),
                path: "/demo/output/IoT_Cricket_Scoring_System.docx".to_string(),
                size_bytes: 2_400_000,
                modified: Some(local(2025, 8, 17, 10, 12)),
            },
            DocumentInfo {
                name: "University_Permission_Letter.docx".to_string(),
                path: "/demo/output/University_Permission_Letter.docx".to_string(),
                size_bytes: 150_000,
                modified: Some(local(2025, 8, 17, 9, 48)),
            },
            DocumentInfo {
                name: "Edge_Computing_Report.docx".to_string(),
                path: "/demo/output/Edge_Computing_Report.docx".to_string(),
                size_bytes: 1_800_000,
                modified: Some(local(2025, 8, 17, 9, 21)),
            },
        ],
        telemetry: Telemetry {
            gpu: Some(GpuInfo {
                name: "NVIDIA GeForce RTX 4090".to_string(),
                utilization: 72.0,
                memory_used_mb: 11_800.0,
                memory_total_mb: 16_376.0,
            }),
            disk: Some(DiskInfo {
                path: "~/.filevo".to_string(),
                used: 2_100_000_000,
                total: 50_000_000_000,
                free: 47_900_000_000,
            }),
            system_memory: Some(SystemMemory {
                used: 14_000_000_000,
                total: 32_000_000_000,
            }),
            model_ready: true,
            web: WebStatus {
                enabled: true,
                live_references: 4,
                last_result: "live".to_string(),
            },
        },
        policy: PolicyTelemetry {
            episodes: 17,
            baseline: 0.653,
            temperature: 1.0,
            archetypes: vec![
                ("Technical Report".to_string(), 0.34),
                ("Executive Summary".to_string(), 0.28),
                ("Project Proposal".to_string(), 0.16),
                ("Formal Letter".to_string(), 0.12),
                ("Academic Monograph".to_string(), 0.10),
            ],
            fonts: vec![
                ("Calibri".to_string(), 0.46),
                ("Arial".to_string(), 0.24),
                ("Georgia".to_string(), 0.18),
                ("Times New Roman".to_string(), 0.12),
            ],
        },
        turns: Vec::new(),
        errors: Vec::new(),
        generated_at: None,
    }
}

pub fn demo_messages() -> Vec<Message> {
    let _ = INTENTS;
    vec![
        Message::new(1, Role::User, "sup", "10:14:23"),
        Message::new(
            2,
            Role::Assistant,
            "Hey there! \u{1F44B}\nI'm Filevo — your document intelligence assistant.\nYou can chat naturally or use slash commands like /create, /analyze, or /index.\nWhat would you like to work on today?",
            "10:14:24",
        ),
        Message::new(
            3,
            Role::User,
            "Explain why a model can overfit even when its training accuracy is high.",
            "10:15:01",
        ),
        Message::new(
            4,
            Role::Assistant,
            "A model can overfit when it learns the training data too well, including its noise and specific patterns, instead of learning the underlying general patterns. This allows it to achieve high training accuracy, but it performs poorly on new, unseen data because it has essentially memorized the training examples rather than learning generalizable relationships.\n\nThink of it like a student who memorizes answers to past exam questions — they do very well on those exact questions (high training accuracy), but fail when the questions are phrased differently (poor generalization).",
            "10:15:03",
        ),
    ]
}
