
"""
Seed demo data for Phase 1.

Creates:
- 10 users
- 30 products across 5 categories
- 6 carts
- Cart items
- 12 orders with order items

Re-runnable:
- Clears demo transactional data and products
- Upserts users without resetting existing passwords

Run:
    python -m scripts.seed
"""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

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

from app.security import hash_password


# ============================================================
# USERS
# email, password, role
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
    # Electronics
    ("Electronics", "Wireless Mouse",
     "2.4GHz ergonomic wireless mouse", "19.99", 100, "ACTIVE"),
    ("Electronics", "Mechanical Keyboard",
     "RGB mechanical keyboard with blue switches", "59.99", 50, "ACTIVE"),
    ("Electronics", "USB-C Hub",
     "7-in-1 aluminium USB-C hub", "34.50", 75, "ACTIVE"),
    ("Electronics", "27 Inch Monitor",
     "1440p IPS monitor with 75Hz refresh rate", "229.00", 30, "ACTIVE"),
    ("Electronics", "Noise Cancelling Headset",
     "Bluetooth over-ear noise cancelling headset", "129.99", 40, "ACTIVE"),
    ("Electronics", "Webcam 1080p",
     "Auto-focus USB webcam", "45.00", 55, "ACTIVE"),

    # Computers
    ("Computers", "Laptop Stand",
     "Adjustable aluminium laptop stand", "39.99", 60, "ACTIVE"),
    ("Computers", "External SSD 1TB",
     "Portable 1TB USB-C SSD", "89.99", 35, "ACTIVE"),
    ("Computers", "USB Keyboard",
     "Compact wired USB keyboard", "24.99", 80, "ACTIVE"),
    ("Computers", "Wireless Keyboard",
     "Slim wireless keyboard", "44.99", 45, "ACTIVE"),
    ("Computers", "Gaming Mouse",
     "High precision gaming mouse", "49.99", 65, "ACTIVE"),
    ("Computers", "Laptop Cooling Pad",
     "USB powered laptop cooling pad", "29.99", 50, "ACTIVE"),

    # Furniture
    ("Furniture", "Office Chair",
     "Ergonomic office chair with lumbar support", "199.99", 20, "ACTIVE"),
    ("Furniture", "Study Table",
     "Wooden study table with storage", "149.99", 15, "ACTIVE"),
    ("Furniture", "Bookshelf",
     "Five-level wooden bookshelf", "119.99", 25, "ACTIVE"),
    ("Furniture", "Desk Mat",
     "Large felt desk mat", "24.99", 90, "ACTIVE"),
    ("Furniture", "Monitor Stand",
     "Wooden monitor stand", "39.99", 40, "ACTIVE"),
    ("Furniture", "Desk Lamp",
     "LED adjustable desk lamp", "34.99", 70, "ACTIVE"),

    # Clothing
    ("Clothing", "Cotton T-Shirt",
     "Comfortable regular-fit cotton T-shirt", "19.99", 100, "ACTIVE"),
    ("Clothing", "Hoodie",
     "Warm cotton hoodie", "49.99", 70, "ACTIVE"),
    ("Clothing", "Denim Jeans",
     "Regular fit denim jeans", "59.99", 60, "ACTIVE"),
    ("Clothing", "Running Shoes",
     "Lightweight running shoes", "79.99", 45, "ACTIVE"),
    ("Clothing", "Formal Shirt",
     "Slim fit formal shirt", "39.99", 50, "ACTIVE"),
    ("Clothing", "Winter Jacket",
     "Water resistant winter jacket", "99.99", 25, "INACTIVE"),

    # Books
    ("Books", "Clean Code",
     "A handbook of agile software craftsmanship", "34.99", 40, "ACTIVE"),
    ("Books", "Designing Data-Intensive Applications",
     "Modern distributed systems and data architecture", "49.99", 30, "ACTIVE"),
    ("Books", "The Pragmatic Programmer",
     "Practical software engineering principles", "39.99", 35, "ACTIVE"),
    ("Books", "Introduction to Algorithms",
     "Comprehensive algorithms reference", "59.99", 20, "ACTIVE"),
    ("Books", "Python Crash Course",
     "Beginner friendly Python programming book", "29.99", 50, "ACTIVE"),
    ("Books", "Legacy Java Guide",
     "Old Java programming reference", "19.99", 5, "DISCONTINUED"),
]


# ============================================================
# CART PLAN
# email -> (product name, quantity)
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
# email, status, days ago, [(product name, quantity)]
# ============================================================

