import pytest

from src.orchestrator.workflow import (
    StepStatus,
    WorkflowManager,
    WorkflowStep,
    WorkflowValidationError,
)


def test_cleanup_without_retry_dependency_is_rejected_before_dispatch():
    manager = WorkflowManager()
    workflow = manager.create_workflow("retry-artifacts")
    events = []
    producer = WorkflowStep(
        "produce",
        lambda: events.append("produce"),
        retries=2,
        produces_artifacts=["run-output"],
    )
    cleanup = WorkflowStep(
        "cleanup",
        lambda: events.append("cleanup"),
        cleanup_artifacts=["run-output"],
    )
    workflow.add_step(producer).add_step(cleanup)

    with pytest.raises(WorkflowValidationError):
        manager.execute_workflow(workflow.id)

    assert workflow.status is StepStatus.PENDING
    assert producer.status is StepStatus.PENDING
    assert cleanup.status is StepStatus.PENDING
    assert events == []
    audit = manager.audit_records()[-1]
    assert audit["event"] == "artifact_cleanup_rejected"
    assert audit["reason"] == "retry_dependency_not_satisfied"
    assert audit["artifact_count"] == 1
    assert "payload" not in audit
    assert "result" not in audit


def test_cleanup_waits_for_retryable_producer_before_removing_artifact():
    manager = WorkflowManager()
    workflow = manager.create_workflow("retry-artifacts")
    attempts = []
    cleanup_events = []

    def flaky_producer():
        attempts.append("attempt")
        if len(attempts) == 1:
            raise RuntimeError("temporary failure")
        return {"artifact": "run-output"}

    producer = WorkflowStep(
        "produce",
        flaky_producer,
        retries=1,
        produces_artifacts=["run-output"],
    )
    cleanup = WorkflowStep(
        "cleanup",
        lambda: cleanup_events.append("cleanup"),
        depends_on=[producer.id],
        cleanup_artifacts=["run-output"],
    )
    workflow.add_step(producer).add_step(cleanup)

    assert manager.execute_workflow(workflow.id)
    assert workflow.status is StepStatus.COMPLETED
    assert producer.status is StepStatus.COMPLETED
    assert producer.attempts == 2
    assert cleanup.status is StepStatus.COMPLETED
    assert cleanup_events == ["cleanup"]
    assert any(
        record["event"] == "workflow_step_retry"
        for record in manager.audit_records()
    )


def test_cleanup_before_retryable_producer_is_rejected_even_with_dependency():
    manager = WorkflowManager()
    workflow = manager.create_workflow("retry-artifacts")
    producer = WorkflowStep(
        "produce",
        lambda: "done",
        retries=1,
        produces_artifacts=["run-output"],
    )
    cleanup = WorkflowStep(
        "cleanup",
        lambda: None,
        depends_on=[producer.id],
        cleanup_artifacts=["run-output"],
    )
    workflow.add_step(cleanup).add_step(producer)

    with pytest.raises(WorkflowValidationError):
        manager.execute_workflow(workflow.id)

    assert workflow.status is StepStatus.PENDING
    assert cleanup.status is StepStatus.PENDING
