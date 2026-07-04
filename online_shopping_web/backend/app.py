from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request as urlrequest

from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
CORS(app)

AGI_EVENTS_ENDPOINT = "http://127.0.0.1:8001/api/events"
AGI_BASE_URL = "http://127.0.0.1:8001"
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "shop_data.sqlite"
_DEMO_DB_RESET_DONE = False
DEMO_VERBOSE_LOGS = os.getenv("SHOP_VERBOSE_LOGS", "").strip().lower() in {"1", "true", "yes"}


PRODUCTS = [
    {
        "id": "p001",
        "name": "AeroBeat Pro Wireless Headphones",
        "category": "Electronics",
        "brand": "AeroBeat",
        "price": 129.99,
        "originalPrice": 179.99,
        "stock": 16,
        "rating": 4.7,
        "image": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=900&q=80",
        "description": "Noise-cancelling over-ear headphones with 38-hour battery life and fast charging.",
        "features": ["Active noise cancelling", "Bluetooth 5.3", "38-hour battery", "Memory foam earcups"],
        "similarProductIds": ["p002", "p003"],
        "cheaperAlternativeIds": ["p002"],
    },
    {
        "id": "p002",
        "name": "SoundLite Everyday Headphones",
        "category": "Electronics",
        "brand": "SoundLite",
        "price": 79.99,
        "originalPrice": 99.99,
        "stock": 28,
        "rating": 4.4,
        "image": "https://images.unsplash.com/photo-1546435770-a3e426bf472b?auto=format&fit=crop&w=900&q=80",
        "description": "Lightweight wireless headphones for daily commute, study, and casual listening.",
        "features": ["Lightweight frame", "24-hour battery", "Foldable design", "Built-in microphone"],
        "similarProductIds": ["p001", "p003"],
        "cheaperAlternativeIds": [],
    },
    {
        "id": "p003",
        "name": "Pocket ANC Earbuds",
        "category": "Electronics",
        "brand": "PocketSound",
        "price": 59.99,
        "originalPrice": 89.99,
        "stock": 34,
        "rating": 4.3,
        "image": "https://images.unsplash.com/photo-1590658268037-6bf12165a8df?auto=format&fit=crop&w=900&q=80",
        "description": "Compact earbuds with active noise reduction and a pocket charging case.",
        "features": ["ANC earbuds", "Charging case", "Water resistant", "Touch controls"],
        "similarProductIds": ["p001", "p002"],
        "cheaperAlternativeIds": [],
    },
    {
        "id": "p004",
        "name": "UrbanTrail Waterproof Jacket",
        "category": "Fashion",
        "brand": "UrbanTrail",
        "price": 94.5,
        "originalPrice": 139.0,
        "stock": 11,
        "rating": 4.6,
        "image": "https://images.unsplash.com/photo-1543076447-215ad9ba6923?auto=format&fit=crop&w=900&q=80",
        "description": "Breathable rain jacket with sealed seams and compact pack-away pocket.",
        "features": ["Waterproof shell", "Adjustable hood", "Pack-away pocket", "Reflective trim"],
        "similarProductIds": ["p005"],
        "cheaperAlternativeIds": ["p005"],
    },
    {
        "id": "p005",
        "name": "CloudLayer Light Windbreaker",
        "category": "Fashion",
        "brand": "CloudLayer",
        "price": 54.0,
        "originalPrice": 74.0,
        "stock": 23,
        "rating": 4.2,
        "image": "https://images.unsplash.com/photo-1523398002811-999ca8dec234?auto=format&fit=crop&w=900&q=80",
        "description": "A light everyday windbreaker for spring weather and travel packing.",
        "features": ["Lightweight", "Travel friendly", "Adjustable cuffs", "Two zip pockets"],
        "similarProductIds": ["p004"],
        "cheaperAlternativeIds": [],
    },
    {
        "id": "p006",
        "name": "BrewLab Smart Coffee Maker",
        "category": "Home",
        "brand": "BrewLab",
        "price": 149.0,
        "originalPrice": 199.0,
        "stock": 8,
        "rating": 4.8,
        "image": "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?auto=format&fit=crop&w=900&q=80",
        "description": "Programmable coffee maker with brew strength control and thermal carafe.",
        "features": ["App scheduling", "Thermal carafe", "Brew strength control", "Reusable filter"],
        "similarProductIds": ["p007"],
        "cheaperAlternativeIds": ["p007"],
    },
    {
        "id": "p007",
        "name": "MorningCup Compact Brewer",
        "category": "Home",
        "brand": "MorningCup",
        "price": 69.0,
        "originalPrice": 89.0,
        "stock": 19,
        "rating": 4.1,
        "image": "https://images.unsplash.com/photo-1517668808822-9ebb02f2a0e6?auto=format&fit=crop&w=900&q=80",
        "description": "Compact drip brewer for small kitchens, offices, and dorm rooms.",
        "features": ["Compact footprint", "One-touch brewing", "Glass carafe", "Auto shutoff"],
        "similarProductIds": ["p006"],
        "cheaperAlternativeIds": [],
    },
    {
        "id": "p008",
        "name": "FlexDesk Ergonomic Chair",
        "category": "Office",
        "brand": "FlexDesk",
        "price": 219.0,
        "originalPrice": 269.0,
        "stock": 7,
        "rating": 4.5,
        "image": "https://images.unsplash.com/photo-1580480055273-228ff5388ef8?auto=format&fit=crop&w=900&q=80",
        "description": "Adjustable office chair with lumbar support and breathable mesh.",
        "features": ["Lumbar support", "Breathable mesh", "Adjustable arms", "Tilt lock"],
        "similarProductIds": ["p009"],
        "cheaperAlternativeIds": ["p009"],
    },
    {
        "id": "p009",
        "name": "StudyMate Task Chair",
        "category": "Office",
        "brand": "StudyMate",
        "price": 118.0,
        "originalPrice": 149.0,
        "stock": 15,
        "rating": 4.0,
        "image": "https://images.unsplash.com/photo-1505843490701-5be5d7a110bd?auto=format&fit=crop&w=900&q=80",
        "description": "Affordable task chair for study desks and short work sessions.",
        "features": ["Padded seat", "Height adjustment", "Smooth casters", "Compact design"],
        "similarProductIds": ["p008"],
        "cheaperAlternativeIds": [],
    },
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    global _DEMO_DB_RESET_DONE
    with connect_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS carts (
                username TEXT NOT NULL,
                product_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (username, product_id),
                FOREIGN KEY (username) REFERENCES users(username)
            );
            """
        )
        if not _DEMO_DB_RESET_DONE:
            conn.execute("DELETE FROM carts")
            conn.execute("DELETE FROM users")
            _DEMO_DB_RESET_DONE = True


@app.before_request
def before_request():
    init_db()


def product_by_id(product_id: str):
    return next((product for product in PRODUCTS if product["id"] == product_id), None)


def product_section_payload(product: dict, section: str):
    brand = product["brand"]
    category = product["category"]
    origin_city = {
        "Electronics": "Shenzhen fulfillment center",
        "Fashion": "Auckland regional warehouse",
        "Home": "Melbourne home-goods hub",
        "Office": "Sydney commercial depot",
    }.get(category, "Auckland regional warehouse")
    merchant_name = f"{brand} Official Store"
    if section == "info":
        return {
            "productId": product["id"],
            "title": f"{product['name']} product information",
            "specifications": [
                {"label": "Brand", "value": brand},
                {"label": "Category", "value": category},
                {"label": "Model", "value": f"{brand[:3].upper()}-{product['id'].upper()}"},
                {"label": "Stock status", "value": f"{product['stock']} units available"},
                {"label": "Catalog rating", "value": f"{product['rating']:.1f}/5"},
            ],
            "packageContents": [
                product["name"],
                "Quick start guide",
                "Warranty card",
                "Protective shipping packaging",
            ],
            "bestFor": [
                f"Customers comparing {category.lower()} options",
                "Shoppers who want clear feature trade-offs before checkout",
                "Gift buyers checking specifications before purchase",
            ],
            "careNotes": [
                "Inspect packaging before opening.",
                "Keep the order confirmation for warranty support.",
                "Product images are representative of the demo catalog.",
            ],
        }
    if section == "shipping":
        return {
            "productId": product["id"],
            "title": f"Shipping options for {product['name']}",
            "shipsFrom": origin_city,
            "freeShippingThreshold": 150,
            "standard": {"name": "Standard tracked delivery", "eta": "3-5 business days", "cost": 12.99},
            "express": {"name": "Express courier", "eta": "1-2 business days", "cost": 24.99},
            "handlingTime": "Orders placed before 2pm usually leave the warehouse the same business day.",
            "limitations": [
                "Remote delivery addresses may require one extra business day.",
                "Large office and home items may ship in reinforced cartons.",
                "Shipping fees are calculated from the cart subtotal at checkout.",
            ],
        }
    if section == "merchant":
        return {
            "productId": product["id"],
            "merchantName": merchant_name,
            "verified": True,
            "merchantRating": round(min(4.9, product["rating"] + 0.1), 1),
            "responseTime": "Usually replies within 4 business hours",
            "dispatchReliability": "97% of demo orders dispatched on time",
            "sellerSince": "2021",
            "servicePromises": [
                "Tracked delivery on every order",
                "Clear warranty handling through MockMart support",
                "No real payment is processed in this course demo",
            ],
        }
    if section == "reviews":
        return {
            "productId": product["id"],
            "averageRating": product["rating"],
            "totalReviews": 186 + int(product["id"].replace("p", "")) * 17,
            "ratingBreakdown": {"5": 68, "4": 21, "3": 7, "2": 3, "1": 1},
            "highlights": [
                "Customers often mention strong value for the listed price.",
                "Most negative notes are about delivery timing or fit expectations.",
                "Several reviews compare this item with cheaper alternatives.",
            ],
            "reviews": [
                {
                    "author": "Maya R.",
                    "rating": 5,
                    "title": "Matched the description",
                    "body": f"The {product['name']} arrived as described and the feature list was accurate.",
                },
                {
                    "author": "Daniel K.",
                    "rating": 4,
                    "title": "Good value after comparing options",
                    "body": "I checked similar products first, then came back because the rating felt more reliable.",
                },
                {
                    "author": "Priya S.",
                    "rating": 4,
                    "title": "Shipping details mattered",
                    "body": "The shipping estimate helped me decide whether to continue to checkout.",
                },
            ],
        }
    return {
        "productId": product["id"],
        "title": f"Warranty and support for {product['name']}",
        "returnWindow": "30 days from delivery in the demo policy",
        "warrantyPeriod": "12 months limited manufacturer-style warranty",
        "supportFlow": [
            "Open an order support request from the account page.",
            "Provide the order number and a short issue description.",
            "MockMart support reviews replacement, return, or troubleshooting options.",
        ],
        "exceptions": [
            "Cosmetic wear from normal use is not covered.",
            "Missing original accessories may delay return processing.",
            "Final refund rules are simulated for coursework only.",
        ],
    }


def cart_payload(username: str):
    with connect_db() as conn:
        rows = conn.execute(
            "SELECT product_id, quantity FROM carts WHERE username = ? ORDER BY updated_at DESC",
            (username,),
        ).fetchall()
    items = []
    for row in rows:
        product = product_by_id(row["product_id"])
        if not product:
            continue
        quantity = int(row["quantity"])
        line_total = round(product["price"] * quantity, 2)
        items.append({"product": product, "quantity": quantity, "lineTotal": line_total})

    subtotal = round(sum(item["lineTotal"] for item in items), 2)
    shipping = 0 if subtotal == 0 or subtotal >= 150 else 12.99
    total = round(subtotal + shipping, 2)
    return {"items": items, "subtotal": subtotal, "shipping": shipping, "total": total}


def agi_cart_summary(cart: dict):
    item_count = sum(int(item["quantity"]) for item in cart.get("items", []))
    product_ids = [item["product"]["id"] for item in cart.get("items", [])]
    return {
        "itemCount": item_count,
        "subtotal": cart.get("subtotal", 0),
        "shippingFee": cart.get("shipping", 0),
        "couponApplied": False,
        "checkoutStep": "",
        "items": cart.get("items", []),
        "cartProductIds": product_ids,
    }


def username_from_request():
    return request.headers.get("X-Demo-User", "").strip()


def get_user(username: str):
    if not username:
        return None
    with connect_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None


def require_user():
    username = username_from_request()
    user = get_user(username)
    if not user:
        return None, (jsonify({"message": "Please log in before using the cart."}), 401)
    return user, None


def log_action_json(actions):
    if not DEMO_VERBOSE_LOGS or not actions:
        return
    print("\n================ AGI ACTION JSON ================", flush=True)
    print(json.dumps(actions, ensure_ascii=False, indent=2), flush=True)
    print("=================================================\n", flush=True)


def related_products_for_cart(cart_product_ids):
    related_ids = []
    for product_id in cart_product_ids or []:
        product = product_by_id(product_id)
        if not product:
            continue
        related_ids.extend(product.get("similarProductIds") or [])
        related_ids.extend(product.get("cheaperAlternativeIds") or [])
    seen = set(cart_product_ids or [])
    related = []
    for product_id in related_ids:
        if product_id in seen:
            continue
        product = product_by_id(product_id)
        if not product:
            continue
        related.append(
            {
                "id": product["id"],
                "name": product["name"],
                "price": product["price"],
                "originalPrice": product["originalPrice"],
                "rating": product["rating"],
                "image": product["image"],
            }
        )
        seen.add(product_id)
    return related[:3]


def safe_web_action(raw_action, *, source, session_id, decision_id=None, cart_product_ids=None):
    raw_action = raw_action or {}
    action_type = raw_action.get("action_type") or raw_action.get("actionType") or "banner"
    tool_name = raw_action.get("tool_name") or raw_action.get("toolName") or action_type
    message = raw_action.get("message") or "Recommended shopping assistance is available."
    priority = raw_action.get("priority") or "medium"
    target_page = raw_action.get("target_page") or raw_action.get("targetPage") or "any"
    action_id = raw_action.get("action_id") or raw_action.get("actionId") or f"web-{uuid.uuid4()}"

    if tool_name == "do_nothing" or action_type == "none":
        return None
    if action_type in {"discount_email", "discount_or_cheaper_recommendation", "price_reassurance"}:
        tool_name = "offer_small_discount"
        action_type = "cart_incentive"
    if action_type in {"customer_service_contact", "checkout_help"}:
        tool_name = "highlight_support"
        action_type = "support_highlight"
    if action_type in {"product_comparison_help"}:
        tool_name = "show_related_recommendations"
        action_type = "recommendation_strip"
    if action_type in {"free_shipping_offer", "shipping_clarity_message"}:
        tool_name = "show_shipping_info"
        action_type = "banner"
    if action_type == "return_policy_message":
        tool_name = "show_return_policy"
        action_type = "banner"
    if action_type in {"review_summary", "product_review_or_specs_help", "confidence_summary"}:
        tool_name = "show_product_reviews"
        action_type = "banner"
    if action_type == "trust_message":
        tool_name = "show_trust_message"
        action_type = "banner"

    allowed_tools = {
        "show_shipping_info",
        "show_return_policy",
        "show_product_reviews",
        "show_product_comparison",
        "show_coupon",
        "offer_small_discount",
        "highlight_support",
        "show_related_recommendations",
        "show_trust_message",
    }
    if tool_name not in allowed_tools:
        return None

    action = {
        "action_id": action_id,
        "decision_id": decision_id,
        "session_id": session_id,
        "source": source,
        "action_type": action_type,
        "tool_name": tool_name,
        "message": message,
        "target_page": target_page,
        "priority": priority,
    }
    if tool_name == "offer_small_discount":
        multiplier = float(raw_action.get("discountMultiplier") or raw_action.get("discount_multiplier") or 0.95)
        if multiplier < 0.95:
            return None
        action.update({"discountMultiplier": multiplier, "demoIncentive": True})
    if tool_name == "highlight_support":
        action.update({"externalContact": False})
    if tool_name == "show_related_recommendations":
        action.update({"products": related_products_for_cart(cart_product_ids or [])})
    return action


def build_web_actions(agi_response, cart_product_ids):
    session_id = agi_response.get("sessionId")
    decision = agi_response.get("agiDecision") or {}
    decision_id = decision.get("decision_id")
    candidates = []
    decision_payload = ((decision.get("action") or {}).get("payload") or {})
    candidates.append(
        safe_web_action(
            decision_payload,
            source="agi_decision",
            session_id=session_id,
            decision_id=decision_id,
            cart_product_ids=cart_product_ids,
        )
    )
    for action in ((agi_response.get("analysis") or {}).get("actions") or []):
        candidates.append(
            safe_web_action(
                action,
                source="risk_analysis",
                session_id=session_id,
                decision_id=decision_id,
                cart_product_ids=cart_product_ids,
            )
        )
    deduped = {}
    for action in [item for item in candidates if item]:
        key = (action["tool_name"], action.get("target_page"), action.get("message"))
        deduped.setdefault(key, action)
    return list(deduped.values())[:3]


def forward_json_to_agi(path, payload=None, method="GET"):
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urlrequest.Request(
        f"{AGI_BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urlrequest.urlopen(req, timeout=3) as response:
        body = response.read().decode("utf-8")
        return json.loads(body) if body else {}


def forward_event_to_agi(payload):
    return forward_json_to_agi("/api/events", payload, "POST")


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "online_shopping_web"})


@app.post("/api/register")
def register():
    payload = request.get_json(silent=True) or {}
    username = payload.get("username", "").strip()
    password = payload.get("password", "")
    name = payload.get("name", "").strip() or username
    if len(username) < 3:
        return jsonify({"message": "Username must be at least 3 characters."}), 400
    if len(password) < 6:
        return jsonify({"message": "Password must be at least 6 characters."}), 400
    with connect_db() as conn:
        existing = conn.execute("SELECT username FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            return jsonify({"message": "Username is already registered."}), 409
        conn.execute(
            """
            INSERT INTO users (username, password_hash, name, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (username, generate_password_hash(password), name, now_iso()),
        )
    return jsonify({"user": {"id": username, "username": username, "name": name}}), 201


@app.post("/api/login")
def login():
    payload = request.get_json(silent=True) or {}
    username = payload.get("username", "")
    password = payload.get("password", "")
    user = get_user(username)
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"message": "Invalid username or password"}), 401
    return jsonify({"user": {"id": username, "username": username, "name": user["name"]}})


