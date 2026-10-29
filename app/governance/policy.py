
from collections.abc import Callable
from typing import TypeVar

from app.governance.schemas import PolicyContext, PolicyResult


Policy = Callable[[PolicyContext], PolicyResult | None]

P = TypeVar("P", bound=Policy)


def identified_policy(policy_id: str) -> Callable[[P], P]:
    """Attach a stable ID to a policy function."""

    def decorator(policy: P) -> P:
        setattr(policy, "__policy_id__", policy_id)
        return policy

    return decorator
