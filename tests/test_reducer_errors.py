from src.orchestrator.engine import OrchestrationEngine


def test_stale_revision_is_persisted_without_mutating_task_state():
    engine = OrchestrationEngine()
    task = {
        "id": "task-1",
        "state": "queued",
        "revision": 1,
        "attempt": 0,
        "payload": {"secret": "do-not-store"},
    }

    assert engine._reduce_task_state(
        task,
        "running",
        expected_revision=1,
        expected_attempt=0,
    )
    assert not engine._reduce_task_state(
        task,
        "completed",
        expected_revision=1,
        expected_attempt=0,
    )

    assert task["state"] == "running"
    assert task["revision"] == 2
    errors = engine.reducer_errors
    assert errors[-1]["reason"] == "stale_revision"
    assert errors[-1]["attempted_state"] == "completed"
    assert errors[-1]["current_state"] == "running"
    assert errors[-1]["expected_revision"] == 1
    assert errors[-1]["actual_revision"] == 2
    assert "payload" not in errors[-1]
    assert "do-not-store" not in str(errors[-1])


def test_stale_attempt_is_persisted_without_committing_transition():
    engine = OrchestrationEngine()
    task = {"id": "task-2", "state": "queued", "revision": 0, "attempt": 0}

    engine._begin_task_attempt(task)

    assert not engine._reduce_task_state(
        task,
        "running",
        expected_revision=0,
        expected_attempt=0,
    )

    assert task["state"] == "queued"
    assert task["revision"] == 0
    assert task["attempt"] == 1
    errors = engine.reducer_errors
    assert errors[-1]["reason"] == "stale_attempt"
    assert errors[-1]["expected_attempt"] == 0
    assert errors[-1]["actual_attempt"] == 1


def test_terminal_lifecycle_transition_is_rejected_separately():
    engine = OrchestrationEngine()
    task = {"id": "task-3", "state": "completed", "revision": 4, "attempt": 2}

    assert not engine._reduce_task_state(
        task,
        "running",
        expected_revision=4,
        expected_attempt=2,
    )

    assert task == {
        "id": "task-3",
        "state": "completed",
        "revision": 4,
        "attempt": 2,
    }
    assert engine.reducer_errors[-1]["reason"] == "terminal_state"


def test_reducer_error_store_is_bounded_and_sanitized():
    engine = OrchestrationEngine()

    for index in range(105):
        task = {
            "id": f"task-{index}",
            "state": "queued",
            "revision": 2,
            "attempt": 0,
            "payload": {"token": "private-token"},
        }
        assert not engine._reduce_task_state(
            task,
            "running",
            expected_revision=1,
            expected_attempt=0,
        )

    errors = engine.reducer_errors
    assert len(errors) == 100
    assert errors[0]["task_id"] == "task-5"
    assert errors[-1]["task_id"] == "task-104"
    assert all("payload" not in error for error in errors)
    assert "private-token" not in str(errors)


def test_reducer_error_report_summarizes_without_private_payloads():
    engine = OrchestrationEngine()
    stale_task = {
        "id": "task-stale",
        "state": "queued",
        "revision": 2,
        "attempt": 0,
        "payload": {"token": "private-token"},
    }
    terminal_task = {
        "id": "task-terminal",
        "state": "completed",
        "revision": 4,
        "attempt": 1,
        "payload": {"secret": "private-secret"},
    }

    assert not engine._reduce_task_state(
        stale_task,
        "running",
        expected_revision=1,
        expected_attempt=0,
    )
    assert not engine._reduce_task_state(
        terminal_task,
        "failed",
        expected_revision=4,
        expected_attempt=1,
    )

    report = engine.reducer_error_report()

    assert report["total"] == 2
    assert report["by_reason"] == {"stale_revision": 1, "terminal_state": 1}
    assert report["by_attempted_state"] == {"running": 1, "failed": 1}
    assert "payload" not in str(report)
    assert "private-token" not in str(report)
    assert "private-secret" not in str(report)

    report["recent"][0]["reason"] = "mutated"
    assert engine.reducer_errors[0]["reason"] == "stale_revision"