@app.get("/api/me")
def me():
    user, error_response = require_user()
    if error_response:
        return error_response
    return jsonify({"user": {"id": user["username"], "username": user["username"], "name": user["name"]}})


@app.get("/api/products")
def list_products():
    search = request.args.get("search", "").strip().lower()
    category = request.args.get("category", "").strip()
    sort = request.args.get("sort", "featured")

    products = PRODUCTS[:]
    if search:
        products = [
            product
            for product in products
            if search in product["name"].lower()
            or search in product["brand"].lower()
            or search in product["description"].lower()
        ]
    if category and category != "All":
        products = [product for product in products if product["category"] == category]

    if sort == "price_asc":
        products.sort(key=lambda product: product["price"])
    elif sort == "price_desc":
        products.sort(key=lambda product: product["price"], reverse=True)
    elif sort == "rating":
        products.sort(key=lambda product: product["rating"], reverse=True)

    return jsonify({"products": products})


@app.get("/api/products/<product_id>")
def get_product(product_id: str):
    product = product_by_id(product_id)
    if not product:
        return jsonify({"message": "Product not found"}), 404
    similar = [product_by_id(pid) for pid in product["similarProductIds"]]
    cheaper = [product_by_id(pid) for pid in product["cheaperAlternativeIds"]]
    return jsonify(
        {
            "product": product,
            "similarProducts": [item for item in similar if item],
            "cheaperAlternatives": [item for item in cheaper if item],
        }
    )


