//! Domain types shared by the application state, backend bridge and renderer.
//!
//! The renderer never reads Python objects directly: the daemon serialises a
//! snapshot and this module defines the stable Rust-side contract.

/// The five mutually-exclusive intent categories emitted by
/// `RLCDDecisionEngine.evaluate_intent`.
pub const INTENTS: [&str; 5] = [
    "DOCUMENT_CREATION",
    "CONVERSATION",
    "DOCUMENT_ANALYSIS",
    "KNOWLEDGE_INDEXING",
    "POLICY_TRAIN",
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Role {
    User,
    Assistant,
    System,
}

#[derive(Debug, Clone)]
pub struct Message {
    pub id: u64,
    pub role: Role,
    pub content: String,
    /// Local wall-clock label (`HH:MM:SS`). Fixtures may provide their own.
    pub timestamp: String,
    pub is_error: bool,
}

impl Message {
    pub fn new(id: u64, role: Role, content: impl Into<String>, timestamp: impl Into<String>) -> Self {
        Self {
            id,
            role,
            content: content.into(),
            timestamp: timestamp.into(),
            is_error: false,
        }
    }

    pub fn error(
        id: u64,
        content: impl Into<String>,
        timestamp: impl Into<String>,
    ) -> Self {
        Self {
            id,
            role: Role::Assistant,
            content: content.into(),
            timestamp: timestamp.into(),
            is_error: true,
        }
    }
}

#[derive(Debug, Clone, Default)]
pub struct ModelInfo {
    pub id: String,
    pub short: String,
    pub device: String,
    pub loaded: bool,
    pub load_error: Option<String>,
    pub context_tokens: Option<u64>,
}

impl ModelInfo {
    pub fn display_name(&self) -> &str {
        if self.short.trim().is_empty() {
            if self.id.trim().is_empty() {
                "Unknown"
            } else {
                &self.id
            }
        } else {
            &self.short
        }
    }

    pub fn context_label(&self) -> String {
        match self.context_tokens {
            Some(tokens) if tokens >= 1000 => format!("{:.1}k tokens", tokens as f64 / 1000.0),
            Some(tokens) => format!("{tokens} tokens"),
            None => "Unknown".to_string(),
        }
    }

    pub fn mode_label(&self) -> &'static str {
        if self.loaded {
            "Local (Ready)"
        } else if self.load_error.is_some() {
            "Local (Error)"
        } else {
            "Local (Idle)"
        }
    }
}

#[derive(Debug, Clone, Default)]
pub struct SessionInfo {
    pub files_indexed: u64,
    pub docs_created: u64,
    pub policy_status: String,
    pub policy_episodes: u64,
    pub policy_baseline: f64,
    pub memory_used: u64,
    pub memory_limit: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Risk {
    Low,
    Medium,
    High,
    Unknown,
}

impl Risk {
    pub fn parse(value: Option<&str>) -> Self {
        match value.map(str::trim).map(str::to_ascii_uppercase).as_deref() {
            Some("LOW") => Self::Low,
            Some("MEDIUM") => Self::Medium,
            Some("HIGH") => Self::High,
            _ => Self::Unknown,
        }
    }

