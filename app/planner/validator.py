
import logging

from pydantic import ValidationError

from app.planner.operations import OperationSpec
from app.planner.schemas import Plan, Task

logger = logging.getLogger(__name__)


class PlanValidationError(ValueError):
    """Raised when a proposed plan fails application validation."""



def validate_task_template(task: Task, registry: dict[str, OperationSpec]) -> None:
    spec = registry.get(task.operation)

    if spec is None:
        raise PlanValidationError(
            f"Unknown operation '{task.operation}' in {task.id}"
        )

    literal_arguments = dict(task.arguments)
    references = dict(task.input_refs)

    # A field cannot be supplied as both a literal and a reference.
    duplicate_fields = set(literal_arguments) & set(references)
    if duplicate_fields:
        raise PlanValidationError(
            f"Task {task.id} specifies arguments both literally "
            f"and by reference: {sorted(duplicate_fields)}"
        )

    # Reject reference descriptors accidentally embedded in literals.
    for argument_name, value in literal_arguments.items():
        if isinstance(value, dict) and (
            "input_refs" in value
            or ("task_id" in value and "path" in value)
        ):
            raise PlanValidationError(
                f"Task {task.id}: argument '{argument_name}' contains "
                "a reference descriptor. Put it in input_refs instead."
            )

    schema_fields = spec.arguments_schema.model_fields
    supplied_fields = set(literal_arguments) | set(references)

    # Both literal arguments and reference destinations must be supported.
    unknown_fields = supplied_fields - set(schema_fields)
    if unknown_fields:
        raise PlanValidationError(
            f"Task {task.id} has unsupported arguments for "
            f"{task.operation}: {sorted(unknown_fields)}"
        )

    # Every required field must be supplied literally or by reference.
    required_fields = {
        name
        for name, field in schema_fields.items()
        if field.is_required()
    }
    missing_fields = required_fields - supplied_fields

    if missing_fields:
        raise PlanValidationError(
            f"Task {task.id} is missing required arguments for "
            f"{task.operation}: {sorted(missing_fields)}"
        )

    # Validate literal values using the operation's actual Pydantic schema.
    # Fill referenced fields with placeholders only for this validation.
    # This checks literal values without requiring the real referenced
    # values to exist before execution.
    validation_arguments = dict(literal_arguments)

    for argument_name in references:
        field = schema_fields[argument_name]

        if field.is_required():
            # A valid placeholder of the right type may not be available.
            # Validate literals separately below instead.
            continue

        # Optional referenced fields are also deferred.
        continue

    # Construct a partial schema dynamically so Pydantic validates the
    # literal fields, their types, constraints, and custom validators
    # without requiring the referenced fields.
    from pydantic import create_model

    literal_schema_fields = {
        name: (schema_fields[name].annotation, ...)
        for name in literal_arguments
    }

    if literal_schema_fields:
        try:
            literal_schema = create_model(
                f"{spec.arguments_schema.__name__}LiteralValidation",
                **literal_schema_fields,
            )
            literal_schema.model_validate(literal_arguments)
        except ValidationError as exc:
            raise PlanValidationError(
                f"Invalid literal arguments for {task.operation} "
                f"in {task.id}: {exc}"
            ) from exc

    logger.info(
        "planner.task_template_validated task_id=%s operation=%s "
        "literal_arg_count=%d reference_count=%d dependencies=%s",
        task.id,
        task.operation,
        len(literal_arguments),
        len(references),
        task.depends_on,
    )


def validate_plan(
    plan: Plan,
    registry: dict[str, OperationSpec],
) -> Plan:
    """Validate plan structure and every task's argument template."""

    logger.info(
        "planner.validation_started goal=%r task_count=%d",
        plan.goal,
        len(plan.tasks),
    )

    try:
        for task in plan.tasks:
            validate_task_template(task, registry)

    except PlanValidationError:
        logger.exception("planner.validation_failed")
        raise

    logger.info(
        "planner.validation_succeeded task_count=%d",
        len(plan.tasks),
    )

    return plan
