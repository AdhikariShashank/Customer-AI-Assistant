
from collections.abc import Iterable

from app.governance.policy import Policy


class PolicyRegistry:
    """Registers policies and identifies governed operations."""

    def __init__(self) -> None:
        self._policies: dict[str, list[Policy]] = {}
        self._required_policies: dict[str, set[str]] = {}

    def register(
        self,
        operation: str,
        policy: Policy,
        *,
        required: bool = True,
    ) -> None:
        """Register a policy for an operation."""

        policies = self._policies.setdefault(operation, [])

        policy_id = getattr(policy, "__policy_id__", None)

        # Policy IDs are attached explicitly by the registration helper below.
        if policy_id is None:
            raise ValueError(
                "Every registered policy must have a stable policy ID."
            )

        if any(
            getattr(existing, "__policy_id__", None) == policy_id
            for existing in policies
        ):
            raise ValueError(
                f"Policy '{policy_id}' is already registered "
                f"for operation '{operation}'."
            )

        policies.append(policy)

        if required:
            self._required_policies.setdefault(operation, set()).add(
                policy_id
            )

    def policies_for(self, operation: str) -> tuple[Policy, ...]:
        """Return the policies registered for an operation."""

        return tuple(self._policies.get(operation, ()))

    def required_policy_ids(self, operation: str) -> frozenset[str]:
        """Return policy IDs that must be registered and evaluated."""

        return frozenset(self._required_policies.get(operation, set()))

    def is_governed(self, operation: str) -> bool:
        """Whether the operation has governance requirements."""

        return operation in self._required_policies

    def registered_operations(self) -> Iterable[str]:
        return tuple(self._policies)
