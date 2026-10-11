#![forbid(unsafe_code)]
//! GitHub Actions trigger policy and runner-allocation guardrails.

use serde_yaml::{Mapping, Value};
use std::fs;
use std::path::{Path, PathBuf};

const DEPENDABOT_SKIP: &str = "github.event.pull_request.user.login != 'dependabot[bot]'";
const UNVERIFIED_DEPENDENCY_NAME: &str = "${{ (github.event.pull_request.user.login == 'dependabot[bot]' || (github.event.pull_request.user.login == 'github-actions[bot]' && github.event.pull_request.head.ref == 'automation/dependency-lock-refresh')) && 'unverified dependency / ' || '' }}";

fn repo_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn mapping_entry<'a>(value: &'a Value, key: &str) -> Option<&'a Value> {
    value.as_mapping()?.get(Value::String(key.to_string()))
}

fn workflow_documents() -> Vec<(String, Value)> {
    let workflow_dir = repo_root().join(".github/workflows");
    let mut paths = fs::read_dir(&workflow_dir)
        .expect("workflow directory should exist")
        .map(|entry| entry.expect("workflow entry should be readable").path())
        .filter(|path| path.extension().is_some_and(|extension| extension == "yml"))
        .collect::<Vec<_>>();
    paths.sort();

    paths
        .into_iter()
        .map(|path| {
            let name = path
                .file_name()
                .expect("workflow should have a file name")
                .to_string_lossy()
                .into_owned();
            let source = fs::read_to_string(&path)
                .unwrap_or_else(|error| panic!("failed to read {}: {error}", path.display()));
            let document = serde_yaml::from_str(&source)
                .unwrap_or_else(|error| panic!("invalid workflow {}: {error}", path.display()));
            (name, document)
        })
        .collect()
}

fn workflow_events(document: &Value) -> &Mapping {
    mapping_entry(document, "on")
        .and_then(Value::as_mapping)
        .expect("workflow should define event mapping")
}

fn has_event(events: &Mapping, event: &str) -> bool {
    events.contains_key(Value::String(event.to_string()))
}

fn sequence_contains(value: Option<&Value>, expected: &str) -> bool {
    value.is_some_and(|value| match value {
        Value::String(item) => item == expected,
        Value::Sequence(items) => items.iter().any(|item| item.as_str() == Some(expected)),
        _ => false,
    })
}

fn workflow_source(name: &str) -> String {
    fs::read_to_string(repo_root().join(".github/workflows").join(name))
        .unwrap_or_else(|error| panic!("failed to read {name}: {error}"))
}

#[test]
fn dependabot_pull_requests_allocate_only_the_owner_review_notice() {
    for (workflow_name, document) in workflow_documents() {
        // Shared governance owns admission for its generated workflows.
        if [
            "bijux-std.yml",
            "github-policy.yml",
            "pr-approval-policy.yml",
            "automerge-pr.yml",
            "dependency-notice.yml",
        ]
        .contains(&workflow_name.as_str())
        {
            continue;
        }
        let events = workflow_events(&document);
        let handles_pull_requests = ["pull_request", "pull_request_target", "pull_request_review"]
            .iter()
            .any(|event| has_event(events, event));
        if !handles_pull_requests {
            continue;
        }

        let jobs = mapping_entry(&document, "jobs")
            .and_then(Value::as_mapping)
            .expect("workflow should define jobs");
        for (job_name, job) in jobs {
            let condition = mapping_entry(job, "if").and_then(Value::as_str).unwrap_or_default();
            assert!(
                condition.contains(DEPENDABOT_SKIP)
                    || condition.contains("github.event_name == 'workflow_dispatch'"),
                "{workflow_name} job {} must skip Dependabot PRs before allocating a runner",
                job_name.as_str().unwrap_or("<unknown>")
            );
            let name = mapping_entry(job, "name").and_then(Value::as_str).unwrap_or_default();
            assert!(
                name.starts_with(UNVERIFIED_DEPENDENCY_NAME),
                "{workflow_name} job {} must not claim a verified human context for a skipped dependency PR",
                job_name.as_str().unwrap_or("<unknown>")
            );
        }
    }
}

#[test]
fn accepted_pull_request_checks_are_not_repeated_on_push() {
    let mut main_push_workflows = Vec::new();
    let mut tag_push_workflows = Vec::new();

    for (workflow_name, document) in workflow_documents() {
        let events = workflow_events(&document);
        let Some(push) = events.get(Value::String("push".to_string())).and_then(Value::as_mapping)
        else {
            continue;
        };

        if sequence_contains(push.get(Value::String("branches".to_string())), "main") {
            main_push_workflows.push(workflow_name.clone());
        }
        if push.contains_key(Value::String("tags".to_string())) {
            tag_push_workflows.push(workflow_name);
        }
    }

    assert!(
        main_push_workflows.is_empty(),
        "accepted PR checks must not repeat on main: {main_push_workflows:?}"
    );
    assert!(
        tag_push_workflows.is_empty(),
        "publication entrypoints must remain manual: {tag_push_workflows:?}"
    );
}

#[test]
fn owner_review_notice_has_a_distinct_read_only_bot_context() {
    let document: Value = serde_yaml::from_str(&workflow_source("dependency-notice.yml"))
        .expect("dependency notice must be valid YAML");
    let events = workflow_events(&document);
    assert_eq!(events.len(), 1);
    assert!(has_event(events, "pull_request_target"));
    let jobs = mapping_entry(&document, "jobs").and_then(Value::as_mapping).expect("notice jobs");
    assert_eq!(jobs.len(), 1);
    let notice = jobs.get(Value::String("notice".to_string())).expect("notice job");
    assert_eq!(
        mapping_entry(notice, "name").and_then(Value::as_str),
        Some("dependency / owner review notice")
    );
    assert_eq!(
        mapping_entry(notice, "if").and_then(Value::as_str),
        Some("${{ github.event.pull_request.user.login == 'dependabot[bot]' || (github.event.pull_request.user.login == 'github-actions[bot]' && github.event.pull_request.head.ref == 'automation/dependency-lock-refresh') }}")
    );
    assert_eq!(mapping_entry(notice, "timeout-minutes").and_then(Value::as_i64), Some(1));
    let permissions = mapping_entry(&document, "permissions")
        .and_then(Value::as_mapping)
        .expect("read-only notice permissions");
    assert_eq!(permissions.len(), 1);
    assert_eq!(
        permissions.get(Value::String("contents".to_string())).and_then(Value::as_str),
        Some("read")
    );
    for step in mapping_entry(notice, "steps").and_then(Value::as_sequence).expect("notice steps") {
        assert!(
            mapping_entry(step, "uses").is_none(),
            "notice must not provision a product runtime"
        );
    }
}
