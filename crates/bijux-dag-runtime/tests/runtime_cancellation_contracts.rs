use bijux_dag_artifacts as _;
use bijux_dag_core as _;
use bijux_dag_runtime as _;
use ctrlc as _;
use hex as _;
use serde as _;
use serde_json as _;
use sha2 as _;
use tempfile as _;
use thiserror as _;

use bijux_dag_artifacts::{write_json_atomic_durable, RunStopRequest};
use bijux_dag_core::parse_graph_strict;
use bijux_dag_runtime::cancellation_is_terminal;
use bijux_dag_runtime::{Runtime, RuntimeConfig};
use serde_json::{json, Value};
use std::fs;
use std::path::Path;
use std::process::Command;
use std::sync::{Mutex, OnceLock};
use std::thread;
use std::time::Duration;

fn cancellation_test_lock() -> &'static Mutex<()> {
    static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
    LOCK.get_or_init(|| Mutex::new(()))
}

fn operator_cancellation_graph() -> String {
    json!({
        "spec": "bijux-dag/v0.1",
        "nodes": [
            {
                "id": "prepare",
                "kind": "const",
                "inputs": [],
                "outputs": [{"name": "value", "path": "prepare.txt"}],
                "params": {"value": "ready"}
            },
            {
                "id": "execute",
                "kind": "shell",
                "inputs": ["in"],
                "outputs": [{"name": "value", "path": "execute.txt"}],
                "params": {
                    "argv": [
                        "/bin/sh",
                        "-c",
                        "printf started > execute.started; sleep 2; cat ../inputs/prepare/in > ../outputs/execute.txt"
                    ]
                },
                "effects": ["filesystem"]
            },
            {
                "id": "publish",
                "kind": "shell",
                "inputs": ["in"],
                "outputs": [{"name": "value", "path": "publish.txt"}],
                "params": {
                    "argv": [
                        "/bin/sh",
                        "-c",
                        "cat ../inputs/execute/in > ../outputs/publish.txt"
                    ]
                },
                "effects": ["filesystem"]
            }
        ],
        "edges": [
            {"from": {"node_id": "prepare", "port": "value"}, "to": {"node_id": "execute", "port": "in"}},
            {"from": {"node_id": "execute", "port": "value"}, "to": {"node_id": "publish", "port": "in"}}
        ]
    })
    .to_string()
}

fn wait_for_running_execution(staging_dir: &Path) {
    // Cancellation must follow committed preparation and an actually running shell.
    let marker = staging_dir.join("nodes/execute/work/execute.started");
    for _ in 0..1000 {
        if marker.exists() {
            return;
        }
        thread::sleep(Duration::from_millis(10));
    }
    panic!("execute node did not start before cancellation: {}", marker.display());
}

fn read_node_trace(run_dir: &std::path::Path, node_id: &str) -> Value {
    serde_json::from_str(
        &fs::read_to_string(run_dir.join("nodes").join(node_id).join("trace.json"))
            .expect("read trace"),
    )
    .expect("parse trace")
}

fn read_timeline(run_dir: &std::path::Path) -> Vec<Value> {
    serde_json::from_str::<Value>(
        &fs::read_to_string(run_dir.join("observability.timeline.json")).expect("timeline"),
    )
    .expect("parse timeline")["entries"]
        .as_array()
        .expect("timeline entries")
        .clone()
}

#[test]
fn cancellation_requires_terminal_node_state() {
    assert!(cancellation_is_terminal(true, true));
    assert!(!cancellation_is_terminal(true, false));
}

