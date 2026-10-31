//! Filevo Native Inference Subsystem.
//!
//! Provides model discovery, weights verification, tokenization,
//! 6-state availability lifecycle tracking, and generation interfaces.

use safetensors::SafeTensors;
use serde::{Deserialize, Serialize};
use std::fs::{self, File};
use std::io::Read;
use std::path::{Path, PathBuf};
use thiserror::Error;
use tokenizers::Tokenizer;

#[derive(Error, Debug)]
pub enum InferenceError {
    #[error("Model not found in cache: {0}")]
    NotFound(String),
    #[error("Failed to read model artifact: {0}")]
    Io(#[from] std::io::Error),
    #[error("Failed to parse JSON configuration: {0}")]
    Json(#[from] serde_json::Error),
    #[error("Tokenizer error: {0}")]
    Tokenizer(String),
    #[error("Safetensors error: {0}")]
    Safetensors(String),
    #[error("Stage failure during {stage}: {reason}")]
    LifecycleFailure { stage: String, reason: String },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "state", content = "details")]
pub enum ModelLifecycle {
    MetadataConfigured {
        model_id: String,
    },
    WeightsPresent {
        model_id: String,
        path: PathBuf,
        size_bytes: u64,
    },
    TokenizerLoaded {
        model_id: String,
        vocab_size: usize,
    },
    BackendInitialized {
        backend_type: String,
    },
    GpuExecutionVerified {
        device: String,
        vram_free_mb: u64,
    },
    Ready {
        latency_p50_ms: u64,
    },
    Failed {
        stage: String,
        reason: String,
        remediation: String,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelFiles {
    pub model_id: String,
    pub snapshot_dir: PathBuf,
    pub config_path: PathBuf,
    pub tokenizer_path: PathBuf,
    pub weights_path: Option<PathBuf>,
    pub total_weights_size: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SafetensorsInfo {
    pub tensor_count: usize,
    pub parameter_count: u64,
    pub data_types: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GenerationResult {
    pub text: String,
    pub prompt_tokens: usize,
    pub completion_tokens: usize,
    pub is_neural: bool,
    pub source_note: String,
}

pub struct ModelManager {
    pub model_id: String,
    cache_root: PathBuf,
}

impl ModelManager {
    pub fn new(model_id: impl Into<String>) -> Self {
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
        let cache_root = PathBuf::from(home).join(".cache").join("huggingface").join("hub");
        Self {
            model_id: model_id.into(),
            cache_root,
        }
    }

    pub fn with_cache_root(model_id: impl Into<String>, cache_root: PathBuf) -> Self {
        Self {
            model_id: model_id.into(),
            cache_root,
        }
    }

    pub fn discover_files(&self) -> Result<ModelFiles, InferenceError> {
        let sanitized = format!("models--{}", self.model_id.replace('/', "--"));
        let model_dir = self.cache_root.join(&sanitized);

        if !model_dir.exists() {
            return Err(InferenceError::NotFound(format!(
                "Directory not found: {}",
                model_dir.display()
            )));
        }

        let snapshots_dir = model_dir.join("snapshots");
        if !snapshots_dir.exists() {
            return Err(InferenceError::NotFound(format!(
                "No snapshots directory in {}",
                model_dir.display()
            )));
        }

        let mut snapshot_entry = None;
        if let Ok(entries) = fs::read_dir(&snapshots_dir) {
            for entry in entries.flatten() {
                if entry.file_type().map(|t| t.is_dir()).unwrap_or(false) {
                    snapshot_entry = Some(entry.path());
                    break;
                }
            }
        }

        let snapshot_dir = snapshot_entry.ok_or_else(|| {
            InferenceError::NotFound(format!("No snapshot commit dir in {}", snapshots_dir.display()))
        })?;

        let config_path = snapshot_dir.join("config.json");
        let tokenizer_path = snapshot_dir.join("tokenizer.json");

        let mut weights_path = None;
        let mut total_weights_size = 0;
        let single_safetensors = snapshot_dir.join("model.safetensors");
        if single_safetensors.exists() {
            if let Ok(meta) = fs::metadata(&single_safetensors) {
                total_weights_size = meta.len();
                weights_path = Some(single_safetensors);
            }
        }

        Ok(ModelFiles {
            model_id: self.model_id.clone(),
            snapshot_dir,
            config_path,
            tokenizer_path,
            weights_path,
            total_weights_size,
        })
    }

    pub fn inspect_safetensors(&self, files: &ModelFiles) -> Result<SafetensorsInfo, InferenceError> {
        let path = files.weights_path.as_ref().ok_or_else(|| {
            InferenceError::NotFound("Weights file path missing".to_string())
        })?;

        let mut file = File::open(path)?;
        let mut header_size_buf = [0u8; 8];
        file.read_exact(&mut header_size_buf)?;
        let header_len = u64::from_le_bytes(header_size_buf) as usize;

        if header_len > 100_000_000 {
            return Err(InferenceError::Safetensors("Corrupted header size".to_string()));
        }

        let mut header_buf = vec![0u8; header_len];
        file.read_exact(&mut header_buf)?;

        let header_str = std::str::from_utf8(&header_buf)
            .map_err(|e| InferenceError::Safetensors(format!("Header utf-8 error: {e}")))?;
        let header_json: serde_json::Value = serde_json::from_str(header_str)?;

        let mut tensor_count = 0;
        let mut parameter_count = 0u64;
        let mut data_types = std::collections::HashSet::new();

        if let Some(obj) = header_json.as_object() {
            for (key, val) in obj {
                if key == "__metadata__" {
                    continue;
                }
                tensor_count += 1;
                if let Some(dtype) = val.get("dtype").and_then(|d| d.as_str()) {
                    data_types.insert(dtype.to_string());
                }
                if let Some(shape) = val.get("shape").and_then(|s| s.as_array()) {
                    let mut prod = 1u64;
                    for dim in shape {
                        if let Some(d) = dim.as_u64() {
                            prod = prod.saturating_mul(d);
                        }
                    }
                    parameter_count = parameter_count.saturating_add(prod);
                }
            }
        }

        let mut dt_vec: Vec<String> = data_types.into_iter().collect();
        dt_vec.sort();

        Ok(SafetensorsInfo {
            tensor_count,
            parameter_count,
            data_types: dt_vec,
        })
    }

    pub fn load_tokenizer(&self, files: &ModelFiles) -> Result<Tokenizer, InferenceError> {
        if !files.tokenizer_path.exists() {
            return Err(InferenceError::NotFound(format!(
                "tokenizer.json not found at {}",
                files.tokenizer_path.display()
            )));
        }
        Tokenizer::from_file(&files.tokenizer_path)
            .map_err(|e| InferenceError::Tokenizer(e.to_string()))
    }

    pub fn assess_lifecycle(&self) -> ModelLifecycle {
        let files = match self.discover_files() {
            Ok(f) => f,
            Err(e) => {
                return ModelLifecycle::Failed {
                    stage: "Discovery".to_string(),
                    reason: e.to_string(),
                    remediation: format!("Run `huggingface-cli download {}`", self.model_id),
                };
            }
        };

        if files.weights_path.is_none() || files.total_weights_size == 0 {
            return ModelLifecycle::Failed {
                stage: "WeightsValidation".to_string(),
                reason: "Weights file model.safetensors is empty or missing".to_string(),
                remediation: "Download safetensors weights".to_string(),
            };
        }

        let tokenizer = match self.load_tokenizer(&files) {
            Ok(t) => t,
            Err(e) => {
                return ModelLifecycle::Failed {
                    stage: "TokenizerLoading".to_string(),
                    reason: e.to_string(),
                    remediation: "Re-download tokenizer.json".to_string(),
                };
            }
        };

        ModelLifecycle::TokenizerLoaded {
            model_id: self.model_id.clone(),
            vocab_size: tokenizer.get_vocab_size(true),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_lifecycle_enum_serialization() {
        let state = ModelLifecycle::Ready { latency_p50_ms: 12 };
        let json = serde_json::to_string(&state).unwrap();
        assert!(json.contains("Ready"));
        assert!(json.contains("12"));

        let fail = ModelLifecycle::Failed {
            stage: "Weights".to_string(),
            reason: "file missing".to_string(),
            remediation: "download".to_string(),
        };
        let fail_json = serde_json::to_string(&fail).unwrap();
        assert!(fail_json.contains("Weights"));
    }

    #[test]
    fn test_smollm2_cached_model_discovery_and_tokenization() {
        let mgr = ModelManager::new("HuggingFaceTB/SmolLM2-1.7B-Instruct");
        let files_res = mgr.discover_files();
        if let Ok(files) = files_res {
            assert!(files.config_path.exists());
            assert!(files.tokenizer_path.exists());
            assert!(files.weights_path.is_some());
            assert!(files.total_weights_size > 1_000_000_000, "1.7B model must be > 1GB");

            // Test Tokenizer
            let tokenizer = mgr.load_tokenizer(&files).expect("Tokenizer must load cleanly");
            let vocab_size = tokenizer.get_vocab_size(true);
            assert!(vocab_size > 30000, "Vocab size should be > 30k, got {vocab_size}");

            let encoding = tokenizer.encode("Create a cricket scoring report", true).unwrap();
            let tokens = encoding.get_ids();
            assert!(!tokens.is_empty());

            // Test Safetensors fast header inspection (zero memory copy of entire model)
            let tensor_info = mgr.inspect_safetensors(&files).expect("Safetensors header inspection must succeed");
            assert!(tensor_info.tensor_count > 100, "1.7B model should have > 100 tensors");
            assert!(tensor_info.parameter_count > 1_000_000_000, "Parameters should exceed 1 billion");
            println!("Discovered parameters: {}", tensor_info.parameter_count);
            println!("Tensor count: {}", tensor_info.tensor_count);
            println!("Data types: {:?}", tensor_info.data_types);
        }
    }
}
