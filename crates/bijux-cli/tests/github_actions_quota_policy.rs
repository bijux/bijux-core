#![forbid(unsafe_code)]
//! GitHub Actions trigger policy and runner-allocation guardrails.

use serde_yaml::{Mapping, Value};
use std::fs;
use std::path::{Path, PathBuf};

const DEPENDABOT_SKIP: &str = "github.event.pull_request.user.login != 'dependabot[bot]'";

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

#[test]
fn owned_product_pull_requests_skip_unrequired_dependency_runs() {
    for (workflow_name, document) in workflow_documents() {
        // Accepted shared controls provide required policy and producer evidence;
        // repository-owned product jobs retain the narrower allocation policy.
        if ["bijux-std.yml", "github-policy.yml", "pr-approval-policy.yml", "automerge-pr.yml"]
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
        }
    }
}

#[test]
fn only_repository_policy_and_standards_run_automatically_after_merge() {
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

    assert_eq!(
        main_push_workflows,
        vec!["bijux-std.yml", "github-policy.yml"],
        "only accepted policy and standards evidence may run automatically after merge"
    );
    assert_eq!(
        tag_push_workflows,
        vec!["github-policy.yml"],
        "tag pushes may produce repository policy evidence but never product or publication jobs"
    );
}
