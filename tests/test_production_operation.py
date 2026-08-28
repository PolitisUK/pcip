from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest
import yaml

import scripts.production_operation_worker as worker


def production_environment(**overrides: str) -> dict[str, str]:
    values = {
        "ENVIRONMENT": "production",
        "RUN_MIGRATIONS": "false",
        "RUN_RIVERMERE_PRODUCTION_DEMO_SEED": "false",
        "PCIP_OPERATIONS_SERVICEBUS_NAMESPACE": "operations.servicebus.windows.net",
        "PCIP_OPERATIONS_QUEUE": "approved-operations",
    }
    values.update(overrides)
    return values


class FakeReceiver:
    def __init__(self, messages):
        self.messages = messages
        self.completed = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def receive_messages(self, **_kwargs):
        return self.messages

    def complete_message(self, message):
        self.completed.append(message)


class FakeClient:
    def __init__(self, receiver):
        self.receiver = receiver

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get_queue_receiver(self, **_kwargs):
        return self.receiver


def request_message(**overrides):
    payload = {
        "correlation_id": str(uuid4()),
        "operation": "lookup-user-identity",
        "email": "existing@example.org",
    }
    payload.update(overrides)
    return SimpleNamespace(body=[json.dumps(payload).encode()]), payload


def test_worker_calls_only_the_existing_lookup_cli_and_emits_non_sensitive_result(monkeypatch, capsys):
    message, request = request_message()
    receiver = FakeReceiver([message])
    captured = []

    def lookup_main(argv):
        captured.append(argv)
        print(json.dumps({"user_id": 7, "active": True, "is_platform_admin": False, "memberships": []}))
        return 0

    monkeypatch.setattr(worker.lookup_user_identity, "main", lookup_main)
    assert worker.main(client_factory=lambda _namespace: FakeClient(receiver), environ=production_environment()) == 0

    assert captured == [["--email", "existing@example.org"]]
    assert receiver.completed == [message]
    rendered = capsys.readouterr().out
    assert request["email"] not in rendered
    assert json.loads(rendered)["result"]["user_id"] == 7


@pytest.mark.parametrize(
    "payload",
    [
        {"operation": "set-platform-admin"},
        {"email": "existing@example.org\n--unexpected"},
        {"correlation_id": "not-a-uuid"},
        {"unexpected": "value"},
    ],
)
def test_worker_refuses_unapproved_or_malformed_messages_without_echoing_content(monkeypatch, capsys, payload):
    message, request = request_message(**payload)
    receiver = FakeReceiver([message])
    monkeypatch.setattr(worker.lookup_user_identity, "main", lambda _argv: pytest.fail("lookup must not run"))

    assert worker.main(client_factory=lambda _namespace: FakeClient(receiver), environ=production_environment()) == 2
    captured = capsys.readouterr()
    assert receiver.completed == [message]
    assert request["email"] not in captured.out + captured.err


def test_worker_suppresses_lookup_error_output_that_could_contain_the_email(monkeypatch, capsys):
    message, request = request_message()
    receiver = FakeReceiver([message])

    def refused_lookup(_argv):
        print(request["email"], file=sys.stderr)
        return 2

    monkeypatch.setattr(worker.lookup_user_identity, "main", refused_lookup)
    assert worker.main(client_factory=lambda _namespace: FakeClient(receiver), environ=production_environment()) == 2

    captured = capsys.readouterr()
    assert receiver.completed == [message]
    assert request["email"] not in captured.out + captured.err


@pytest.mark.parametrize(
    "values",
    [
        production_environment(ENVIRONMENT="staging"),
        production_environment(RUN_MIGRATIONS="true"),
        production_environment(RUN_RIVERMERE_PRODUCTION_DEMO_SEED="true"),
        production_environment(PCIP_OPERATIONS_QUEUE=""),
    ],
)
def test_worker_fails_closed_when_runtime_safeguards_are_not_present(capsys, values):
    assert worker.main(environ=values) == 2
    assert capsys.readouterr().err == "Production operation refused.\n"


def test_worker_rejects_caller_controlled_cli_arguments(capsys):
    assert worker.main(["--sql", "select 1"], environ=production_environment()) == 2
    assert capsys.readouterr().err == "Production operation refused.\n"


def test_workflow_is_protected_queue_mediated_and_never_starts_a_job():
    workflow = open(".github/workflows/production-operation.yml", encoding="utf-8").read()
    assert yaml.compose(workflow) is not None

    assert "workflow_dispatch:" in workflow
    assert "environment: production" in workflow
    assert "group: pcip-production-operations" in workflow
    assert "- lookup-user-identity" in workflow
    assert "test \"$OPERATION\" = \"lookup-user-identity\"" in workflow
    assert "https://servicebus.azure.net" in workflow
    assert "PCIP_OPERATION_EMAIL" not in workflow
    assert "az containerapp job start" not in workflow
    assert "--command" not in workflow
    assert "--args" not in workflow
    assert "--sql" not in workflow
    assert "::add-mask::$OPERATION_EMAIL" in workflow
    assert "vars.AZURE_PRODUCTION_OPERATIONS_CLIENT_ID" in workflow
    assert "client-id: ${{ vars.AZURE_CLIENT_ID }}" not in workflow
    assert "Production operations must be dispatched from main." in workflow
    assert "Production is not configured for the supplied immutable image." in workflow
    assert "scripts.production_operation_worker" in workflow
    assert "ContainerAppConsoleLogs_CL" in workflow


def test_workflow_result_contract_is_limited_to_approved_non_sensitive_fields():
    workflow = open(".github/workflows/production-operation.yml", encoding="utf-8").read()

    assert "[\"active\", \"is_platform_admin\", \"memberships\", \"user_id\"]" in workflow
    assert "password_hash" not in workflow
    assert "connection-string" not in workflow.lower()
    assert "existing@example.org" not in workflow


def test_operations_infrastructure_is_event_driven_and_least_privilege():
    bicep = open("infra/production-operations.bicep", encoding="utf-8").read()

    assert "targetScope = 'resourceGroup'" in bicep
    assert "resource operationsServiceBus" in bicep
    assert "disableLocalAuth: true" in bicep
    assert "resource operationsQueue" in bicep
    assert "resource operationsEnvironment" in bicep
    assert "triggerType: 'Event'" in bicep
    assert "type: 'azure-servicebus'" in bicep
    assert "scripts.production_operation_worker" in bicep
    assert "keyVaultUrl: databaseUrlSecret.properties.secretUriWithVersion" in bicep
    assert "scope: databaseUrlSecret" in bicep
    assert "scope: operationsQueue" in bicep
    assert "69a216fc-b8fb-44d8-bc22-1f3c2cd27a39" in bicep
    assert "4f6d3b9b-027b-4f4c-9142-0e5a2a2247e0" in bicep
    assert "az containerapp job start" not in bicep
    assert "Contributor" not in bicep