@app.get("/api/products/<product_id>/<section>")
def get_product_section(product_id: str, section: str):
    if section not in {"info", "shipping", "merchant", "reviews", "warranty"}:
        return jsonify({"message": "Product section not found"}), 404
    product = product_by_id(product_id)
    if not product:
        return jsonify({"message": "Product not found"}), 404
    return jsonify({section: product_section_payload(product, section), "product": product})


@app.get("/api/categories")
def categories():
    return jsonify({"categories": sorted({product["category"] for product in PRODUCTS})})


@app.get("/api/cart")
def get_cart():
    user, error_response = require_user()
    if error_response:
        return error_response
    return jsonify(cart_payload(user["username"]))


@app.post("/api/cart/add")
def add_to_cart():
    user, error_response = require_user()
    if error_response:
        return error_response
    payload = request.get_json(silent=True) or {}
    product_id = payload.get("productId")
    quantity = max(int(payload.get("quantity", 1)), 1)
    product = product_by_id(product_id)
    if not product:
        return jsonify({"message": "Product not found"}), 404
    username = user["username"]
    with connect_db() as conn:
        row = conn.execute(
            "SELECT quantity FROM carts WHERE username = ? AND product_id = ?",
            (username, product_id),
        ).fetchone()
        next_quantity = min((int(row["quantity"]) if row else 0) + quantity, product["stock"])
        conn.execute(
            """
            INSERT INTO carts (username, product_id, quantity, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(username, product_id)
            DO UPDATE SET quantity = excluded.quantity, updated_at = excluded.updated_at
            """,
            (username, product_id, next_quantity, now_iso()),
        )
    return jsonify(cart_payload(username))


