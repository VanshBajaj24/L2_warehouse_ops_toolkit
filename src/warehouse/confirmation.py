import secrets
import time
from dataclasses import dataclass, field

from .errors import ToolError

CONFIRMATION_TTL_SECONDS = 300  # 5 minutes


@dataclass
class PendingOperation:
    confirmation_id: str
    action: str
    params: dict
    preview: str
    irreversible: bool = False
    created_at: float = field(default_factory=time.time)
    executed: bool = False


class ConfirmationStore:
    def __init__(self):
        self._pending: dict[str, PendingOperation] = {}

    def create(
        self,
        action: str,
        params: dict,
        preview: str,
        irreversible: bool = False,
    ) -> dict:
        confirmation_id = f"CONF-{secrets.token_hex(4)}"
        op = PendingOperation(
            confirmation_id=confirmation_id,
            action=action,
            params=params,
            preview=preview,
            irreversible=irreversible,
        )
        self._pending[confirmation_id] = op
        result = {
            "confirmation_id": confirmation_id,
            "action": action,
            "preview": preview,
            "requires_confirmation": True,
        }
        if irreversible:
            result["irreversible"] = True
        return result

    def confirm(self, confirmation_id: str) -> PendingOperation:
        op = self._pending.get(confirmation_id)
        if op is None:
            raise ToolError(
                "INVALID_CONFIRMATION_ID",
                "The confirmation ID is invalid.",
                "The confirmation ID is invalid. Call the original tool again to get a new preview.",
            )
        if op.executed:
            raise ToolError(
                "ALREADY_CONFIRMED",
                "This operation was already confirmed and executed.",
                "This operation was already confirmed and executed.",
            )
        elapsed = time.time() - op.created_at
        if elapsed > CONFIRMATION_TTL_SECONDS:
            raise ToolError(
                "CONFIRMATION_EXPIRED",
                "The confirmation has expired.",
                "The confirmation has expired. Call the original tool again to get a fresh preview.",
            )
        op.executed = True
        return op
