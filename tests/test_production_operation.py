from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import yaml

import scripts.production_operation_worker as worker


def workflow_step(workflow: str, name: str) -> str:
    """Return one named GitHub Actions step without coupling tests to offsets."""
    marker = f"      - name: {name}\n"
    _, found, remainder = workflow.partition(marker)
    assert found, f"workflow step {name!r} is missing"
    return remainder.partition("      - name: ")[0]


def worker_identity_filters(workflow: str) -> list[str]:
    """Extract the jq worker-template checks that receive the identity input."""
    return re.findall(
        r'jq -e --arg image [^\n]*--arg identity "\$OPERATIONS_WORKER_IDENTITY"[^\n]* \'\n(.*?)\n\s*\' >/dev/null',
        workflow,
        flags=re.DOTALL,
    )


EXPECTED_WORKER_IDENTITY = (
    "/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/rg-pcip-prod/"
    "providers/Microsoft.ManagedIdentity/userAssignedIdentities/pcip-production-operations-identity"
)
OBSERVED_WORKER_IDENTITY = EXPECTED_WORKER_IDENTITY.replace("resourceGroups", "resourcegroups")
WORKER_IMAGE = "pcipproductionnevsxrlbacr.azurecr.io/pcip@sha256:" + "a" * 64
WORKER_PROVENANCE = "b" * 40


def approved_worker_job(identity: str = OBSERVED_WORKER_IDENTITY) -> dict:
    return {
        "identity": {"type": "UserAssigned", "userAssignedIdentities": {identity: {}}},
        "properties": {
            "provisioningState": "Succeeded",
            "configuration": {
                "triggerType": "Event",
                "replicaTimeout": 300,
                "replicaRetryLimit": 0,
                "eventTriggerConfig": {
                    "scale": {
                        "minExecutions": 0,
                        "maxExecutions": 1,
                        "pollingInterval": 15,
                        "rules": [
                            {
                                "type": "azure-servicebus",
                                "identity": identity,
                                "metadata": {
                                    "queueName": "approved-operations",
                                    "namespace": "pcip-production-operations.servicebus.windows.net",
                                },
                            }
                        ],
                    }
                },
                "registries": [{"server": "pcipproductionnevsxrlbacr.azurecr.io", "identity": identity}],
                "secrets": [{"name": "database-url", "identity": identity, "keyVaultUrl": "https://example.test/secret"}],
            },
            "template": {
                "containers": [
                    {
                        "name": "production-operation",
                        "image": WORKER_IMAGE,
                        "command": ["python", "-m", "scripts.production_operation_worker"],
                        "env": [
                            {"name": "DATABASE_URL", "secretRef": "database-url"},
                            {"name": "PCIP_OPERATIONS_WORKER_PROVENANCE", "value": WORKER_PROVENANCE},
                        ],
                        "resources": {"cpu": 0.25, "memory": "0.5Gi"},
                    }
                ]
            },
        },
    }


