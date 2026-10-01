"""Seed demo data: 1 admin + several normal users, a product catalog, carts, and orders with a
variety of statuses (placed / shipped / delivered / returned / cancelled).

Re-runnable: it clears products, carts and orders each time and re-inserts them, and upserts the
users (so passwords/roles stay stable). Run:  python -m scripts.seed
"""
import asyncio
from datetime import datetime, timedelta

from sqlalchemy import select, delete

from app.db import AsyncLocalSession
from app.models import User, Product, CartItem, Order, OrderItem
from app.security import hash_password

# --- demo users (email, password, role) ---
USERS = [
    ("admin@shop.com", "admin123", "admin"),
    ("ajay@shop.com", "user123", "user"),
    ("sunny@shop.com", "user123", "user"),
    ("simi@shop.com", "user123", "user"),
    ("dik@shop.com", "user123", "user"),
]

# --- product catalog (name, description, price, stock) ---
PRODUCTS = [
    ("Wireless Mouse",       "2.4GHz ergonomic mouse",        19.99, 100),
    ("Mechanical Keyboard",  "RGB, blue switches",            59.99,  50),
    ("USB-C Hub",            "7-in-1 aluminium hub",          34.50,  75),
    ("27\" Monitor",         "1440p IPS, 75Hz",              229.00,  30),
    ("Laptop Stand",         "Adjustable aluminium stand",    39.99,  60),
    ("Noise-Cancel Headset", "Bluetooth over-ear",           129.99,  40),
    ("Webcam 1080p",         "Auto-focus USB webcam",         45.00,  55),
    ("Desk Mat",             "Large felt desk mat",           24.99,  90),
]


async def main():
    async with AsyncLocalSession() as s:
        # ---------- 1) wipe transactional data (children first) ----------
        await s.execute(delete(OrderItem))
        await s.execute(delete(Order))
        await s.execute(delete(CartItem))
        await s.execute(delete(Product))
        await s.commit()

        # ---------- 2) upsert users ----------
        users: dict[str, User] = {}
        for email, pw, role in USERS:
            u = (await s.scalars(select(User).where(User.email == email))).first()
            if not u:
                u = User(email=email, hashed_password=hash_password(pw), role=role)
                s.add(u)
            else:
                u.role = role
            users[email] = u
        await s.commit()
        for u in users.values():
            await s.refresh(u)

        # ---------- 3) products ----------
        products: list[Product] = []
        for name, desc, price, stock in PRODUCTS:
            p = Product(name=name, description=desc, price=price, stock=stock)
            s.add(p)
            products.append(p)
        await s.commit()
        for p in products:
            await s.refresh(p)
        by_name = {p.name: p for p in products}

        # ---------- 4) carts (current, not-yet-ordered items) ----------
        cart_plan = {
            "ajay@shop.com": [("Wireless Mouse", 1), ("Desk Mat", 2)],
            "sunny@shop.com":   [("USB-C Hub", 1)],
            "simi@shop.com": [("Webcam 1080p", 1), ("Laptop Stand", 1)],
        }
        for email, lines in cart_plan.items():
            for pname, qty in lines:
                s.add(CartItem(user_id=users[email].id, product_id=by_name[pname].id, quantity=qty))
        await s.commit()

        # ---------- 5) orders with varied statuses ----------
        # (user_email, status, days_ago, [(product_name, qty), ...])
        order_plan = [
            ("ajay@shop.com", "delivered",  20, [("Mechanical Keyboard", 1), ("Wireless Mouse", 1)]),
            ("ajay@shop.com", "shipped",     4, [("27\" Monitor", 1)]),
            ("ajay@shop.com", "returned",   12, [("Noise-Cancel Headset", 1)]),
            ("sunny@shop.com",   "placed",      1, [("Laptop Stand", 2)]),
            ("sunny@shop.com",   "delivered",  30, [("USB-C Hub", 1), ("Desk Mat", 1)]),
            ("sunny@shop.com",   "cancelled",   8, [("Webcam 1080p", 1)]),
            ("simi@shop.com", "shipped",     3, [("Mechanical Keyboard", 1)]),
            ("simi@shop.com", "delivered",  15, [("Wireless Mouse", 2), ("Desk Mat", 1)]),
            ("simi@shop.com", "returned",   22, [("27\" Monitor", 1)]),
        ]
        status_counts: dict[str, int] = {}
        for email, status, days_ago, lines in order_plan:
            when = datetime.now() - timedelta(days=days_ago)
            order = Order(user_id=users[email].id, status=status, total=0.0, created_at=when)
            s.add(order)
            await s.flush()  # get order.id

            total = 0.0
            for pname, qty in lines:
                p = by_name[pname]
                total += p.price * qty
                s.add(OrderItem(order_id=order.id, product_id=p.id,
                                product_name=p.name, price=p.price, quantity=qty))
            order.total = round(total, 2)
            status_counts[status] = status_counts.get(status, 0) + 1
        await s.commit()

    # ---------- summary ----------
    print("Seeded:")
    print(f"  users    : {len(USERS)}  (admin@shop.com/admin123 , ajay|sunny|simi@shop.com/user123)")
    print(f"  products : {len(PRODUCTS)}")
    print(f"  carts    : {sum(len(v) for v in cart_plan.values())} items across 3 users")
    print(f"  orders   : {len(order_plan)}  -> " + ", ".join(f"{k}:{v}" for k, v in sorted(status_counts.items())))


if __name__ == "__main__":
    asyncio.run(main())