@app.post("/api/cart/update")
def update_cart():
    user, error_response = require_user()
    if error_response:
        return error_response
    payload = request.get_json(silent=True) or {}
    product_id = payload.get("productId")
    quantity = int(payload.get("quantity", 1))
    product = product_by_id(product_id)
    if not product:
        return jsonify({"message": "Product not found"}), 404
    username = user["username"]
    with connect_db() as conn:
        if quantity <= 0:
            conn.execute("DELETE FROM carts WHERE username = ? AND product_id = ?", (username, product_id))
        else:
            conn.execute(
                """
                INSERT INTO carts (username, product_id, quantity, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(username, product_id)
                DO UPDATE SET quantity = excluded.quantity, updated_at = excluded.updated_at
                """,
                (username, product_id, min(quantity, product["stock"]), now_iso()),
            )
    return jsonify(cart_payload(username))


@app.post("/api/cart/remove")
def remove_from_cart():
    user, error_response = require_user()
    if error_response:
        return error_response
    payload = request.get_json(silent=True) or {}
    username = user["username"]
    with connect_db() as conn:
        conn.execute(
            "DELETE FROM carts WHERE username = ? AND product_id = ?",
            (username, payload.get("productId")),
        )
    return jsonify(cart_payload(username))


@app.post("/api/cart/clear")
def clear_cart():
    user, error_response = require_user()
    if error_response:
        return error_response
    username = user["username"]
    with connect_db() as conn:
        conn.execute("DELETE FROM carts WHERE username = ?", (username,))
    return jsonify(cart_payload(username))


