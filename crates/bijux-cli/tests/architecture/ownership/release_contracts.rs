#![forbid(unsafe_code)]
//! Publishing metadata and automation contract guardrails.

use serde::Deserialize;
use serde_json::Value;
use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};

fn repo_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn read_repo_file(path: &str) -> String {
    fs::read_to_string(repo_root().join(path)).expect("repo file should exist")
}

#[derive(Debug, Deserialize)]
struct WorkspacePackageBoundary {
    packages: Vec<PackageBoundaryEntry>,
    crates_io_publish_order: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct PackageBoundaryEntry {
    #[serde(rename = "crate")]
    crate_name: String,
    product_family: String,
    release_status: String,
}

fn quoted_value_after(text: &str, prefix: &str) -> Option<String> {
    text.lines().find_map(|line| {
        let trimmed = line.trim();
        if !trimmed.starts_with(prefix) {
            return None;
        }
        let value = trimmed.strip_prefix(prefix)?.trim();
        Some(value.trim_matches('"').to_string())
    })
}

fn workflow_document(name: &str) -> serde_yaml::Value {
    serde_yaml::from_str(&read_repo_file(&format!(".github/workflows/{name}")))
        .expect("workflow should contain valid YAML")
}

fn is_hex_sha(value: &str) -> bool {
    value.len() == 40 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn repository_config(repo_name: &str) -> Value {
    let manifest = read_repo_file(".github/standards/repo-config.manifest.json");
    let parsed: Value =
        serde_json::from_str(&manifest).expect("standards manifest should be valid JSON");
    let repositories = parsed
        .get("repositories")
        .and_then(Value::as_array)
        .expect("standards manifest should define repositories array");
    repositories
        .iter()
        .find(|entry| entry.get("name").and_then(Value::as_str) == Some(repo_name))
        .cloned()
        .expect("repository should exist in standards manifest")
}

fn workflow_allowlist_for_repo(repo_name: &str) -> Vec<String> {
    let repo = repository_config(repo_name);
    repo.get("workflow_allowlist")
        .and_then(Value::as_array)
        .expect("repository should define workflow allowlist")
        .iter()
        .map(|value| value.as_str().expect("allowlist entry should be string").to_string())
        .collect()
}

fn release_env_value_for_repo(repo_name: &str, key: &str) -> String {
    let repo = repository_config(repo_name);
    repo.get("release_env")
        .and_then(Value::as_array)
        .expect("repository should define release_env")
        .iter()
        .find(|entry| entry.get("key").and_then(Value::as_str) == Some(key))
        .and_then(|entry| entry.get("value"))
        .and_then(Value::as_str)
        .expect("release_env entry should exist and be a string")
        .to_string()
}

fn release_env_json_value_for_repo(repo_name: &str, key: &str) -> Value {
    let repo = repository_config(repo_name);
    repo.get("release_env")
        .and_then(Value::as_array)
        .expect("repository should define release_env")
        .iter()
        .find(|entry| entry.get("key").and_then(Value::as_str) == Some(key))
        .and_then(|entry| entry.get("value"))
        .cloned()
        .expect("release_env entry should exist")
}

fn workflow_env_value_for_repo(repo_name: &str, workflow_name: &str, key: &str) -> String {
    let repo = repository_config(repo_name);
    repo.get("workflow_wrappers")
        .and_then(|wrappers| wrappers.get(workflow_name))
        .and_then(|workflow| workflow.get("env"))
        .and_then(|env| env.get(key))
        .and_then(Value::as_str)
        .expect("workflow env entry should exist and be a string")
        .to_string()
}

fn shell_assignment_value(text: &str, key: &str) -> Option<String> {
    let prefix = format!("{key}=");
    text.lines().find_map(|line| {
        let trimmed = line.trim();
        trimmed
            .strip_prefix(&prefix)
            .map(|value| value.trim().trim_matches('"').trim_matches('\'').to_string())
    })
}

fn make_assignment_value(text: &str, key: &str) -> Option<String> {
    let prefix = format!("{key} ?= ");
    text.lines().find_map(|line| {
        let trimmed = line.trim();
        trimmed.strip_prefix(&prefix).map(|value| value.trim().to_string())
    })
}

fn json_shell_assignment_value(text: &str, key: &str) -> Value {
    let raw = shell_assignment_value(text, key).expect("shell assignment should exist");
    serde_json::from_str(&raw).expect("shell assignment JSON should parse")
}

fn read_workspace_package_boundary() -> WorkspacePackageBoundary {
    let path = repo_root().join("contracts/foundation/workspace_package_boundary.v1.json");
    let raw = fs::read_to_string(&path)
        .unwrap_or_else(|err| panic!("failed to read {}: {err}", path.display()));
    serde_json::from_str(&raw).unwrap_or_else(|err| panic!("invalid {}: {err}", path.display()))
}

fn manifest_path_for(crate_name: &str) -> String {
    format!("crates/{crate_name}/Cargo.toml")
}

#[test]
fn workspace_manifest_declares_shared_project_links() {
    let manifest = read_repo_file("Cargo.toml");
    for required in
        ["homepage = ", "documentation = ", "authors = [\"Bijan Mousavi <bijan@bijux.io>\"]"]
    {
        assert!(
            manifest.contains(required),
            "workspace manifest is missing shared project metadata: {required}"
        );
    }
}

#[test]
fn crate_manifests_declare_clear_publish_metadata() {
    for (path, required) in [
        (
            "crates/bijux-cli/Cargo.toml",
            vec![
                "description = ",
                "homepage",
                "documentation = ",
                "readme = ",
                "keywords = [",
                "categories = [",
                "automation",
                "plugins",
            ],
        ),
        (
            "crates/bijux-dag-core/Cargo.toml",
            vec![
                "description = ",
                "documentation = ",
                "readme = ",
                "keywords = [",
                "categories = [",
                "Deterministic DAG kernel",
            ],
        ),
        (
            "crates/bijux-dag-artifacts/Cargo.toml",
            vec![
                "description = ",
                "documentation = ",
                "readme = ",
                "keywords = [",
                "categories = [",
                "Artifact identity",
            ],
        ),
        (
            "crates/bijux-dag-runtime/Cargo.toml",
            vec![
                "description = ",
                "documentation = ",
                "readme = ",
                "keywords = [",
                "categories = [",
                "Execution engine",
            ],
        ),
        (
            "crates/bijux-dag-app/Cargo.toml",
            vec![
                "description = ",
                "documentation = ",
                "readme = ",
                "keywords = [",
                "categories = [",
                "Application orchestration",
            ],
        ),
        (
            "crates/bijux-dag-cli/Cargo.toml",
            vec![
                "description = ",
                "documentation = ",
                "readme = ",
                "keywords = [",
                "categories = [",
                "Installable command-line package",
            ],
        ),
        (
            "crates/bijux-dag-testkit/Cargo.toml",
            vec![
                "publish = false",
                "description = ",
                "documentation = ",
                "readme = ",
                "keywords = [",
                "categories = [",
                "Deterministic fixtures",
            ],
        ),
        (
            "crates/bijux-cli-python/Cargo.toml",
            vec![
                "publish = false",
                "description = ",
                "homepage",
                "documentation = ",
                "readme = ",
                "keywords = [",
                "categories = [",
                "installing and launching the Bijux command runtime",
            ],
        ),
        (
            "crates/bijux-dev/Cargo.toml",
            vec![
                "publish = false",
                "description = ",
                "homepage",
                "readme = ",
                "Unified maintainer control plane",
            ],
        ),
    ] {
        let manifest = read_repo_file(path);
        for field in required {
            assert!(manifest.contains(field), "{path} is missing crate metadata field: {field}");
        }
    }
}

#[test]
fn workspace_package_boundary_keeps_support_crates_private() {
    let boundary = read_workspace_package_boundary();

    for entry in boundary.packages {
        let path = manifest_path_for(&entry.crate_name);
        let manifest = read_repo_file(&path);
        if entry.release_status == "private" {
            assert!(
                manifest.contains("publish = false"),
                "{path} must stay private to protect the public release boundary"
            );
        } else {
            assert!(
                !manifest.contains("publish = false"),
                "{path} must remain publishable as part of the public release boundary"
            );
        }
    }
}
#[test]
fn pinned_rust_toolchain_matches_workspace_rust_version() {
    let workspace_manifest = read_repo_file("Cargo.toml");
    let rust_toolchain = read_repo_file("rust-toolchain.toml");
    let workspace_rust_version =
        quoted_value_after(&workspace_manifest, "rust-version = ").expect("workspace rust-version");
    let channel = quoted_value_after(&rust_toolchain, "channel = ").expect("toolchain channel");
    assert_eq!(
        channel,
        format!("{workspace_rust_version}.0"),
        "rust-toolchain.toml must pin the exact patch release derived from workspace rust-version"
    );
}

#[test]
fn managed_release_toolchains_match_workspace_rust_version() {
    let workspace_manifest = read_repo_file("Cargo.toml");
    let workspace_rust_version =
        quoted_value_after(&workspace_manifest, "rust-version = ").expect("workspace rust-version");
    let exact_toolchain = format!("{workspace_rust_version}.0");

    for key in [
        "BIJUX_RELEASE_RUST_TOOLCHAIN",
        "BIJUX_CRATES_RELEASE_RUST_TOOLCHAIN",
        "BIJUX_PYPI_RUST_TOOLCHAIN",
    ] {
        assert_eq!(
            release_env_value_for_repo("bijux-core", key),
            exact_toolchain,
            "standards manifest release toolchain {key} must match workspace rust-version"
        );
    }

    assert_eq!(
        workflow_env_value_for_repo("bijux-core", "ci", "RUST_TOOLCHAIN_VERSION"),
        exact_toolchain,
        "ci workflow wrapper must provision the exact patch release derived from workspace rust-version"
    );

    let release_env = read_repo_file(".github/release.env");
    for key in [
        "BIJUX_RELEASE_RUST_TOOLCHAIN",
        "BIJUX_CRATES_RELEASE_RUST_TOOLCHAIN",
        "BIJUX_PYPI_RUST_TOOLCHAIN",
    ] {
        assert_eq!(
            shell_assignment_value(&release_env, key).as_deref(),
            Some(exact_toolchain.as_str()),
            ".github/release.env must keep {key} aligned with the workspace rust-version"
        );
    }

    let ci_workflow = workflow_document("ci.yml");
    assert_eq!(
        ci_workflow["env"]["RUST_TOOLCHAIN_VERSION"].as_str(),
        Some(exact_toolchain.as_str()),
        ".github/workflows/ci.yml must keep RUST_TOOLCHAIN_VERSION aligned with the workspace rust-version"
    );
}

#[test]
fn repo_owned_toolchain_overrides_match_workspace_rust_version() {
    let workspace_manifest = read_repo_file("Cargo.toml");
    let workspace_rust_version =
        quoted_value_after(&workspace_manifest, "rust-version = ").expect("workspace rust-version");
    let exact_toolchain = format!("{workspace_rust_version}.0");

    let governance_workflow = read_repo_file(".github/workflows/repository-governance.yml");
    let unquoted = format!("RUST_TOOLCHAIN_VERSION: {exact_toolchain}");
    let quoted = format!("RUST_TOOLCHAIN_VERSION: \"{exact_toolchain}\"");
    assert!(
        governance_workflow.contains(&unquoted) || governance_workflow.contains(&quoted),
        ".github/workflows/repository-governance.yml must keep RUST_TOOLCHAIN_VERSION aligned with the workspace rust-version"
    );

    let docs_deploy_env = read_repo_file(".github/docs-deploy.env");
    assert_eq!(
        shell_assignment_value(&docs_deploy_env, "BIJUX_DOCS_RUST_TOOLCHAIN").as_deref(),
        Some(exact_toolchain.as_str()),
        ".github/docs-deploy.env must keep BIJUX_DOCS_RUST_TOOLCHAIN aligned with the workspace rust-version"
    );
}

#[test]
fn github_workflows_pin_external_actions_to_commits() {
    for path in [
        ".github/workflows/ci.yml",
        ".github/workflows/deploy-docs.yml",
        ".github/workflows/github-policy.yml",
        ".github/workflows/bijux-std.yml",
    ] {
        let content = read_repo_file(path);
        let document: serde_yaml::Value = serde_yaml::from_str(&content).expect("valid workflow");
        for job in document["jobs"].as_mapping().expect("workflow jobs").values() {
            for step in job["steps"].as_sequence().into_iter().flatten() {
                if let Some(action) = step["uses"].as_str() {
                    if !action.starts_with("./") {
                        let (_, revision) = action.split_once('@').expect("action revision");
                        assert!(
                            is_hex_sha(revision),
                            "{path} must pin {action} to a full commit SHA"
                        );
                    }
                }
                if step["uses"]
                    .as_str()
                    .is_some_and(|action| action.starts_with("dtolnay/rust-toolchain@"))
                {
                    assert!(
                        step["with"]["toolchain"]
                            .as_str()
                            .is_some_and(|toolchain| !toolchain.is_empty()),
                        "{path} must declare the Rust toolchain input"
                    );
                }
            }
        }
    }
}

#[test]
fn github_release_workflow_publishes_release_assets_from_the_stamped_release_tree() {
    let workflow_allowlist = workflow_allowlist_for_repo("bijux-core");
    assert!(
        workflow_allowlist.iter().any(|entry| entry == "release-github"),
        "bijux-core workflow allowlist must include release-github for managed release publication"
    );
    assert!(
        repo_root().join(".github/workflows/release-github.yml").exists(),
        "bijux-core must carry the managed release-github workflow when allowlisted"
    );
}

#[test]
fn release_publication_stays_manual_and_decoupled_from_tag_pushes() {
    assert!(!repo_root().join(".github/workflows/release-on-tag.yml").exists());
    for name in [
        "release-crates.yml",
        "release-ghcr.yml",
        "release-github.yml",
        "release-pypi.yml",
        "deploy-docs.yml",
    ] {
        let workflow = workflow_document(name);
        let events = workflow["on"].as_mapping().expect("workflow events");
        assert_eq!(events.len(), 1, "{name} must expose only manual publication");
        assert!(events.contains_key(serde_yaml::Value::String("workflow_dispatch".into())));
        assert_eq!(
            workflow["on"]["workflow_dispatch"]["inputs"]["accepted_commit"]["required"].as_bool(),
            Some(true)
        );
        if name != "deploy-docs.yml" {
            assert_eq!(
                workflow["on"]["workflow_dispatch"]["inputs"]["release_tag"]["required"].as_bool(),
                Some(true)
            );
        }
        let jobs = workflow["jobs"].as_mapping().expect("workflow jobs");
        assert!(jobs.contains_key(serde_yaml::Value::String("publication_admission".into())));
        for (job_name, job) in jobs {
            if job_name.as_str() == Some("publication_admission") {
                continue;
            }
            let needs = &job["needs"];
            let admitted = needs.as_str() == Some("publication_admission")
                || needs.as_sequence().is_some_and(|dependencies| {
                    dependencies
                        .iter()
                        .any(|dependency| dependency.as_str() == Some("publication_admission"))
                });
            assert!(admitted, "{name} must admit publication before {job_name:?}");
        }
    }
    let validation = workflow_document("release-validation.yml");
    let events = validation["on"].as_mapping().expect("validation events");
    for event in ["pull_request", "workflow_dispatch"] {
        assert!(events.contains_key(serde_yaml::Value::String(event.into())));
    }
    assert!(!events.contains_key(serde_yaml::Value::String("push".into())));
}

#[test]
fn release_build_matrices_cover_cli_and_dag_release_families() {
    let boundary = read_workspace_package_boundary();
    let expected_public_crates = boundary.crates_io_publish_order;
    let expected_public_crates_value = expected_public_crates.join(" ");
    let manifest_build_matrix =
        release_env_json_value_for_repo("bijux-core", "BIJUX_RELEASE_BUILD_MATRIX_JSON");
    let manifest_build_entries =
        manifest_build_matrix.as_array().expect("release build matrix should be an array");
    let manifest_build_slugs: Vec<&str> = manifest_build_entries
        .iter()
        .map(|entry| entry["package_slug"].as_str().expect("package_slug"))
        .collect();
    assert_eq!(
        manifest_build_slugs,
        vec!["bijux-cli", "bijux-dag"],
        "release build matrix must stage both CLI and DAG release families"
    );
    let dag_build_entry = manifest_build_entries
        .iter()
        .find(|entry| entry["package_slug"].as_str() == Some("bijux-dag"))
        .expect("DAG release family entry");
    assert_eq!(
        dag_build_entry["artifacts_dir"].as_str(),
        Some("artifacts/rust"),
        "DAG release family should stage Rust release artifacts under artifacts/rust"
    );
    assert_eq!(
        dag_build_entry["build_targets"].as_str(),
        Some("build-dag-release-bundle"),
        "DAG release family should build the dedicated binary release bundle target"
    );

    let manifest_ghcr_matrix =
        release_env_json_value_for_repo("bijux-core", "BIJUX_GHCR_RELEASE_PACKAGE_MATRIX_JSON");
    let manifest_ghcr_slugs: Vec<&str> = manifest_ghcr_matrix
        .as_array()
        .expect("GHCR package matrix should be an array")
        .iter()
        .map(|entry| entry["package_slug"].as_str().expect("package_slug"))
        .collect();
    assert_eq!(
        manifest_ghcr_slugs,
        expected_public_crates.iter().map(String::as_str).collect::<Vec<_>>(),
        "GHCR package matrix must publish one container package for every public crate release"
    );
    for entry in manifest_ghcr_matrix
        .as_array()
        .expect("GHCR package matrix should be an array")
        .iter()
        .filter(|entry| {
            entry["package_slug"].as_str().is_some_and(|slug| slug.starts_with("bijux-dag-"))
        })
    {
        assert_eq!(
            entry["artifact_name"].as_str(),
            Some("bijux-dag-release"),
            "DAG crate GHCR packages must publish from the shared DAG release bundle artifact"
        );
    }
    assert_eq!(
        release_env_value_for_repo("bijux-core", "BIJUX_GHCR_RELEASE_ALLOWED_PACKAGES"),
        expected_public_crates_value,
        "GHCR release configuration must explicitly allow the full public crate release set"
    );

    let release_env = read_repo_file(".github/release.env");
    let release_build_matrix =
        json_shell_assignment_value(&release_env, "BIJUX_RELEASE_BUILD_MATRIX_JSON");
    let release_build_slugs: Vec<&str> = release_build_matrix
        .as_array()
        .expect("release build matrix assignment should be an array")
        .iter()
        .map(|entry| entry["package_slug"].as_str().expect("package_slug"))
        .collect();
    assert_eq!(
        release_build_slugs,
        vec!["bijux-cli", "bijux-dag"],
        ".github/release.env must stage both CLI and DAG release families"
    );

    let release_ghcr_matrix =
        json_shell_assignment_value(&release_env, "BIJUX_GHCR_RELEASE_PACKAGE_MATRIX_JSON");
    let release_ghcr_slugs: Vec<&str> = release_ghcr_matrix
        .as_array()
        .expect("GHCR release assignment should be an array")
        .iter()
        .map(|entry| entry["package_slug"].as_str().expect("package_slug"))
        .collect();
    assert_eq!(
        release_ghcr_slugs,
        expected_public_crates.iter().map(String::as_str).collect::<Vec<_>>(),
        ".github/release.env must publish one GHCR package for every public crate"
    );
    for entry in release_ghcr_matrix
        .as_array()
        .expect("GHCR release assignment should be an array")
        .iter()
        .filter(|entry| {
            entry["package_slug"].as_str().is_some_and(|slug| slug.starts_with("bijux-dag-"))
        })
    {
        assert_eq!(
            entry["artifact_name"].as_str(),
            Some("bijux-dag-release"),
            ".github/release.env must map DAG crate GHCR packages to the shared DAG release bundle artifact"
        );
    }
    assert_eq!(
        shell_assignment_value(&release_env, "BIJUX_GHCR_RELEASE_ALLOWED_PACKAGES").as_deref(),
        Some(expected_public_crates_value.as_str()),
        ".github/release.env must explicitly allow the full public crate GHCR release set"
    );
}

#[test]
fn ghcr_release_workflow_keeps_shared_build_families_intact() {
    let document = workflow_document("release-ghcr.yml");
    let command = document["jobs"]["resolve"]["steps"]
        .as_sequence()
        .expect("resolve steps")
        .iter()
        .filter_map(|step| step["run"].as_str())
        .find(|command| command.contains("filter_matrix()"))
        .expect("release matrix resolver");
    assert!(
        !command.contains("filter_matrix \"${build_matrix_json}\" \"${allowed_packages}\""),
        "release-ghcr must not filter the shared build matrix by the per-package GHCR allowlist"
    );
    assert!(
        command.contains("package_matrix_json=\"$(filter_matrix"),
        "release-ghcr should continue filtering the publish matrix by the GHCR allowlist"
    );
}

#[test]
fn pypi_release_workflow_builds_pypi_compatible_distributions() {
    let workflow_allowlist = workflow_allowlist_for_repo("bijux-core");
    assert!(
        workflow_allowlist.iter().any(|entry| entry == "release-pypi"),
        "bijux-core workflow allowlist must include release-pypi for Python compatibility publication"
    );
    assert!(
        repo_root().join(".github/workflows/release-pypi.yml").exists(),
        "bijux-core must carry the managed release-pypi workflow when allowlisted"
    );
}

#[test]
fn crates_release_automation_targets_public_cli_and_dag_crates() {
    let boundary = read_workspace_package_boundary();
    let workflow_support = read_repo_file("makes/gh.mk");
    let publish_support = read_repo_file("makes/rust.mk");
    let release_env = read_repo_file(".github/release.env");
    let expected_packages = boundary.crates_io_publish_order.join(" ");
    let workflow_packages = make_assignment_value(&workflow_support, "GH_CRATES_RELEASE_PACKAGES")
        .expect("GH_CRATES_RELEASE_PACKAGES");
    let publish_packages = make_assignment_value(&publish_support, "RUST_PUBLISH_PACKAGES")
        .expect("RUST_PUBLISH_PACKAGES");
    let release_packages = shell_assignment_value(&release_env, "BIJUX_CRATES_RELEASE_PACKAGES")
        .expect("BIJUX_CRATES_RELEASE_PACKAGES");
    let allowed_packages =
        shell_assignment_value(&release_env, "BIJUX_CRATES_RELEASE_ALLOWED_PACKAGES")
            .expect("BIJUX_CRATES_RELEASE_ALLOWED_PACKAGES");
    let private_crates = boundary
        .packages
        .iter()
        .filter(|entry| entry.release_status == "private")
        .map(|entry| entry.crate_name.as_str())
        .collect::<BTreeSet<_>>();
    let dag_public_crates = boundary
        .packages
        .iter()
        .filter(|entry| entry.product_family == "bijux-dag" && entry.release_status == "public")
        .map(|entry| entry.crate_name.as_str())
        .collect::<BTreeSet<_>>();
    let cli_index = boundary
        .crates_io_publish_order
        .iter()
        .position(|crate_name| crate_name == "bijux-cli")
        .expect("workspace package boundary must publish bijux-cli");
    for dag_crate in &dag_public_crates {
        let dag_index = boundary
            .crates_io_publish_order
            .iter()
            .position(|crate_name| crate_name == dag_crate)
            .unwrap_or_else(|| {
                panic!("workspace package boundary missing DAG public crate `{dag_crate}`")
            });
        assert!(
            dag_index < cli_index,
            "workspace package boundary must publish DAG crates before bijux-cli"
        );
    }

    assert!(
        workflow_packages == expected_packages,
        "release planning should publish the DAG crate family in dependency order before the CLI runtime crate"
    );
    assert!(
        workflow_support.contains("gh-release-plan-github"),
        "release planning support should include a dedicated GitHub Release lane"
    );
    assert!(
        publish_packages == expected_packages,
        "cargo publish automation should publish the DAG crate family in dependency order before the CLI runtime crate"
    );
    assert!(
        !workflow_support.contains("GH_CRATES_RELEASE_PACKAGES ?= bijux-cli bijux-cli-python"),
        "release planning must not treat the Python bridge crate as a crates.io package"
    );
    for private_crate in private_crates {
        assert!(
            !workflow_packages.split_whitespace().any(|crate_name| crate_name == private_crate),
            "release planning must keep private crates out of the crates.io publish order"
        );
        assert!(
            !publish_packages.split_whitespace().any(|crate_name| crate_name == private_crate),
            "cargo publish automation must keep private crates out of the crates.io publish order"
        );
        assert!(
            !release_packages.split_whitespace().any(|crate_name| crate_name == private_crate)
                && !allowed_packages
                    .split_whitespace()
                    .any(|crate_name| crate_name == private_crate),
            ".github/release.env must not reintroduce private crates into the public release set"
        );
    }
    assert!(
        publish_support.contains("build-dag-release-bundle"),
        "Rust release automation should expose a dedicated DAG binary bundle target for release workflows"
    );
    assert!(
        release_packages == expected_packages,
        ".github/release.env must export the DAG-first crates publish order"
    );
    assert!(
        allowed_packages == expected_packages,
        ".github/release.env must explicitly allow only the intended public crates release set"
    );
    assert!(
        publish_support.contains("RUST_PUBLISH_SKIP_EXISTING ?= 1"),
        "cargo publish automation should skip already-published crate versions by default"
    );
    assert!(
        publish_support.contains("already present on crates.io"),
        "cargo publish automation should emit an explicit skip path when a crate version already exists"
    );
    assert!(
        publish_support.contains("registry already has this release"),
        "cargo publish automation should recover cleanly when cargo publish reports a duplicate release"
    );
}

#[test]
fn generated_ported_snapshots_are_not_checked_in() {
    let ported_dir = repo_root().join("crates/bijux-cli/tests/data/golden/ported");
    if !ported_dir.exists() {
        return;
    }

    let entries = fs::read_dir(&ported_dir).expect("ported snapshot dir");
    let checked_in = entries
        .filter_map(Result::ok)
        .filter(|entry| entry.path().extension().is_some_and(|ext| ext == "json"))
        .map(|entry| entry.file_name().to_string_lossy().into_owned())
        .collect::<Vec<_>>();
    assert!(
        checked_in.is_empty(),
        "generated ported snapshots must stay out of the repo: {checked_in:?}"
    );
}

#[test]
fn vendored_runtime_registry_matches_root_contract() {
    let root_contract = read_repo_file("contracts/official_product_namespace_registry.json");
    let vendored_contract =
        read_repo_file("crates/bijux-cli/contracts/official_product_namespace_registry.json");
    assert_eq!(
        vendored_contract, root_contract,
        "published runtime crate must vendor the same official product registry contract as the workspace root"
    );
}