def worker_filter_accepts(jq_filter: str, job: dict) -> bool:
    assert shutil.which("jq"), "jq is required by the protected workflow checks"
    result = subprocess.run(
        [
            "jq",
            "-e",
            "--arg",
            "image",
            WORKER_IMAGE,
            "--arg",
            "provenance",
            WORKER_PROVENANCE,
            "--arg",
            "identity",
            EXPECTED_WORKER_IDENTITY,
            "--arg",
            "registry",
            "pcipproductionnevsxrlbacr.azurecr.io",
            jq_filter,
        ],
        input=json.dumps(job),
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


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
    assert "group: pcip-production-control" in workflow
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


def test_release_and_rollback_retain_an_independently_approved_worker_artifact():
    promotion = Path(".github/workflows/promote-release.yml").read_text()
    rollback = Path(".github/workflows/rollback-release.yml").read_text()
    promotion_worker_check = workflow_step(
        promotion,
        "Verify the independently pinned production-operations worker",
    )
    rollback_worker_check = workflow_step(
        rollback,
        "Verify the independently pinned production-operations worker",
    )

    assert promotion.index("Verify the independently pinned production-operations worker") < promotion.index(
        "Enable the approved production Rivermere startup runner"
    )
    assert rollback.index("Verify the independently pinned production-operations worker") < rollback.index(
        "Verify rollback readiness"
    )

    for worker_check in (promotion_worker_check, rollback_worker_check):
        # Disabled/not-yet-provisioned infrastructure remains an explicit,
        # backwards-compatible skip. Enabled infrastructure fails closed.
        assert 'case "${PRODUCTION_OPERATIONS_ENABLED:-false}" in' in worker_check
        assert "''|false)" in worker_check
        assert "worker artifact verification skipped" in worker_check
        assert "true)" in worker_check
        assert "PCIP_PRODUCTION_OPERATIONS_ENABLED must be true or false." in worker_check
        assert 'test -n "${!value}"' in worker_check
        assert '[[ "$OPERATIONS_WORKER_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]]' in worker_check
        assert '[[ "$OPERATIONS_WORKER_REVISION" =~ ^[0-9a-f]{40}$ ]]' in worker_check
        assert "OPERATIONS_WORKER_IDENTITY" in worker_check
        assert 'expected_image="$PRODUCTION_ACR.azurecr.io/$IMAGE_REPOSITORY@$OPERATIONS_WORKER_DIGEST"' in worker_check
        assert "contains(tags, 'sha-$OPERATIONS_WORKER_REVISION')" in worker_check
        assert ".properties.template.containers[0].image == $image" in worker_check
        assert '"PCIP_OPERATIONS_WORKER_PROVENANCE" and .value == $provenance' in worker_check
        assert "az containerapp job update" not in worker_check
        assert "az containerapp job start" not in worker_check
        assert "|| true" not in worker_check

        # The fixed event-driven worker and its security-critical template
        # are proven without coupling the worker digest to App Service.
        assert '.identity.type == "UserAssigned"' in worker_check
        assert "def same_resource_id($expected):" in worker_check
        assert "ascii_downcase" in worker_check
        assert "map(ascii_downcase)" in worker_check
        assert "same_resource_id($identity)" in worker_check
        assert '--arg identity "$OPERATIONS_WORKER_IDENTITY"' in worker_check
        assert '(.properties.configuration.registries | length) == 1' in worker_check
        assert '.server == $registry and (.identity | same_resource_id($identity))' in worker_check
        assert '.name == "database-url" and (.identity | same_resource_id($identity))' in worker_check
        assert '.properties.configuration.triggerType == "Event"' in worker_check
        assert '"scripts.production_operation_worker"' in worker_check
        assert '"DATABASE_URL" and .secretRef == "database-url"' in worker_check
        assert '.type == "azure-servicebus" and (.identity | same_resource_id($identity))' in worker_check

    # Historical application rollbacks keep the approved worker, rather than
    # replacing it with a possibly pre-worker application image.
    assert "historical App" in rollback_worker_check
    assert "ROLLBACK_DIGEST" not in rollback_worker_check
    assert "IMAGE_DIGEST" not in promotion_worker_check


def test_all_production_control_paths_serialize_at_job_scope_without_blocking_staging():
    promotion = Path(".github/workflows/promote-release.yml").read_text()
    rollback = Path(".github/workflows/rollback-release.yml").read_text()
    operation = Path(".github/workflows/production-operation.yml").read_text()

    for workflow in (promotion, rollback, operation):
        assert "group: pcip-production-control" in workflow
        assert "cancel-in-progress: false" in workflow
    assert "group: pcip-release-promotion" not in promotion
    assert "group: pcip-production-operations" not in operation
    assert "group: pcip-staging-release" in promotion
    assert promotion.index("group: pcip-staging-release") < promotion.index("group: pcip-production-control")
    assert operation.index("group: pcip-production-control") < operation.index(
        "Validate the fixed operation and deployed release evidence"
    )


def test_operations_worker_provenance_is_immutable_and_caller_cannot_select_it():
    workflow = Path(".github/workflows/production-operation.yml").read_text()
    bicep = Path("infra/production-operations.bicep").read_text()

    assert "PCIP_PRODUCTION_OPERATIONS_WORKER_DIGEST" in workflow
    assert "PCIP_PRODUCTION_OPERATIONS_WORKER_REVISION" in workflow
    assert "PCIP_PRODUCTION_OPERATIONS_WORKER_IDENTITY" in workflow
    assert "contains(tags, 'sha-$OPERATIONS_WORKER_REVISION')" in workflow
    assert "workerProvenanceRevision" in bicep
    assert "PCIP_OPERATIONS_WORKER_PROVENANCE" in bicep
    assert "operationsWorkerDigest" in bicep
    assert "operationsWorkerProvenanceRevision" in bicep
    assert "worker_image" not in workflow
    assert "az containerapp job update" not in workflow
    assert "az containerapp job start" not in workflow


def test_operations_workflow_keeps_independent_worker_validation_and_no_write_privilege_expansion():
    workflow = Path(".github/workflows/production-operation.yml").read_text()
    bicep = Path("infra/production-operations.bicep").read_text()

    assert ".properties.template.containers[0].image == $image" in workflow
    assert '.identity.type == "UserAssigned"' in workflow
    assert "def same_resource_id($expected):" in workflow
    assert "map(ascii_downcase)" in workflow
    assert "same_resource_id($identity)" in workflow
    assert 'expected_image="DOCKER|$PRODUCTION_ACR.azurecr.io/$IMAGE_REPOSITORY@$PRODUCTION_IMAGE_DIGEST"' in workflow
    assert "az containerapp job update" not in workflow
    assert "az containerapp job start" not in workflow
    assert "Contributor" not in bicep
    assert "operationsWorkflowJobReader" in bicep
    assert "operationsWorkflowQueueSender" in bicep


def test_worker_identity_checks_accept_casing_only_differences_and_reject_other_resource_ids():
    workflows = [
        Path(".github/workflows/production-operation.yml").read_text(),
        Path(".github/workflows/promote-release.yml").read_text(),
        Path(".github/workflows/rollback-release.yml").read_text(),
    ]
    filters = [jq_filter for workflow in workflows for jq_filter in worker_identity_filters(workflow)]
    assert len(filters) == 5
    assert all(worker_filter_accepts(jq_filter, approved_worker_job()) for jq_filter in filters)

    for replacement in (
        EXPECTED_WORKER_IDENTITY.replace("rg-pcip-prod", "rg-other"),
        EXPECTED_WORKER_IDENTITY.replace("11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"),
        EXPECTED_WORKER_IDENTITY.replace("pcip-production-operations-identity", "same-basename-in-a-different-path"),
    ):
        assert all(not worker_filter_accepts(jq_filter, approved_worker_job(replacement)) for jq_filter in filters)


def test_worker_identity_checks_reject_multiple_or_mismatched_identity_references():
    filters = [
        jq_filter
        for workflow in (
            Path(".github/workflows/production-operation.yml").read_text(),
            Path(".github/workflows/promote-release.yml").read_text(),
            Path(".github/workflows/rollback-release.yml").read_text(),
        )
        for jq_filter in worker_identity_filters(workflow)
    ]
    different_identity = EXPECTED_WORKER_IDENTITY.replace(
        "pcip-production-operations-identity", "pcip-production-operations-other"
    )

    multiple = approved_worker_job()
    multiple["identity"]["userAssignedIdentities"][different_identity] = {}
    assert all(not worker_filter_accepts(jq_filter, multiple) for jq_filter in filters)

    for path in (
        ("properties", "configuration", "registries", 0, "identity"),
        ("properties", "configuration", "secrets", 0, "identity"),
        ("properties", "configuration", "eventTriggerConfig", "scale", "rules", 0, "identity"),
    ):
        mismatched = copy.deepcopy(approved_worker_job())
        target = mismatched
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = different_identity
        assert all(not worker_filter_accepts(jq_filter, mismatched) for jq_filter in filters)


def test_workflow_result_contract_is_limited_to_approved_non_sensitive_fields():
    workflow = open(".github/workflows/production-operation.yml", encoding="utf-8").read()

    assert "[\"active\", \"is_platform_admin\", \"memberships\", \"user_id\"]" in workflow
    assert "password_hash" not in workflow
    assert "connection-string" not in workflow.lower()
    assert "existing@example.org" not in workflow


def test_operation_result_polling_orders_by_time_and_fails_on_query_errors_but_tolerates_delay():
    workflow = Path(".github/workflows/production-operation.yml").read_text()
    result_step = workflow_step(workflow, "Retrieve the approved non-sensitive result")

    assert "order by TimeGenerated asc" in result_step
    assert "_timestamp_d" not in result_step
    assert "logs=$(az monitor log-analytics query" in result_step
    assert "2>/dev/null" not in result_step
    assert "|| true" not in result_step
    # A successful empty log result is polled for propagation delay; only a
    # genuine Azure query error exits under the step's set -euo pipefail.
    assert "set -euo pipefail" in result_step
    assert "for attempt in {1..30}; do" in result_step
    assert "sleep 10" in result_step
    assert "[\"active\", \"is_platform_admin\", \"memberships\", \"user_id\"]" in result_step


def test_operations_infrastructure_bootstraps_a_user_assigned_identity_before_the_job():
    bicep = open("infra/production-operations.bicep", encoding="utf-8").read()

    assert "targetScope = 'resourceGroup'" in bicep
    assert "resource operationsWorkerIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31'" in bicep
    assert "name: operationsWorkerIdentityName" in bicep
    assert "resource operationsJob 'Microsoft.App/jobs@2025-01-01'" in bicep
    assert bicep.index("resource operationsWorkerIdentity") < bicep.index("resource operationsJob")
    assert "dependsOn: [\n    operationsAcrPull\n    operationsDatabaseSecretReader\n    operationsQueueReceiver\n  ]" in bicep
    assert "type: 'UserAssigned'" in bicep
    assert "'${operationsWorkerIdentity.id}': {}" in bicep
    assert bicep.count("identity: operationsWorkerIdentity.id") == 3
    assert "operationsJob.identity.principalId" not in bicep
    assert "SystemAssigned" not in bicep
    assert "identity: 'system'" not in bicep


def test_operations_infrastructure_is_event_driven_and_least_privilege():
    bicep = open("infra/production-operations.bicep", encoding="utf-8").read()

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
    assert bicep.count("principalId: operationsWorkerIdentity.properties.principalId") == 3
    assert "4633458b-17de-408a-b874-0445c86b69e6" in bicep
    assert "7f951dda-4ed3-4680-a7ca-43fe172d538d" in bicep
    assert "69a216fc-b8fb-44d8-bc22-1f3c2cd27a39" in bicep
    assert "4f6d3b9b-027b-4f4c-9142-0e5a2a2247e0" in bicep
    assert "az containerapp job start" not in bicep
    assert "Contributor" not in bicep
