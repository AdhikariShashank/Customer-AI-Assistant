"""
Seed demo data.

Creates:
- 10 users
- 30 products
- 5 product categories
- carts
- cart items
- orders
- order items

Re-runnable:
- Clears products, carts, cart items, orders and order items
- Upserts users

Run:
    python -m scripts.seed
"""

import asyncio
from datetime import datetime, timedelta

from sqlalchemy import delete, select

from app.db import AsyncLocalSession
from app.models import (
    User,
    Product,
    Cart,
    CartItem,
    Order,
    OrderItem,
)
from app.enums.cart import CartStatus
from app.enums.product import ProductStatus
from app.security import hash_password


# ============================================================
# USERS
# ============================================================

USERS = [
    ("admin@shop.com", "admin123", "admin"),
    ("ajay@shop.com", "user123", "user"),
    ("sunny@shop.com", "user123", "user"),
    ("simi@shop.com", "user123", "user"),
    ("dik@shop.com", "user123", "user"),
    ("rahul@shop.com", "user123", "user"),
    ("neha@shop.com", "user123", "user"),
    ("rohit@shop.com", "user123", "user"),
    ("priya@shop.com", "user123", "user"),
    ("amit@shop.com", "user123", "user"),
]


# ============================================================
# PRODUCTS
# category, name, description, price, stock, status
# ============================================================

PRODUCTS = [
    # ---------------- Electronics ----------------
    (
        "Electronics",
        "Wireless Mouse",
        "2.4GHz ergonomic wireless mouse",
        19.99,
        100,
        ProductStatus.ACTIVE,
    ),
    (
        "Electronics",
        "Mechanical Keyboard",
        "RGB mechanical keyboard with blue switches",
        59.99,
        50,
        ProductStatus.ACTIVE,
    ),
    (
        "Electronics",
        "USB-C Hub",
        "7-in-1 aluminium USB-C hub",
        34.50,
        75,
        ProductStatus.ACTIVE,
    ),
    (
        "Electronics",
        "27 Inch Monitor",
        "1440p IPS monitor with 75Hz refresh rate",
        229.00,
        30,
        ProductStatus.ACTIVE,
    ),
    (
        "Electronics",
        "Noise Cancelling Headset",
        "Bluetooth over-ear noise cancelling headset",
        129.99,
        40,
        ProductStatus.ACTIVE,
    ),
    (
        "Electronics",
        "Webcam 1080p",
        "Auto-focus USB webcam",
        45.00,
        55,
        ProductStatus.ACTIVE,
    ),

    # ---------------- Computers ----------------
    (
        "Computers",
        "Laptop Stand",
        "Adjustable aluminium laptop stand",
        39.99,
        60,
        ProductStatus.ACTIVE,
    ),
    (
        "Computers",
        "External SSD 1TB",
        "Portable 1TB USB-C SSD",
        89.99,
        35,
        ProductStatus.ACTIVE,
    ),
    (
        "Computers",
        "USB Keyboard",
        "Compact wired USB keyboard",
        24.99,
        80,
        ProductStatus.ACTIVE,
    ),
    (
        "Computers",
        "Wireless Keyboard",
        "Slim wireless keyboard",
        44.99,
        45,
        ProductStatus.ACTIVE,
    ),
    (
        "Computers",
        "Gaming Mouse",
        "High precision gaming mouse",
        49.99,
        65,
        ProductStatus.ACTIVE,
    ),
    (
        "Computers",
        "Laptop Cooling Pad",
        "USB powered laptop cooling pad",
        29.99,
        50,
        ProductStatus.ACTIVE,
    ),

    # ---------------- Furniture ----------------
    (
        "Furniture",
        "Office Chair",
        "Ergonomic office chair with lumbar support",
        199.99,
        20,
        ProductStatus.ACTIVE,
    ),
    (
        "Furniture",
        "Study Table",
        "Wooden study table with storage",
        149.99,
        15,
        ProductStatus.ACTIVE,
    ),
    (
        "Furniture",
        "Bookshelf",
        "Five-level wooden bookshelf",
        119.99,
        25,
        ProductStatus.ACTIVE,
    ),
    (
        "Furniture",
        "Desk Mat",
        "Large felt desk mat",
        24.99,
        90,
        ProductStatus.ACTIVE,
    ),
    (
        "Furniture",
        "Monitor Stand",
        "Wooden monitor stand",
        39.99,
        40,
        ProductStatus.ACTIVE,
    ),
    (
        "Furniture",
        "Desk Lamp",
        "LED adjustable desk lamp",
        34.99,
        70,
        ProductStatus.ACTIVE,
    ),

    # ---------------- Clothing ----------------
    (
        "Clothing",
        "Cotton T-Shirt",
        "Comfortable regular-fit cotton T-shirt",
        19.99,
        100,
        ProductStatus.ACTIVE,
    ),
    (
        "Clothing",
        "Hoodie",
        "Warm cotton hoodie",
        49.99,
        70,
        ProductStatus.ACTIVE,
    ),
    (
        "Clothing",
        "Denim Jeans",
        "Regular fit denim jeans",
        59.99,
        60,
        ProductStatus.ACTIVE,
    ),
    (
        "Clothing",
        "Running Shoes",
        "Lightweight running shoes",
        79.99,
        45,
        ProductStatus.ACTIVE,
    ),
    (
        "Clothing",
        "Formal Shirt",
        "Slim fit formal shirt",
        39.99,
        50,
        ProductStatus.ACTIVE,
    ),
    (
        "Clothing",
        "Winter Jacket",
        "Water resistant winter jacket",
        99.99,
        25,
        ProductStatus.INACTIVE,
    ),

    # ---------------- Books ----------------
    (
        "Books",
        "Clean Code",
        "A handbook of agile software craftsmanship",
        34.99,
        40,
        ProductStatus.ACTIVE,
    ),
    (
        "Books",
        "Designing Data-Intensive Applications",
        "Modern distributed systems and data architecture",
        49.99,
        30,
        ProductStatus.ACTIVE,
    ),
    (
        "Books",
        "The Pragmatic Programmer",
        "Practical software engineering principles",
        39.99,
        35,
        ProductStatus.ACTIVE,
    ),
    (
        "Books",
        "Introduction to Algorithms",
        "Comprehensive algorithms reference",
        59.99,
        20,
        ProductStatus.ACTIVE,
    ),
    (
        "Books",
        "Python Crash Course",
        "Beginner friendly Python programming book",
        29.99,
        50,
        ProductStatus.ACTIVE,
    ),
    (
        "Books",
        "Legacy Java Guide",
        "Old Java programming reference",
        19.99,
        5,
        ProductStatus.DISCONTINUED,
    ),
]