#[test]
fn operator_cancellation_preserves_completed_nodes_and_marks_remaining_nodes_cancelled() {
    let _guard = cancellation_test_lock().lock().expect("cancellation test lock");
    let graph = parse_graph_strict(&operator_cancellation_graph()).expect("parse graph");
    let runtime = Runtime::new();
    let out = tempfile::tempdir().expect("temp");

    let run_id = "operator-interrupt";
    let staging_dir = out.path().join(format!("run.tmp-{run_id}"));
    let signaler = thread::spawn(move || {
        wait_for_running_execution(&staging_dir);
        let status = Command::new("kill")
            .args(["-INT", &std::process::id().to_string()])
            .status()
            .expect("send interrupt");
        assert!(status.success(), "interrupt delivery failed");
    });

    let run_path = runtime
        .run(
            &graph,
            out.path(),
            RuntimeConfig { jobs: 1, run_id: Some(run_id.to_string()), ..RuntimeConfig::default() },
        )
        .expect("cancelled run");
    signaler.join().expect("signaler thread");

    let manifest: Value = serde_json::from_str(
        &fs::read_to_string(run_path.join("manifest.json")).expect("manifest"),
    )
    .expect("parse manifest");
    assert_eq!(manifest["status"], "cancelled");
    assert_eq!(manifest["run_cancellation_cause"], "operator_interrupt");
    assert_eq!(manifest["node_counts"]["success"], 1);
    assert_eq!(manifest["node_counts"]["cancelled"], 2);

    let prepare = read_node_trace(&run_path, "prepare");
    assert_eq!(prepare["status"], "success");

    let execute = read_node_trace(&run_path, "execute");
    assert_eq!(execute["status"], "cancelled");
    assert_eq!(execute["failure"]["code"], "EXEC_CANCELLED");
    assert_eq!(execute["lifecycle_state"], "cancelled");
    assert_eq!(execute["transition_cause"], "CancelRequested");

    let publish = read_node_trace(&run_path, "publish");
    assert_eq!(publish["status"], "cancelled");
    assert_eq!(publish["skip_reason"]["reason"], "cancelled");
    assert_eq!(publish["lifecycle_state"], "cancelled");
    assert_eq!(publish["transition_cause"], "CancelRequested");

    let timeline = read_timeline(&run_path);
    let run_started_idx = timeline
        .iter()
        .position(|entry| entry["label"] == "run_started")
        .expect("run started timeline entry");
    let execute_cancel_idx = timeline
        .iter()
        .position(|entry| {
            entry["label"] == "node_cancelled"
                && entry["node_id"] == "execute"
                && entry["source_event"] == "node_finished"
        })
        .expect("execute cancellation timeline entry");
    let publish_cancel_idx = timeline
        .iter()
        .position(|entry| {
            entry["label"] == "node_cancelled"
                && entry["node_id"] == "publish"
                && entry["source_event"] == "node_skipped"
        })
        .expect("publish cancellation timeline entry");
    let run_completed_idx = timeline
        .iter()
        .position(|entry| entry["label"] == "run_completed")
        .expect("run completed timeline entry");
    assert!(timeline.iter().any(|entry| {
        entry["label"] == "node_cancelled"
            && entry["node_id"] == "execute"
            && entry["source_event"] == "node_finished"
    }));
    assert!(timeline.iter().any(|entry| {
        entry["label"] == "node_cancelled"
            && entry["node_id"] == "publish"
            && entry["source_event"] == "node_skipped"
    }));
    assert!(run_started_idx < execute_cancel_idx);
    assert!(execute_cancel_idx < publish_cancel_idx);
    assert!(publish_cancel_idx < run_completed_idx);
}

#[test]
fn stop_request_file_cancels_running_run_and_records_operator_request_cause() {
    let _guard = cancellation_test_lock().lock().expect("cancellation test lock");
    let out = tempfile::tempdir().expect("temp");
    let run_id = "stoppable";
    let staging_dir = out.path().join("run.tmp-stoppable");
    let stop_request_path = staging_dir.join("run.stop-request.json");
    let run_root = out.path().to_path_buf();
    let graph_json = operator_cancellation_graph();

    let runner = thread::spawn(move || {
        let graph = parse_graph_strict(&graph_json).expect("parse graph");
        Runtime::new().run(
            &graph,
            &run_root,
            RuntimeConfig { jobs: 1, run_id: Some(run_id.to_string()), ..RuntimeConfig::default() },
        )
    });

    wait_for_running_execution(&staging_dir);

    let request = RunStopRequest {
        schema_version: "run-stop-request/v0.1".to_string(),
        run_id: run_id.to_string(),
        requested_unix_ms: 42,
        source: "cli".to_string(),
        reason: None,
    };
    write_json_atomic_durable(
        &stop_request_path,
        &serde_json::to_value(&request).expect("request json"),
    )
    .expect("write stop request");

    let run_path = runner.join().expect("runner thread").expect("cancelled run");
    assert_eq!(run_path, out.path().join("run-stoppable"));

    let manifest: Value = serde_json::from_str(
        &fs::read_to_string(run_path.join("manifest.json")).expect("manifest"),
    )
    .expect("parse manifest");
    assert_eq!(manifest["status"], "cancelled");
    assert_eq!(manifest["run_cancellation_cause"], "operator_request");
    assert_eq!(manifest["node_counts"]["success"], 1);
    assert_eq!(manifest["node_counts"]["cancelled"], 2);
    assert!(run_path.join("run.stop-request.json").exists());

    let execute = read_node_trace(&run_path, "execute");
    assert_eq!(execute["status"], "cancelled");
    assert_eq!(execute["failure"]["code"], "EXEC_CANCELLED");

    let publish = read_node_trace(&run_path, "publish");
    assert_eq!(publish["status"], "cancelled");
    assert!(!run_path.join("nodes").join("publish").join("outputs").join("publish.txt").exists());

    let audit: Value =
        serde_json::from_str(&fs::read_to_string(run_path.join("run.audit.json")).expect("audit"))
            .expect("parse audit");
    assert!(audit.as_array().expect("audit array").iter().any(|entry| {
        entry["action"] == "cancel" && entry["source"] == "cli" && entry["ts"] == 42
    }));

    let timeline = read_timeline(&run_path);
    let cancel_idx = timeline
        .iter()
        .position(|entry| entry["label"] == "run_cancel_requested")
        .expect("cancel request timeline entry");
    let publish_idx = timeline
        .iter()
        .position(|entry| {
            entry["label"] == "node_cancelled"
                && entry["node_id"] == "publish"
                && entry["source_event"] == "node_skipped"
        })
        .expect("publish cancellation timeline entry");
    let run_completed_idx = timeline
        .iter()
        .position(|entry| entry["label"] == "run_completed")
        .expect("run completed timeline entry");
    assert!(cancel_idx < publish_idx);
    assert!(publish_idx < run_completed_idx);
}