@app.post("/api/checkout/start")
def checkout_start():
    user, error_response = require_user()
    if error_response:
        return error_response
    return jsonify({"checkoutId": "demo-checkout-001", "cart": cart_payload(user["username"])})


@app.post("/api/checkout/complete")
def checkout_complete():
    user, error_response = require_user()
    if error_response:
        return error_response
    username = user["username"]
    payload = request.get_json(silent=True) or {}
    requested_product_ids = payload.get("productIds") or []
    current_cart = cart_payload(username)
    current_product_ids = [item["product"]["id"] for item in current_cart["items"]]
    completed_product_ids = [
        product_id for product_id in requested_product_ids if product_id in current_product_ids
    ] or current_product_ids
    order_items = [item for item in current_cart["items"] if item["product"]["id"] in completed_product_ids]
    order_subtotal = round(sum(item["lineTotal"] for item in order_items), 2)
    order_shipping = 0 if order_subtotal == 0 or order_subtotal >= 150 else 12.99
    order = {
        "items": order_items,
        "subtotal": order_subtotal,
        "shipping": order_shipping,
        "total": round(order_subtotal + order_shipping, 2),
    }
    with connect_db() as conn:
        for product_id in completed_product_ids:
            conn.execute(
                "DELETE FROM carts WHERE username = ? AND product_id = ?",
                (username, product_id),
            )
    remaining_cart = cart_payload(username)
    return jsonify(
        {
            "orderId": "ORD-DEMO-1001",
            "completedProductIds": completed_product_ids,
            "order": order,
            "remainingCart": remaining_cart,
            "cartCleared": len(remaining_cart["items"]) == 0,
        }
    )