# ============================================================
# CART PLAN
# ============================================================

CART_PLAN = {
    "ajay@shop.com": [
        ("Wireless Mouse", 1),
        ("Desk Mat", 2),
    ],
    "sunny@shop.com": [
        ("USB-C Hub", 1),
        ("Laptop Stand", 1),
    ],
    "simi@shop.com": [
        ("Webcam 1080p", 1),
        ("Office Chair", 1),
    ],
    "dik@shop.com": [
        ("Mechanical Keyboard", 1),
        ("Gaming Mouse", 1),
    ],
    "rahul@shop.com": [
        ("Cotton T-Shirt", 2),
        ("Running Shoes", 1),
    ],
    "neha@shop.com": [
        ("Clean Code", 1),
        ("Python Crash Course", 2),
    ],
}


# ============================================================
# ORDER PLAN
# user_email, status, days_ago, products
# ============================================================

ORDER_PLAN = [
    (
        "ajay@shop.com",
        "delivered",
        20,
        [
            ("Mechanical Keyboard", 1),
            ("Wireless Mouse", 1),
        ],
    ),
    (
        "ajay@shop.com",
        "shipped",
        4,
        [
            ("27 Inch Monitor", 1),
        ],
    ),
    (
        "ajay@shop.com",
        "returned",
        12,
        [
            ("Noise Cancelling Headset", 1),
        ],
    ),
    (
        "sunny@shop.com",
        "placed",
        1,
        [
            ("Laptop Stand", 2),
        ],
    ),
    (
        "sunny@shop.com",
        "delivered",
        30,
        [
            ("USB-C Hub", 1),
            ("Desk Mat", 1),
        ],
    ),
    (
        "sunny@shop.com",
        "cancelled",
        8,
        [
            ("Webcam 1080p", 1),
        ],
    ),
    (
        "simi@shop.com",
        "shipped",
        3,
        [
            ("Mechanical Keyboard", 1),
        ],
    ),
    (
        "simi@shop.com",
        "delivered",
        15,
        [
            ("Wireless Mouse", 2),
            ("Desk Mat", 1),
        ],
    ),
    (
        "simi@shop.com",
        "returned",
        22,
        [
            ("27 Inch Monitor", 1),
        ],
    ),
    (
        "dik@shop.com",
        "placed",
        2,
        [
            ("External SSD 1TB", 1),
            ("Laptop Stand", 1),
        ],
    ),
    (
        "rahul@shop.com",
        "delivered",
        40,
        [
            ("Running Shoes", 1),
            ("Cotton T-Shirt", 2),
        ],
    ),
    (
        "neha@shop.com",
        "cancelled",
        6,
        [
            ("Designing Data-Intensive Applications", 1),
        ],
    ),
]


