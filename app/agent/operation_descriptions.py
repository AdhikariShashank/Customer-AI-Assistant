OUTPUT_DESCRIPTIONS = {
    "search_products": """
    Returns a dictionary with:
    - ok: boolean indicating whether the operation succeeded.
    - filters: object containing query, category, min_price, max_price.
    - products: list of product objects, each containing:
        - id: product ID.
        - name: product name.
        - category: product category.
        - description: product description.
        - price: product price.
        - stock: available stock.
    - pagination: object containing limit, offset, total, returned,
      and has_more.
    Use products.0.id to reference the first product's ID.
    Use products.0.name to reference the first product's name.
    For selecting a product by a field rather than position, use
    path="products" with select_by and select_field.
    """,

    "get_product": """
    Returns a dictionary with:
    - ok: boolean indicating whether the operation succeeded.
    - product: object containing:
        - id: product ID.
        - name: product name.
        - category: product category.
        - description: product description.
        - price: product price.
        - stock: available stock.
    Use product.id to reference the product ID.
    Use product.name to reference the product name.
    """,

    "get_active_cart": """
    Returns a dictionary with:
    - ok: boolean indicating whether the operation succeeded.
    - cart: object containing:
        - id: cart ID.
        - status: cart status.
        - items: list of cart item objects, each containing:
            - item_id: cart item ID used by remove_item.
            - product_id: ID of the product in the cart.
            - name: product name.
            - quantity: item quantity.
            - unit_price: unit price.
            - subtotal: item subtotal.
        - item_count: total quantity across all cart items.
        - total: cart total.
    Use cart.items, not cart.products.
    Each cart item uses product_id for the product ID and item_id
    for the cart item's own ID. These IDs are not interchangeable.
    To remove a product by product ID, select the matching item from
    cart.items using select_by={"field": "product_id", "value": <ID>}
    and extract item_id using select_field="item_id".
    Do not assume the cart item is at a fixed list position.
    """,

    "add_item": """
    Returns a dictionary with:
    - ok: boolean indicating whether the operation succeeded.
    - message: operation result message.
    - cart: updated cart object containing:
        - id: cart ID.
        - status: cart status.
        - items: list of cart item objects, each containing:
            - item_id: cart item ID.
            - product_id: product ID.
            - name: product name.
            - quantity: updated item quantity.
            - unit_price: unit price.
            - subtotal: updated item subtotal.
        - item_count: total quantity across all cart items.
        - total: updated cart total.
    Use cart.items to inspect the updated cart.
    """,

    "remove_item": """
    Returns a dictionary with:
    - ok: boolean indicating whether the operation succeeded.
    - message: operation result message, when available.
    - error: error details when the operation fails, when available.
    - cart: updated cart object on a successful removal, containing:
        - id: cart ID.
        - status: cart status.
        - items: remaining cart item objects, each containing:
            - item_id: cart item ID.
            - product_id: product ID.
            - name: product name.
            - quantity: item quantity.
            - unit_price: unit price.
            - subtotal: item subtotal.
        - item_count: total quantity across remaining cart items.
        - total: updated cart total.
    The tool's item_id argument requires a cart item ID, not a product ID.
    If the user identifies a product by product ID, first retrieve the
    active cart and resolve the matching cart item's item_id.
    Check ok before treating the operation as successful.
    """,

    "list_orders": """
    Returns a dictionary with:
    - ok: boolean indicating whether the operation succeeded.
    - orders: list of order objects, each containing:
        - id: order ID.
        - user_id: owner user ID.
        - status: order status.
        - total_amount: order total.
        - created_at: order creation timestamp.
        - items: list of order item objects, each containing:
            - order_item_id: order line-item ID.
            - product_id: product ID.
            - product_name: product name.
            - quantity: ordered quantity.
            - unit_price: unit price.
            - subtotal: line-item subtotal.
    - count: number of orders returned.
    - total_count: total number of matching orders.
    Use orders.0.id to reference the first returned order's ID.
    Do not assume that the first order is the order the user means
    unless the request or result establishes that.
    """,

    "get_order": """
    Returns a dictionary with:
    - ok: boolean indicating whether the operation succeeded.
    - order: object containing:
        - id: order ID.
        - user_id: owner user ID.
        - status: order status.
        - total_amount: order total.
        - created_at: order creation timestamp.
        - items: list of order item objects, each containing:
            - order_item_id: order line-item ID.
            - product_id: product ID.
            - product_name: product name.
            - quantity: ordered quantity.
            - unit_price: unit price.
            - subtotal: line-item subtotal.
    Use order.id to reference the order ID.
    """,

    "place_order": """
    Returns a dictionary with:
    - ok: boolean indicating whether the operation succeeded.
    - message: operation result message, when available.
    - order: created order object on success, containing:
        - id: new order ID.
        - user_id: owner user ID.
        - status: order status.
        - total_amount: order total.
        - created_at: order creation timestamp.
        - items: list of order item objects, each containing:
            - order_item_id: order line-item ID.
            - product_id: product ID.
            - product_name: product name.
            - quantity: ordered quantity.
            - unit_price: unit price.
            - subtotal: line-item subtotal.
    Check ok before treating the operation as successful.
    Use order.id to reference the newly created order ID.
    """,
}



OPERATION_ACCESS = {
    "search_products": "read",
    "get_product": "read",
    "get_active_cart": "read",
    "add_item": "write",
    "remove_item": "write",
    "list_orders": "read",
    "get_order": "read",
    "place_order": "write",
}