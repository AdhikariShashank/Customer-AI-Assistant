
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel

# Import your actual input models here.
# Import your existing tool implementations through your
# application's dependency-injection/tool factory pattern.


@dataclass(frozen=True)
class OperationSpec:
    name: str
    arguments_schema: type[BaseModel]
    execute: Callable[..., Any]
    access: str  # "read" or "write"


def build_operation_registry(
    *,
    search_products,
    get_product,
    get_active_cart,
    add_item,
    remove_item,
    list_orders,
    get_order,
    place_order,
    schemas: dict[str, type[BaseModel]],
) -> dict[str, OperationSpec]:
    """Build an allowlisted registry using existing tool instances."""

    bindings = {
        "search_products": (search_products, "read"),
        "get_product": (get_product, "read"),
        "get_active_cart": (get_active_cart, "read"),
        "add_item": (add_item, "write"),
        "remove_item": (remove_item, "write"),
        "list_orders": (list_orders, "read"),
        "get_order": (get_order, "read"),
        "place_order": (place_order, "write"),
    }

    if set(schemas) != set(bindings):
        raise ValueError("Every registered operation needs an argument schema.")

    return {
        name: OperationSpec(
            name=name,
            arguments_schema=schemas[name],
            execute=tool,
            access=access,
        )
        for name, (tool, access) in bindings.items()
    }
