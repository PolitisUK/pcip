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
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence
from uuid import UUID

from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient

from scripts import lookup_user_identity


SERVICE_BUS_NAMESPACE_ENV = "PCIP_OPERATIONS_SERVICEBUS_NAMESPACE"
SERVICE_BUS_QUEUE_ENV = "PCIP_OPERATIONS_QUEUE"
APPROVED_OPERATION = "lookup-user-identity"


class ProductionOperationError(RuntimeError):
    """Raised when an operational request is unsafe or malformed."""


@dataclass(frozen=True)
class OperationRequest:
    correlation_id: str
    email: str


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
    if not isinstance(payload, dict) or set(payload) != {"correlation_id", "email", "operation"}:
        raise ProductionOperationError("Production operation refused.")
    correlation_id = payload.get("correlation_id")
    email = payload.get("email")
    if payload.get("operation") != APPROVED_OPERATION or not isinstance(correlation_id, str) or not isinstance(email, str):
        raise ProductionOperationError("Production operation refused.")
    try:
        parsed_id = UUID(correlation_id)
    except (TypeError, ValueError) as exc:
        raise ProductionOperationError("Production operation refused.") from exc
    if str(parsed_id) != correlation_id.lower() or not email or len(email) > 254 or "\n" in email or "\r" in email:
        raise ProductionOperationError("Production operation refused.")
    return OperationRequest(correlation_id=correlation_id, email=email)


def _lookup_result(email: str) -> dict[str, Any]:
    """Call the exact existing CLI without permitting caller-controlled flags."""
    output = io.StringIO()
    errors = io.StringIO()
    try:
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            exit_code = lookup_user_identity.main(["--email", email])
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


def _message_body(message: Any) -> bytes:
    return b"".join(bytes(section) for section in message.body)


def _emit(correlation_id: str, *, status: str, result: dict[str, Any] | None = None) -> None:
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
            result = _lookup_result(request.email)
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
    except Exception:
        # Do not expose database, transport, message, or credential details.
        print("Production operation failed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