    pub fn label(self) -> &'static str {
        match self {
            Self::Low => "LOW",
            Self::Medium => "MEDIUM",
            Self::High => "HIGH",
            Self::Unknown => "UNKNOWN",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DistributionError {
    Missing,
    NotFinite,
    OutOfRange,
    BadSum,
}

impl DistributionError {
    pub fn message(self) -> &'static str {
        match self {
            Self::Missing => "Distribution unavailable",
            Self::NotFinite => "Distribution contains a non-finite value",
            Self::OutOfRange => "Distribution contains a value outside [0, 1]",
            Self::BadSum => "Distribution does not sum to 1",
        }
    }
}

/// A snapshot of the RLCD intent distribution.
#[derive(Debug, Clone)]
pub struct Decision {
    /// True only when the backend evaluated the current prompt. The backend's
    /// initial values are a prior/demo fixture and are never presented as live.
    pub available: bool,
    pub values: [Option<f64>; 5],
    pub confidence: Option<f64>,
    pub entropy: Option<f64>,
    pub risk: Risk,
    pub source: String,
}

impl Default for Decision {
    fn default() -> Self {
        Self {
            available: false,
            values: [None; 5],
            confidence: None,
            entropy: None,
            risk: Risk::Unknown,
            source: "unavailable".to_string(),
        }
    }
}

impl Decision {
    pub fn from_map(
        available: bool,
        probabilities: &std::collections::HashMap<String, f64>,
        confidence: Option<f64>,
        entropy: Option<f64>,
        risk: Option<&str>,
        source: impl Into<String>,
    ) -> Self {
        let mut values = [None; 5];
        for (index, name) in INTENTS.iter().enumerate() {
            values[index] = probabilities.get(*name).copied();
        }
        Self {
            available,
            values,
            confidence,
            entropy,
            risk: Risk::parse(risk),
            source: source.into(),
        }
    }

    pub fn probability_sum(&self) -> Option<f64> {
        self.values
            .iter()
            .try_fold(0.0, |sum, value| value.map(|v| sum + v))
    }

    /// A distribution is only rendered as a probability distribution when it
    /// is complete, finite, in range and sums to one within two percentage
    /// points (the backend rounds each value to 0.01).
    pub fn validate(&self) -> Result<(), DistributionError> {
        if !self.available || self.values.iter().any(Option::is_none) {
            return Err(DistributionError::Missing);
        }
        let mut sum = 0.0;
        for value in self.values.iter().flatten() {
            if !value.is_finite() {
                return Err(DistributionError::NotFinite);
            }
            if !(0.0..=1.0).contains(value) {
                return Err(DistributionError::OutOfRange);
            }
            sum += value;
        }
        if (sum - 1.0).abs() > 0.02 {
            return Err(DistributionError::BadSum);
        }
        Ok(())
    }

    pub fn winning_value(&self) -> Option<f64> {
        self.values.iter().flatten().copied().fold(None, |acc, v| {
            Some(match acc {
                Some(a) if a > v => a,
                _ => v,
            })
        })
    }