@app.post("/api/agi/events")
def proxy_agi_event():
    payload = request.get_json(silent=True) or {}
    event_type = ((payload.get("event") or {}).get("type")) or ""
    user = payload.get("user") or {}
    username = user.get("userId") or username_from_request()
    if event_type in {"logout", "session_end"}:
        try:
            agi_response = forward_event_to_agi(payload)
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return jsonify({
                "accepted": False,
                "reason": "agi_unavailable",
                "detail": str(exc),
                "webActions": [],
                "actionRuntimeStatus": "agi_unavailable",
            }), 202
        return jsonify(agi_response)

    if not username or not get_user(username):
        return jsonify({"accepted": False, "reason": "login_required_for_agi_scoring"}), 202

    cart = cart_payload(username)
    cart_summary = agi_cart_summary(cart)
    event_body = payload.get("event") or {}
    event_metadata = event_body.get("metadata") or {}
    if event_type == "order_complete":
        order_cart = payload.get("cart") or {}
        completed_product_ids = event_metadata.get("completedProductIds") or []
        if not completed_product_ids and order_cart.get("items"):
            completed_product_ids = [item["product"]["id"] for item in order_cart.get("items", [])]
        payload["cart"] = {
            **order_cart,
            "cartProductIds": completed_product_ids,
            "completedProductIds": completed_product_ids,
            "remainingCartProductIds": event_metadata.get("remainingCartProductIds") or cart_summary["cartProductIds"],
        }
    elif cart_summary["itemCount"] <= 0:
        return jsonify({"accepted": False, "reason": "cart_required_for_agi_scoring"}), 202
    else:
        payload["cart"] = cart_summary

    payload["user"] = {**user, "userId": username, "isLoggedIn": True}
    scoped_product_ids = (payload.get("cart") or {}).get("cartProductIds") or cart_summary["cartProductIds"]
    payload["event"] = {
        **event_body,
        "metadata": {
            **event_metadata,
            "cartProductIds": scoped_product_ids,
            "cartScoped": True,
            "scoringScope": "current_user_cart",
        },
    }
    try:
        agi_response = forward_event_to_agi(payload)
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return jsonify({
            "accepted": False,
            "reason": "agi_unavailable",
            "detail": str(exc),
            "webActions": [],
            "actionRuntimeStatus": "agi_unavailable",
        }), 202

    actions = ((agi_response.get("analysis") or {}).get("actions")) or []
    log_action_json(actions)
    web_actions = build_web_actions(agi_response, scoped_product_ids)
    risk_score = ((agi_response.get("analysis") or {}).get("score"))
    agi_response["webActions"] = web_actions
    agi_response["riskScore"] = risk_score
    agi_response["actionRuntimeContext"] = {"score": risk_score}
    agi_response["actionRuntimeStatus"] = "ready" if web_actions else "no_action"
    return jsonify(agi_response)


