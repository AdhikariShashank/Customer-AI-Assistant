import logging

from app.agent.operation_descriptions import OUTPUT_DESCRIPTIONS
from app.planner.operations import build_operation_registry
from app.tools.cart import create_cart_tools
from app.tools.dependencies import cart_service_context, order_service_context, product_service_context
from app.tools.order import create_order_tools
from app.tools.product import create_product_tools

logger = logging.getLogger(__name__)


def build_application_dependencies():

    product_tools = create_product_tools(
        product_service_context
    )

    cart_tools = create_cart_tools(
        cart_service_context
    )

    order_tools = create_order_tools(
        order_service_context
    )

    all_tools = (
        product_tools
        + cart_tools
        + order_tools
    )

    # Build the argument schema mapping from the tools themselves.
    schemas = {
        tool.name: tool.args_schema
        for tool in all_tools
    }

    tools_by_name = {
        tool.name: tool
        for tool in all_tools
    }

    operation_registry = build_operation_registry(
        search_products=tools_by_name["search_products"],
        get_product=tools_by_name["get_product"],
        get_active_cart=tools_by_name["get_active_cart"],
        add_item=tools_by_name["add_item"],
        remove_item=tools_by_name["remove_item"],
        list_orders=tools_by_name["list_orders"],
        get_order=tools_by_name["get_order"],
        place_order=tools_by_name["place_order"],
        schemas=schemas,
        output_descriptions=OUTPUT_DESCRIPTIONS,
    )

    logger.info(
        "Registered operations: %s",
        list(operation_registry.keys()),
    )

    return operation_registry