    pub fn winning_intent(&self) -> Option<&'static str> {
        if self.validate().is_err() {
            return None;
        }
        let mut best = 0usize;
        for i in 1..self.values.len() {
            if self.values[i].unwrap_or(0.0) > self.values[best].unwrap_or(0.0) {
                best = i;
            }
        }
        Some(INTENTS[best])
    }
}

#[derive(Debug, Clone)]
pub struct ReferenceInfo {
    pub url: String,
    pub title: String,
    pub domain: String,
}

#[derive(Debug, Clone)]
pub struct DocumentInfo {
    pub name: String,
    pub path: String,
    pub size_bytes: u64,
    /// Unix seconds. Formatted with the host's local timezone by the renderer.
    pub modified: Option<i64>,
}

#[derive(Debug, Clone)]
pub struct GpuInfo {
    pub name: String,
    pub utilization: f64,
    pub memory_used_mb: f64,
    pub memory_total_mb: f64,
}

#[derive(Debug, Clone)]
pub struct DiskInfo {
    pub path: String,
    pub used: u64,
    pub total: u64,
    pub free: u64,
}

#[derive(Debug, Clone)]
pub struct SystemMemory {
    pub used: u64,
    pub total: u64,
}

#[derive(Debug, Clone)]
pub struct WebStatus {
    pub enabled: bool,
    pub live_references: u64,
    pub last_result: String,
}

impl Default for WebStatus {
    fn default() -> Self {
        Self {
            enabled: false,
            live_references: 0,
            last_result: "unknown".to_string(),
        }
    }
}

#[derive(Debug, Clone, Default)]
pub struct Telemetry {
    pub gpu: Option<GpuInfo>,
    pub disk: Option<DiskInfo>,
    pub system_memory: Option<SystemMemory>,
    pub model_ready: bool,
    pub web: WebStatus,
}

#[derive(Debug, Clone, Default)]
pub struct PolicyTelemetry {
    pub episodes: u64,
    pub baseline: f64,
    pub temperature: f64,
    pub archetypes: Vec<(String, f64)>,
    pub fonts: Vec<(String, f64)>,
}

#[derive(Debug, Clone, Default)]
pub struct Dashboard {
    pub model: ModelInfo,
    pub session: SessionInfo,
    pub decision: Decision,
    pub references: Vec<ReferenceInfo>,
    pub documents: Vec<DocumentInfo>,
    pub telemetry: Telemetry,
    pub policy: PolicyTelemetry,
    pub turns: Vec<TurnSnapshot>,
    pub errors: Vec<String>,
    /// Unix seconds when the daemon assembled the snapshot.
    pub generated_at: Option<i64>,
}

#[derive(Debug, Clone)]
pub struct TurnSnapshot {
    pub role: Role,
    pub content: String,
    pub timestamp: f64,
}

/// Human-readable binary size (base 1024) used by the documents table.
pub fn format_size(bytes: u64) -> String {
    const KIB: f64 = 1024.0;
    const MIB: f64 = 1024.0 * 1024.0;
    const GIB: f64 = 1024.0 * 1024.0 * 1024.0;
    let value = bytes as f64;
    if value >= GIB {
        format!("{:.1} GB", value / GIB)
    } else if value >= MIB {
        format!("{:.1} MB", value / MIB)
    } else if value >= KIB {
        format!("{:.0} KB", value / KIB)
    } else {
        format!("{bytes} B")
    }
}

pub fn format_epoch_hms(epoch: f64) -> String {
    let seconds = epoch as i64;
    chrono::DateTime::from_timestamp(seconds, 0)
        .map(|dt| {
            dt.with_timezone(&chrono::Local)
                .format("%H:%M:%S")
                .to_string()
        })
        .unwrap_or_else(|| "--:--:--".to_string())
}

pub fn format_epoch_document(epoch: Option<i64>) -> String {
    epoch
        .and_then(|seconds| chrono::DateTime::from_timestamp(seconds, 0))
        .map(|dt| {
            dt.with_timezone(&chrono::Local)
                .format("%Y-%m-%d %H:%M")
                .to_string()
        })
        .unwrap_or_else(|| "Unknown".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    fn map(values: [f64; 5]) -> HashMap<String, f64> {
        INTENTS
            .iter()
            .enumerate()
            .map(|(i, name)| ((*name).to_string(), values[i]))
            .collect()
    }

    #[test]
    fn valid_distribution_is_accepted() {
        let decision = Decision::from_map(
            true,
            &map([0.12, 0.71, 0.08, 0.05, 0.04]),
            Some(0.71),
            Some(0.58),
            Some("LOW"),
            "test",
        );
        assert!(decision.validate().is_ok());
        assert_eq!(decision.winning_intent(), Some("CONVERSATION"));
    }

    #[test]
    fn invalid_sum_is_not_silently_normalised() {
        let decision = Decision::from_map(
            true,
            &map([0.2, 0.2, 0.2, 0.2, 0.2]),
            Some(0.2),
            Some(0.9),
            Some("HIGH"),
            "test",
        );
        assert_eq!(decision.validate(), Ok(()));
        let bad = Decision::from_map(
            true,
            &map([0.5, 0.5, 0.5, 0.5, 0.5]),
            None,
            None,
            None,
            "test",
        );
        assert_eq!(bad.validate(), Err(DistributionError::BadSum));
    }

    #[test]
    fn unavailable_prior_is_not_a_distribution() {
        let decision = Decision::from_map(
            false,
            &map([0.12, 0.71, 0.08, 0.05, 0.04]),
            Some(0.713),
            Some(0.58),
            Some("LOW"),
            "backend_default_prior",
        );
        assert_eq!(decision.validate(), Err(DistributionError::Missing));
    }

    #[test]
    fn sizes_are_human_readable() {
        assert_eq!(format_size(150 * 1024), "150 KB");
        assert_eq!(format_size(2_500_000), "2.4 MB");
    }
}