@app.get("/api/agi/state/<session_id>")
def proxy_agi_state(session_id):
    try:
        return jsonify(forward_json_to_agi(f"/agi/state/{session_id}"))
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return jsonify({"available": False, "reason": "agi_unavailable", "detail": str(exc)}), 202


@app.get("/api/agi/decision/<session_id>")
def proxy_agi_decision(session_id):
    try:
        return jsonify(forward_json_to_agi(f"/agi/decision/{session_id}"))
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return jsonify({"available": False, "reason": "agi_unavailable", "detail": str(exc)}), 202


@app.get("/api/agi/evaluation")
def proxy_agi_evaluation():
    try:
        return jsonify(forward_json_to_agi("/agi/evaluation"))
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return jsonify({"available": False, "reason": "agi_unavailable", "detail": str(exc)}), 202


@app.get("/api/agi/evolution")
def proxy_agi_evolution():
    try:
        return jsonify(forward_json_to_agi("/agi/evolution"))
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return jsonify({"available": False, "reason": "agi_unavailable", "detail": str(exc)}), 202


@app.post("/api/agi/feedback")
def proxy_agi_feedback():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(forward_json_to_agi("/agi/feedback", payload, "POST"))
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return jsonify({"accepted": False, "reason": "agi_unavailable", "detail": str(exc)}), 202


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
