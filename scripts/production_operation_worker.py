"""Fixed worker for one approved, queue-triggered production operation.

The worker is not a general command runner. GitHub can submit a message only;
it has no permission to start or override this secret-bearing Container Apps job.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient

from scripts import lookup_user_identity, platform_admin_dry_run, platform_admin_enable

SERVICE_BUS_NAMESPACE_ENV = "PCIP_OPERATIONS_SERVICEBUS_NAMESPACE"
SERVICE_BUS_QUEUE_ENV = "PCIP_OPERATIONS_QUEUE"
LOOKUP_OPERATION = "lookup-user-identity"
PLATFORM_ADMIN_DRY_RUN_OPERATION = "set-platform-admin-dry-run"
PLATFORM_ADMIN_ENABLE_OPERATION = "set-platform-admin"


class ProductionOperationError(RuntimeError):
    """Raised when an operational request is unsafe or malformed."""


@dataclass(frozen=True)
class OperationRequest:
    correlation_id: str
    operation: str
    email: str
    user_id: int | None = None


def _validate_runtime(environ: Mapping[str, str] | None = None) -> tuple[str, str]:
    values = os.environ if environ is None else environ
    if values.get("ENVIRONMENT", "").strip().lower() != "production":
        raise ProductionOperationError("Production operation refused.")
    for flag in ("RUN_MIGRATIONS", "RUN_RIVERMERE_PRODUCTION_DEMO_SEED"):
        if values.get(flag, "").strip().lower() != "false":
            raise ProductionOperationError("Production operation refused.")
    namespace = values.get(SERVICE_BUS_NAMESPACE_ENV, "").strip()
    queue = values.get(SERVICE_BUS_QUEUE_ENV, "").strip()
    if not namespace or not queue:
        raise ProductionOperationError("Production operation refused.")
    return namespace, queue


def parse_request(body: bytes) -> OperationRequest:
    try:
        payload = json.loads(body)
    except (TypeError, ValueError) as exc:
        raise ProductionOperationError("Production operation refused.") from exc
    if not isinstance(payload, dict):
        raise ProductionOperationError("Production operation refused.")
    correlation_id = payload.get("correlation_id")
    email = payload.get("email")
    operation = payload.get("operation")
    if not isinstance(correlation_id, str) or not isinstance(email, str):
        raise ProductionOperationError("Production operation refused.")
    try:
        parsed_id = UUID(correlation_id)
    except (TypeError, ValueError) as exc:
        raise ProductionOperationError("Production operation refused.") from exc
    if (
        str(parsed_id) != correlation_id.lower()
        or not email
        or len(email) > 254
        or "\n" in email
        or "\r" in email
    ):
        raise ProductionOperationError("Production operation refused.")
    if operation == LOOKUP_OPERATION:
        if set(payload) != {"correlation_id", "email", "operation"}:
            raise ProductionOperationError("Production operation refused.")
        return OperationRequest(
            correlation_id=correlation_id,
            operation=operation,
            email=email,
        )
    if operation in {
        PLATFORM_ADMIN_DRY_RUN_OPERATION,
        PLATFORM_ADMIN_ENABLE_OPERATION,
    }:
        if set(payload) != {"correlation_id", "email", "operation", "user_id"}:
            raise ProductionOperationError("Production operation refused.")
        user_id = payload.get("user_id")
        if type(user_id) is not int or user_id <= 0:
            raise ProductionOperationError("Production operation refused.")
        return OperationRequest(
            correlation_id=correlation_id,
            operation=operation,
            email=email,
            user_id=user_id,
        )
    raise ProductionOperationError("Production operation refused.")


def _run_fixed_cli(
    main: Callable[[Sequence[str]], int], argv: list[str]
) -> dict[str, Any]:
    """Run one internally selected CLI while suppressing all unapproved output."""
    output = io.StringIO()
    errors = io.StringIO()
    try:
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            exit_code = main(argv)
    except SystemExit as exc:
        exit_code = int(exc.code) if isinstance(exc.code, int) else 2
    if exit_code != 0:
        raise ProductionOperationError("Production operation refused.")
    try:
        result = json.loads(output.getvalue())
    except ValueError as exc:
        raise ProductionOperationError("Production operation refused.") from exc
    if not isinstance(result, dict):
        raise ProductionOperationError("Production operation refused.")
    return result


def _valid_memberships(value: Any) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, dict)
        and set(item) == {"organisation_id", "role", "is_active"}
        and type(item["organisation_id"]) is int
        and isinstance(item["role"], str)
        and type(item["is_active"]) is bool
        for item in value
    )


def _validated_result(request: OperationRequest) -> dict[str, Any]:
    if request.operation == LOOKUP_OPERATION:
        result = _run_fixed_cli(lookup_user_identity.main, ["--email", request.email])
        if (
            set(result) != {"user_id", "active", "is_platform_admin", "memberships"}
            or type(result["user_id"]) is not int
            or type(result["active"]) is not bool
            or type(result["is_platform_admin"]) is not bool
            or not _valid_memberships(result["memberships"])
        ):
            raise ProductionOperationError("Production operation refused.")
        return result

    if (
        request.operation == PLATFORM_ADMIN_DRY_RUN_OPERATION
        and request.user_id is not None
    ):
        result = _run_fixed_cli(
            platform_admin_dry_run.main,
            ["--email", request.email, "--expected-user-id", str(request.user_id)],
        )
        if (
            set(result)
            != {
                "user_id",
                "active",
                "current_is_platform_admin",
                "intended_is_platform_admin",
                "would_change",
                "memberships",
                "memberships_unchanged",
                "account_fields_unchanged",
            }
            or type(result["user_id"]) is not int
            or result["user_id"] != request.user_id
            or type(result["active"]) is not bool
            or type(result["current_is_platform_admin"]) is not bool
            or type(result["intended_is_platform_admin"]) is not bool
            or type(result["would_change"]) is not bool
            or type(result["memberships_unchanged"]) is not bool
            or type(result["account_fields_unchanged"]) is not bool
            or not result["memberships_unchanged"]
            or not result["account_fields_unchanged"]
            or not _valid_memberships(result["memberships"])
            or (
                result["active"]
                and (
                    not result["intended_is_platform_admin"]
                    or result["would_change"]
                    != (not result["current_is_platform_admin"])
                )
            )
            or (
                not result["active"]
                and (
                    result["intended_is_platform_admin"]
                    != result["current_is_platform_admin"]
                    or result["would_change"]
                )
            )
        ):
            raise ProductionOperationError("Production operation refused.")
        return result
    if request.operation == PLATFORM_ADMIN_ENABLE_OPERATION and request.user_id is not None:
        try:
            result = platform_admin_enable.execute_platform_admin_enable(
                email=request.email,
                expected_user_id=request.user_id,
            ).approved_result()
        except platform_admin_enable.PlatformAdminEnableError as exc:
            raise ProductionOperationError("Production operation refused.") from exc
        if (
            set(result)
            != {
                "user_id",
                "active",
                "previous_is_platform_admin",
                "is_platform_admin",
                "changed",
                "memberships",
                "memberships_unchanged",
                "account_fields_unchanged",
            }
            or type(result["user_id"]) is not int
            or result["user_id"] != request.user_id
            or result["active"] is not True
            or result["previous_is_platform_admin"] is not False
            or result["is_platform_admin"] is not True
            or result["changed"] is not True
            or result["memberships_unchanged"] is not True
            or result["account_fields_unchanged"] is not True
            or not _valid_memberships(result["memberships"])
        ):
            raise ProductionOperationError("Production operation refused.")
        return result
    raise ProductionOperationError("Production operation refused.")


def _message_body(message: Any) -> bytes:
    return b"".join(bytes(section) for section in message.body)


def _emit(
    correlation_id: str, *, status: str, result: dict[str, Any] | None = None
) -> None:
    payload: dict[str, Any] = {"correlation_id": correlation_id, "status": status}
    if result is not None:
        payload["result"] = result
    print(json.dumps(payload, sort_keys=True), flush=True)


def process_one_request(client: Any, queue: str) -> int:
    with client.get_queue_receiver(queue_name=queue, max_wait_time=20) as receiver:
        messages = receiver.receive_messages(max_message_count=1, max_wait_time=20)
        if len(messages) != 1:
            return 2
        message = messages[0]
        try:
            request = parse_request(_message_body(message))
            result = _validated_result(request)
        except ProductionOperationError:
            # Invalid or refused requests are consumed without echoing their body.
            receiver.complete_message(message)
            return 2
        receiver.complete_message(message)
        _emit(request.correlation_id, status="succeeded", result=result)
        return 0


def _service_bus_client(namespace: str) -> ServiceBusClient:
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    return ServiceBusClient(fully_qualified_namespace=namespace, credential=credential)


def main(
    argv: Sequence[str] | None = None,
    *,
    client_factory: Callable[[str], Any] = _service_bus_client,
    environ: Mapping[str, str] | None = None,
) -> int:
    """Receive and run exactly one validated request from the dedicated queue."""
    if argv:
        print("Production operation refused.", file=sys.stderr)
        return 2
    try:
        namespace, queue = _validate_runtime(environ)
        with client_factory(namespace) as client:
            return process_one_request(client, queue)
    except ProductionOperationError:
        print("Production operation refused.", file=sys.stderr)
        return 2
    except Exception:  # noqa: BLE001 - external failures must remain sanitised.
        # Do not expose database, transport, message, or credential details.
        print("Production operation failed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