ORDER_PLAN = [
    ("ajay@shop.com", "delivered", 20, [
        ("Mechanical Keyboard", 1),
        ("Wireless Mouse", 1),
    ]),
    ("ajay@shop.com", "shipped", 4, [
        ("27 Inch Monitor", 1),
    ]),
    ("ajay@shop.com", "returned", 12, [
        ("Noise Cancelling Headset", 1),
    ]),
    ("sunny@shop.com", "placed", 1, [
        ("Laptop Stand", 2),
    ]),
    ("sunny@shop.com", "delivered", 30, [
        ("USB-C Hub", 1),
        ("Desk Mat", 1),
    ]),
    ("sunny@shop.com", "cancelled", 8, [
        ("Webcam 1080p", 1),
    ]),
    ("simi@shop.com", "shipped", 3, [
        ("Mechanical Keyboard", 1),
    ]),
    ("simi@shop.com", "delivered", 15, [
        ("Wireless Mouse", 2),
        ("Desk Mat", 1),
    ]),
    ("simi@shop.com", "returned", 22, [
        ("27 Inch Monitor", 1),
    ]),
    ("dik@shop.com", "placed", 2, [
        ("External SSD 1TB", 1),
        ("Laptop Stand", 1),
    ]),
    ("rahul@shop.com", "delivered", 40, [
        ("Running Shoes", 1),
        ("Cotton T-Shirt", 2),
    ]),
    ("neha@shop.com", "cancelled", 6, [
        ("Designing Data-Intensive Applications", 1),
    ]),
]


# ============================================================
# MAIN
# ============================================================

async def main():
    async with AsyncLocalSession() as session:

        # 1. Clear demo data in foreign-key dependency order.
        # WARNING: This deletes existing orders, carts and products
        # in the configured database. Use only for a demo/dev DB.

        await session.execute(delete(OrderItem))
        await session.execute(delete(Order))
        await session.execute(delete(CartItem))
        await session.execute(delete(Cart))
        await session.execute(delete(Product))
        await session.commit()

        # 2. Upsert users by email.
        users: dict[str, User] = {}

        for email, password, role in USERS:
            user = (
                await session.scalars(
                    select(User).where(User.email == email)
                )
            ).first()

            if user is None:
                user = User(
                    email=email,
                    hashed_password=hash_password(password),
                    role=role,
                )
                session.add(user)
            else:
                # Preserve existing password hashes.
                user.role = role

            users[email] = user

        await session.flush()

        # 3. Create products using the updated model fields.
        products: list[Product] = []

        for category, name, description, price, stock, status in PRODUCTS:
            product = Product(
                name=name,
                category=category,
                description=description,
                price=Decimal(price),
                stock=stock,
                is_active=(status == "ACTIVE"),
                metadata_json={
                    "source": "seed",
                    "featured": Decimal(price) > Decimal("100"),
                    "catalog_status": status,
                },
            )
            session.add(product)
            products.append(product)

        await session.flush()

        by_name = {product.name: product for product in products}

        # 4. Create one cart per user in CART_PLAN.
        carts: dict[str, Cart] = {}

        for email in CART_PLAN:
            cart = Cart(
                user_id=users[email].id,
                status="ACTIVE",
            )
            session.add(cart)
            carts[email] = cart

        await session.flush()

        # 5. Create cart items using cart_id and unit_price.
        cart_item_count = 0

        for email, lines in CART_PLAN.items():
            cart = carts[email]

            for product_name, quantity in lines:
                product = by_name[product_name]

                session.add(
                    CartItem(
                        cart_id=cart.id,
                        product_id=product.id,
                        quantity=quantity,
                        unit_price=product.price,
                    )
                )
                cart_item_count += 1

        # 6. Create orders and historical order items.
        status_counts: dict[str, int] = {}

        for email, status, days_ago, lines in ORDER_PLAN:
            created_at = datetime.now(timezone.utc) - timedelta(
                days=days_ago
            )

            total = Decimal("0.00")
            order_items: list[OrderItem] = []

            for product_name, quantity in lines:
                product = by_name[product_name]
                unit_price = product.price
                subtotal = unit_price * quantity
                total += subtotal

                order_items.append(
                    OrderItem(
                        product_id=product.id,
                        product_name=product.name,
                        quantity=quantity,
                        unit_price=unit_price,
                        subtotal=subtotal,
                    )
                )

            order = Order(
                user_id=users[email].id,
                status=status,
                total_amount=total,
                created_at=created_at,
                items=order_items,
            )
            session.add(order)

            status_counts[status] = status_counts.get(status, 0) + 1

        # Commit all seeded data together.
        await session.commit()

    print("\n======================================")
    print("Database seeded successfully!")
    print("======================================")
    print(f"Users       : {len(USERS)}")
    print(f"Products    : {len(PRODUCTS)}")
    print(f"Categories  : {len({p[0] for p in PRODUCTS})}")
    print(f"Carts       : {len(CART_PLAN)}")
    print(f"Cart Items  : {cart_item_count}")
    print(f"Orders      : {len(ORDER_PLAN)}")
    print("\nOrder statuses:")

    for status, count in sorted(status_counts.items()):
        print(f"  {status:<12}: {count}")

    print("\nDemo credentials:")
    print("  Admin : admin@shop.com / admin123")
    print("  Users : ajay@shop.com / user123")
    print("          sunny@shop.com / user123")
    print("          simi@shop.com / user123")
    print("======================================\n")


if __name__ == "__main__":
    asyncio.run(main())