# ============================================================
# MAIN
# ============================================================

async def main():

    async with AsyncLocalSession() as s:

        # ----------------------------------------------------
        # 1. Clear transactional/demo data
        # ----------------------------------------------------

        await s.execute(delete(OrderItem))
        await s.execute(delete(Order))

        await s.execute(delete(CartItem))
        await s.execute(delete(Cart))

        await s.execute(delete(Product))

        await s.commit()

        # ----------------------------------------------------
        # 2. Upsert users
        # ----------------------------------------------------

        users: dict[str, User] = {}

        for email, password, role in USERS:

            user = (
                await s.scalars(
                    select(User).where(User.email == email)
                )
            ).first()

            if not user:
                user = User(
                    email=email,
                    hashed_password=hash_password(password),
                    role=role,
                )

                s.add(user)

            else:
                user.role = role

            users[email] = user

        await s.commit()

        # Refresh IDs
        for user in users.values():
            await s.refresh(user)

        # ----------------------------------------------------
        # 3. Create products
        # ----------------------------------------------------

        products: list[Product] = []

        for (
            category,
            name,
            description,
            price,
            stock,
            status,
        ) in PRODUCTS:

            product = Product(
                name=name,
                description=description,
                category=category,
                price=price,
                stock=stock,
                status=status,
                product_metadata={
                    "source": "seed",
                    "featured": price > 100,
                },
            )

            s.add(product)
            products.append(product)

        await s.commit()

        # Refresh product IDs
        for product in products:
            await s.refresh(product)

        by_name = {
            product.name: product
            for product in products
        }

        # ----------------------------------------------------
        # 4. Create carts
        # ----------------------------------------------------

        carts: dict[str, Cart] = {}

        for email in CART_PLAN.keys():

            cart = Cart(
                user_id=users[email].id,
                status=CartStatus.ACTIVE,
            )

            s.add(cart)
            carts[email] = cart

        await s.commit()

        # ----------------------------------------------------
        # 5. Create cart items
        #
        # NOTE:
        # CartItem currently has user_id, not cart_id.
        # ----------------------------------------------------

        cart_item_count = 0

        for email, lines in CART_PLAN.items():

            for product_name, quantity in lines:

                product = by_name[product_name]

                cart_item = CartItem(
                    user_id=users[email].id,
                    product_id=product.id,
                    quantity=quantity,
                )

                s.add(cart_item)
                cart_item_count += 1

        await s.commit()

        # ----------------------------------------------------
        # 6. Create orders + order items
        # ----------------------------------------------------

        status_counts: dict[str, int] = {}

        for (
            email,
            status,
            days_ago,
            lines,
        ) in ORDER_PLAN:

            created_at = (
                datetime.now()
                - timedelta(days=days_ago)
            )

            order = Order(
                user_id=users[email].id,
                status=status,
                total=0.0,
                created_at=created_at,
            )

            s.add(order)

            # Get order.id
            await s.flush()

            total = 0.0

            for product_name, quantity in lines:

                product = by_name[product_name]

                item_total = product.price * quantity

                total += item_total

                order_item = OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    product_name=product.name,
                    price=product.price,
                    quantity=quantity,
                )

                s.add(order_item)

            order.total = round(total, 2)

            status_counts[status] = (
                status_counts.get(status, 0) + 1
            )

        await s.commit()

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print("\n======================================")
    print("Database seeded successfully!")
    print("======================================")

    print(f"Users       : {len(USERS)}")
    print(f"Products    : {len(PRODUCTS)}")
    print("Categories  : 5")
    print(f"Carts       : {len(CART_PLAN)}")
    print(f"Cart Items  : {cart_item_count}")
    print(f"Orders      : {len(ORDER_PLAN)}")

    print("\nOrder statuses:")

    for status, count in sorted(status_counts.items()):
        print(f"  {status:<12} : {count}")

    print("\nCategories:")

    categories = sorted(
        {
            product[0]
            for product in PRODUCTS
        }
    )

    for category in categories:
        count = sum(
            1
            for product in PRODUCTS
            if product[0] == category
        )

        print(f"  {category:<15} : {count} products")

    print("\nDemo credentials:")
    print("  Admin : admin@shop.com / admin123")
    print("  Users : ajay@shop.com / user123")
    print("          sunny@shop.com / user123")
    print("          simi@shop.com / user123")
    print("======================================\n")


if __name__ == "__main__":
    asyncio.run(main())