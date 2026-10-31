//! Filevo Persistence & Schema Migration Engine.
//!
//! Handles safe versioned state migration, pre-migration backups,
//! atomic file writes, and checkpointing for ~/.filevo.

use filevo_policy::PolicyParameters;
use serde::{Deserialize, Serialize};
use std::fs::{self, File};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};
use thiserror::Error;

#[derive(Error, Debug)]
pub enum StoreError {
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),
    #[error("Serialization error: {0}")]
    Json(#[from] serde_json::Error),
    #[error("Migration failed: {0}")]
    Migration(String),
}

pub struct StateStore {
    root_dir: PathBuf,
}

impl StateStore {
    pub fn new(root_dir: PathBuf) -> Self {
        Self { root_dir }
    }

    pub fn backup_existing_state(&self) -> Result<Option<PathBuf>, StoreError> {
        if !self.root_dir.exists() {
            return Ok(None);
        }

        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        let backup_dir = self.root_dir.join("backups").join(format!("backup_{now}"));
        fs::create_dir_all(&backup_dir)?;

        let mut copied = false;
        for entry in fs::read_dir(&self.root_dir)? {
            let entry = entry?;
            let path = entry.path();
            if path.is_file() {
                let dest = backup_dir.join(entry.file_name());
                fs::copy(&path, dest)?;
                copied = true;
            }
        }

        if copied {
            Ok(Some(backup_dir))
        } else {
            Ok(None)
        }
    }

    pub fn migrate_legacy_policy(&self, legacy_path: &Path) -> Result<PolicyParameters, StoreError> {
        if !legacy_path.exists() {
            return Ok(PolicyParameters::default());
        }

        let mut file = File::open(legacy_path)?;
        let mut content = String::new();
        file.read_to_string(&mut content)?;

        let val: serde_json::Value = serde_json::from_str(&content)?;

        let mut params = PolicyParameters::default();
        if let Some(episodes) = val.get("episodes").and_then(|e| e.as_u64()) {
            params.total_episodes = episodes;
        }
        if let Some(baseline) = val.get("baseline").and_then(|b| b.as_f64()) {
            params.running_baseline = baseline;
        }
        if let Some(biases) = val.get("archetype_biases").and_then(|b| b.as_object()) {
            for (k, v) in biases {
                if let Some(score) = v.as_f64() {
                    params.biases.insert(k.clone(), score);
                }
            }
        }

        Ok(params)
    }

    pub fn atomic_write_json<T: Serialize>(&self, filename: &str, data: &T) -> Result<PathBuf, StoreError> {
        fs::create_dir_all(&self.root_dir)?;
        let target_path = self.root_dir.join(filename);
        let tmp_path = self.root_dir.join(format!("{filename}.tmp"));

        let payload = serde_json::to_string_pretty(data)?;
        let mut file = File::create(&tmp_path)?;
        file.write_all(payload.as_bytes())?;
        file.sync_all()?;
        fs::rename(tmp_path, &target_path)?;

        Ok(target_path)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_backup_and_migration() {
        let tmp = tempfile::tempdir().unwrap();
        let store = StateStore::new(tmp.path().to_path_buf());

        // Create mock legacy policy file
        let legacy = tmp.path().join("rlcd_policy.json");
        let mock_json = r#"{
            "episodes": 42,
            "baseline": 0.68,
            "archetype_biases": {
                "Technical Report": 0.85,
                "Academic Monograph": 0.25
            }
        }"#;
        fs::write(&legacy, mock_json).unwrap();

        // Test backup
        let backup = store.backup_existing_state().unwrap();
        assert!(backup.is_some());
        let bdir = backup.unwrap();
        assert!(bdir.join("rlcd_policy.json").exists());

        // Test migration
        let params = store.migrate_legacy_policy(&legacy).unwrap();
        assert_eq!(params.total_episodes, 42);
        assert!((params.running_baseline - 0.68).abs() < 1e-6);
        assert_eq!(params.biases.get("Technical Report").copied(), Some(0.85));

        // Test atomic write
        let out = store.atomic_write_json("policy_v2.json", &params).unwrap();
        assert!(out.exists());
    }
}
