from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS

from config_loader import load_llm_config

load_llm_config()

from agent_engine import AGIAgent
from risk_engine import analyze_event
from risk_llm_scorer import RiskLLMScorer


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "agi_data.sqlite"
SESSION_TTL_SECONDS = 10 * 60
DEMO_VERBOSE_LOGS = os.getenv("AGI_VERBOSE_LOGS", "").strip().lower() in {"1", "true", "yes"}

app = Flask(__name__)
CORS(app)
_agent = None
_late_llm_scorer = None


def get_agent():
    global _agent
    if _agent is None:
        _agent = AGIAgent(DB_PATH)
    return _agent


def get_late_llm_scorer():
    global _late_llm_scorer
    if _late_llm_scorer is None:
        _late_llm_scorer = RiskLLMScorer()
    return _late_llm_scorer


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                site_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                started_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                ended_at TEXT,
                latest_url TEXT,
                latest_page_type TEXT,
                current_score INTEGER NOT NULL DEFAULT 100,
                current_state TEXT NOT NULL DEFAULT 'browsing_uncertain',
                risk_started INTEGER NOT NULL DEFAULT 0,
                device_id TEXT,
                cart_snapshot_json TEXT
            );

            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                page_type TEXT,
                url TEXT,
                product_json TEXT,
                cart_json TEXT,
                client_signals_json TEXT,
                raw_payload_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS score_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                score INTEGER NOT NULL,
                state TEXT NOT NULL,
                reason TEXT NOT NULL,
                event_id TEXT,
                score_delta INTEGER NOT NULL DEFAULT 0,
                base_score_delta INTEGER NOT NULL DEFAULT 0,
                risk_multiplier REAL NOT NULL DEFAULT 1.0,
                risk_multiplier_source TEXT,
                llm_request_id TEXT
            );

            CREATE TABLE IF NOT EXISTS llm_score_requests (
                request_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                event_id TEXT,
                score_history_id INTEGER,
                cart_scope_key TEXT,
                status TEXT NOT NULL,
                current_score INTEGER NOT NULL,
                max_delta INTEGER NOT NULL,
                default_multiplier REAL NOT NULL,
                default_score_delta INTEGER NOT NULL,
                llm_multiplier REAL,
                llm_score_delta INTEGER,
                reason_code TEXT,
                context_json TEXT NOT NULL,
                result_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS actions (
                action_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                action_type TEXT NOT NULL,
                state TEXT NOT NULL,
                reason TEXT NOT NULL,
                message TEXT NOT NULL,
                source_event_id TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                page TEXT,
                product_id TEXT,
                metadata_json TEXT,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS world_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                world_state_json TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS belief_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                belief_state_json TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                memory_type TEXT NOT NULL,
                content_json TEXT NOT NULL,
                importance REAL NOT NULL DEFAULT 0,
                reward REAL NOT NULL DEFAULT 0,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                world_state_json TEXT NOT NULL,
                belief_state_json TEXT NOT NULL,
                reasoning_json TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                selected_tool TEXT,
                action_payload_json TEXT,
                confidence REAL NOT NULL DEFAULT 0,
                safety_status TEXT NOT NULL,
                llm_provider TEXT,
                llm_model TEXT,
                llm_status TEXT,
                llm_latency_ms INTEGER NOT NULL DEFAULT 0,
                llm_reasoning_json TEXT,
                llm_input_summary_json TEXT,
                llm_output_json TEXT,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                decision_id INTEGER,
                feedback_event_json TEXT NOT NULL,
                reward REAL NOT NULL DEFAULT 0,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS action_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                decision_id INTEGER,
                action_id TEXT,
                tool_name TEXT,
                action_type TEXT,
                feedback_type TEXT NOT NULL,
                render_status TEXT,
                device_id TEXT,
                metadata_json TEXT,
                reward REAL NOT NULL DEFAULT 0,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS error_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                severity TEXT NOT NULL,
                source TEXT NOT NULL,
                session_id TEXT,
                device_id TEXT,
                error_type TEXT NOT NULL,
                message TEXT NOT NULL,
                metadata_json TEXT
            );

            CREATE TABLE IF NOT EXISTS agent_evolution (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                update_type TEXT NOT NULL,
                before_json TEXT,
                after_json TEXT,
                reason TEXT,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tool_policy (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                blocker_type TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                score REAL NOT NULL DEFAULT 0.5,
                usage_count INTEGER NOT NULL DEFAULT 0,
                average_reward REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                UNIQUE(blocker_type, tool_name)
            );

            CREATE TABLE IF NOT EXISTS world_model_weights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_name TEXT NOT NULL,
                blocker_type TEXT NOT NULL,
                weight REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                UNIQUE(signal_name, blocker_type)
            );
            """
        )
        ensure_schema(conn)
        purge_legacy_test_user(conn)
        seed_defaults(conn)


def ensure_schema(conn):
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
    }
    if "risk_started" not in columns:
        conn.execute("ALTER TABLE sessions ADD COLUMN risk_started INTEGER NOT NULL DEFAULT 0")
    if "device_id" not in columns:
        conn.execute("ALTER TABLE sessions ADD COLUMN device_id TEXT")

    score_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(score_history)").fetchall()
    }
    score_history_additions = {
        "event_id": "TEXT",
        "score_delta": "INTEGER NOT NULL DEFAULT 0",
        "base_score_delta": "INTEGER NOT NULL DEFAULT 0",
        "risk_multiplier": "REAL NOT NULL DEFAULT 1.0",
        "risk_multiplier_source": "TEXT",
        "llm_request_id": "TEXT",
    }
    for column, definition in score_history_additions.items():
        if column not in score_columns:
            conn.execute(f"ALTER TABLE score_history ADD COLUMN {column} {definition}")


def purge_legacy_test_user(conn):
    rows = conn.execute(
        "SELECT session_id FROM sessions WHERE user_id = 'test123'"
    ).fetchall()
    session_ids = [row["session_id"] for row in rows]
    if not session_ids:
        return
    for session_id in session_ids:
        for table in (
            "action_feedback",
            "error_logs",
            "llm_score_requests",
            "agent_feedback",
            "agent_decisions",
            "agent_memory",
            "belief_states",
            "world_states",
            "user_events",
            "actions",
            "score_history",
            "events",
        ):
            conn.execute(f"DELETE FROM {table} WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))


def seed_defaults(conn):
    timestamp = now_iso()
    tool_defaults = [
        ("shipping_concern", "show_shipping_info", 0.7),
        ("product_uncertainty", "show_product_reviews", 0.65),
        ("comparison_hesitation", "show_product_comparison", 0.62),
        ("price_concern", "show_coupon", 0.55),
        ("trust_concern", "show_trust_message", 0.58),
        ("checkout_friction", "show_trust_message", 0.56),
        ("none", "do_nothing", 0.4),
    ]
    for blocker, tool, score in tool_defaults:
        conn.execute(
            """
            INSERT OR IGNORE INTO tool_policy
                (blocker_type, tool_name, score, usage_count, average_reward, updated_at)
            VALUES (?, ?, ?, 0, 0, ?)
            """,
            (blocker, tool, score, timestamp),
        )

    weight_defaults = [
        ("shipping_fee_visible", "shipping_concern", 0.45),
        ("checkout", "checkout_friction", 0.18),
        ("checkout", "shipping_concern", 0.12),
        ("cart", "price_concern", 0.12),
        ("coupon_attempt", "price_concern", 0.45),
        ("comparison", "comparison_hesitation", 0.34),
        ("comparison", "product_uncertainty", 0.18),
        ("comparison", "price_concern", 0.16),
        ("checkout_exit", "checkout_friction", 0.45),
        ("checkout_exit", "shipping_concern", 0.18),
        ("product_uncertainty_signal", "product_uncertainty", 0.16),
    ]
    for signal, blocker, weight in weight_defaults:
        conn.execute(
            """
            INSERT OR IGNORE INTO world_model_weights
                (signal_name, blocker_type, weight, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (signal, blocker, weight, timestamp),
        )


def row_to_dict(row):
    return dict(row) if row else None


def decode_json(value, fallback=None):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def has_scoring_cart(payload):
    cart = payload.get("cart") or {}
    try:
        item_count = int(cart.get("itemCount") or 0)
    except (TypeError, ValueError):
        item_count = 0
    items = cart.get("items") or []
    product_ids = cart.get("cartProductIds") or []
    return item_count > 0 or bool(items) or bool(product_ids)


def session_exists(session_id):
    if not session_id:
        return False
    with connect_db() as conn:
        row = conn.execute("SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    return bool(row)


def log_incoming_event(payload):
    if not DEMO_VERBOSE_LOGS:
        return
    user = payload.get("user") or {}
    event = payload.get("event") or {}
    print("\n================ AGI EVENT RECEIVED ================", flush=True)
    print(f"time: {now_iso()}", flush=True)
    print(f"event: {event.get('type', 'unknown')}", flush=True)
    print(f"user: {user.get('userId', 'unknown')}", flush=True)
    print(f"session: {user.get('sessionId', 'unknown')}\n", flush=True)


def payload_device_id(payload):
    return (
        ((payload.get("user") or {}).get("deviceId"))
        or ((payload.get("clientSignals") or {}).get("deviceId"))
        or ((payload.get("event") or {}).get("metadata") or {}).get("deviceId")
        or ""
    )


def cart_scope_key_from_cart(cart):
    product_ids = set(cart.get("cartProductIds") or [])
    for item in cart.get("items") or []:
        product = item.get("product") or {}
        if product.get("id"):
            product_ids.add(product["id"])
    return "|".join(sorted(product_ids))


def cart_scope_key_from_session(session):
    if not session:
        return ""
    cart_snapshot = session["cart_snapshot_json"] if isinstance(session, sqlite3.Row) else session.get("cart_snapshot_json")
    cart = decode_json(cart_snapshot, {})
    return cart_scope_key_from_cart(cart or {})


def log_error_event(
    error_type,
    message,
    *,
    severity="warning",
    source="agi_backend",
    session_id=None,
    device_id=None,
    metadata=None,
):
    with connect_db() as conn:
        conn.execute(
            """
            INSERT INTO error_logs (
                timestamp, severity, source, session_id, device_id,
                error_type, message, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_iso(),
                severity,
                source,
                session_id,
                device_id,
                error_type,
                message,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )


def cleanup_inactive_sessions():
    cutoff = time.time() - SESSION_TTL_SECONDS
    ended_at = now_iso()
    with connect_db() as conn:
        rows = conn.execute(
            "SELECT session_id, last_seen_at FROM sessions WHERE status = 'active'"
        ).fetchall()
        for row in rows:
            try:
                last_seen = datetime.fromisoformat(row["last_seen_at"]).timestamp()
            except ValueError:
                last_seen = time.time()
            if last_seen < cutoff:
                conn.execute(
                    "UPDATE sessions SET status = 'ended', ended_at = ? WHERE session_id = ?",
                    (ended_at, row["session_id"]),
                )


@app.before_request
def before_request():
    init_db()
    cleanup_inactive_sessions()


def mark_session_ended(session_id):
    ended_at = now_iso()
    with connect_db() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET status = 'ended', ended_at = ?, last_seen_at = ?
            WHERE session_id = ?
            """,
            (ended_at, ended_at, session_id),
        )


def complete_scoring_session(session_id):
    ended_at = now_iso()
    with connect_db() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET status = 'ended', ended_at = ?, last_seen_at = ?, current_score = 100,
                current_state = 'converted', risk_started = 0
            WHERE session_id = ?
            """,
            (ended_at, ended_at, session_id),
        )


def reset_scoring_session(session_id, reason="cart_scope_reset"):
    updated_at = now_iso()
    with connect_db() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET status = 'active', ended_at = NULL, last_seen_at = ?, current_score = 100,
                current_state = ?, risk_started = 0
            WHERE session_id = ?
            """,
            (updated_at, reason, session_id),
        )


def get_recent_events(session_id, limit=20):
    with connect_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM events
            WHERE session_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    events = []
    for row in rows:
        item = row_to_dict(row)
        item["raw_payload"] = decode_json(item.pop("raw_payload_json"), {})
        item["product"] = decode_json(item.pop("product_json"), None)
        item["cart"] = decode_json(item.pop("cart_json"), None)
        item["client_signals"] = decode_json(item.pop("client_signals_json"), None)
        events.append(item)
    return events


def existing_action_types(session_id):
    with connect_db() as conn:
        rows = conn.execute(
            "SELECT action_type, state FROM actions WHERE session_id = ?",
            (session_id,),
        ).fetchall()
    return {(row["action_type"], row["state"]) for row in rows}


def persist_actions(session, event_id, state, reasons, recommended_actions):
    existing = existing_action_types(session["session_id"])
    reason = "; ".join(reasons)
    created = []
    with connect_db() as conn:
        for action in recommended_actions:
            action_type = action.get("action_type", "retention_message")
            key = (action_type, state)
            if key in existing:
                continue
            action_id = str(uuid.uuid4())
            message = action.get("message", "Recommended AGI intervention.")
            conn.execute(
                """
                INSERT INTO actions (
                    action_id, session_id, user_id, timestamp, action_type,
                    state, reason, message, source_event_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action_id,
                    session["session_id"],
                    session["user_id"],
                    now_iso(),
                    action_type,
                    state,
                    reason,
                    message,
                    event_id,
                ),
            )
            created.append(
                {
                    "action_id": action_id,
                    "action_type": action_type,
                    "state": state,
                    "reason": reason,
                    "message": message,
                }
            )
    return created


def save_action_feedback_record(feedback_record):
    event = feedback_record.get("event") or {}
    if not (event.get("action_id") or event.get("tool_name") or event.get("action_type")):
        return
    with connect_db() as conn:
        conn.execute(
            """
            INSERT INTO action_feedback (
                session_id, decision_id, action_id, tool_name, action_type,
                feedback_type, render_status, device_id, metadata_json, reward, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feedback_record.get("session_id"),
                feedback_record.get("decision_id"),
                event.get("action_id") or event.get("actionId"),
                event.get("tool_name") or event.get("toolName"),
                event.get("action_type") or event.get("actionType"),
                event.get("feedback_type") or event.get("type") or "unknown",
                event.get("render_status") or event.get("renderStatus"),
                event.get("device_id") or event.get("deviceId"),
                json.dumps(event.get("metadata") or {}, ensure_ascii=False),
                float(feedback_record.get("reward") or 0),
                feedback_record.get("timestamp") or now_iso(),
            ),
        )


def upsert_session(payload):
    user = payload.get("user") or {}
    source = payload.get("source") or {}
    event = payload.get("event") or {}
    session_id = user.get("sessionId")
    user_id = user.get("userId")
    is_logged_in = bool(user.get("isLoggedIn"))

    if not session_id or not user_id or not is_logged_in or user_id == "anonymous":
        return None

    event_type = event.get("type", "")
    timestamp = payload.get("timestamp") or now_iso()
    latest_url = source.get("url", "")
    page_type = source.get("pageType", "")
    cart_json = json.dumps(payload.get("cart"), ensure_ascii=False)
    device_id = payload_device_id(payload)

    with connect_db() as conn:
        existing = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if not existing:
            conn.execute(
                """
                INSERT INTO sessions (
                    session_id, user_id, site_id, status, started_at, last_seen_at,
                    ended_at, latest_url, latest_page_type, current_score,
                    current_state, risk_started, device_id, cart_snapshot_json
                ) VALUES (?, ?, ?, 'active', ?, ?, NULL, ?, ?, 100, 'browsing_uncertain', 0, ?, ?)
                """,
                (
                    session_id,
                    user_id,
                    source.get("siteId", "unknown"),
                    timestamp,
                    timestamp,
                    latest_url,
                    page_type,
                    device_id,
                    cart_json,
                ),
            )
        elif event_type == "session_start":
            conn.execute(
                """
                UPDATE sessions
                SET status = 'active', ended_at = NULL, last_seen_at = ?,
                    latest_url = ?, latest_page_type = ?, cart_snapshot_json = ?,
                    current_score = 100, current_state = 'browsing_uncertain',
                    risk_started = 0, device_id = ?
                WHERE session_id = ?
                """,
                (timestamp, latest_url, page_type, cart_json, device_id, session_id),
            )
        elif existing["status"] == "active" or event_type in {"session_end", "logout"}:
            conn.execute(
                """
                UPDATE sessions
                SET last_seen_at = ?, latest_url = ?, latest_page_type = ?,
                    cart_snapshot_json = ?, device_id = COALESCE(NULLIF(?, ''), device_id)
                WHERE session_id = ?
                """,
                (timestamp, latest_url, page_type, cart_json, device_id, session_id),
            )

    with connect_db() as conn:
        return row_to_dict(
            conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        )


def persist_event(payload):
    user = payload.get("user") or {}
    source = payload.get("source") or {}
    event = payload.get("event") or {}
    event_id = payload.get("eventId") or str(uuid.uuid4())
    timestamp = payload.get("timestamp") or now_iso()
    with connect_db() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO events (
                event_id, session_id, user_id, event_type, timestamp, page_type, url,
                product_json, cart_json, client_signals_json, raw_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                user.get("sessionId"),
                user.get("userId"),
                event.get("type", "unknown"),
                timestamp,
                source.get("pageType", ""),
                source.get("url", ""),
                json.dumps(payload.get("product"), ensure_ascii=False),
                json.dumps(payload.get("cart"), ensure_ascii=False),
                json.dumps(payload.get("clientSignals"), ensure_ascii=False),
                json.dumps(payload, ensure_ascii=False),
            ),
        )
    return event_id


def save_and_start_late_llm_request(llm_request, session, event_id, score_history_id):
    request_id = llm_request["request_id"]
    context = dict(llm_request.get("context") or {})
    context["event_id"] = event_id
    context["session_id"] = session["session_id"]
    created_at = now_iso()
    with connect_db() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO llm_score_requests (
                request_id, session_id, event_id, score_history_id, cart_scope_key,
                status, current_score, max_delta, default_multiplier,
                default_score_delta, context_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'applied_default', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                session["session_id"],
                event_id,
                score_history_id,
                llm_request.get("cart_scope_key") or cart_scope_key_from_session(session),
                int(context.get("current_score") or session.get("current_score") or 100),
                int(llm_request.get("max_delta") or context.get("max_delta") or 0),
                float(llm_request.get("default_multiplier") or 0.5),
                int(llm_request.get("default_score_delta") or 0),
                json.dumps(context, ensure_ascii=False),
                created_at,
                created_at,
            ),
        )

    thread = threading.Thread(
        target=run_late_llm_score_request,
        args=(request_id, context),
        daemon=True,
    )
    thread.start()


def run_late_llm_score_request(request_id, context):
    try:
        result = get_late_llm_scorer().score_multiplier(context)
        apply_late_llm_score_result(request_id, result)
    except Exception as exc:  # pragma: no cover - defensive background worker
        mark_late_llm_request_invalid(request_id, "worker_error", {"error": str(exc)})
        log_error_event(
            "late_llm_worker_error",
            str(exc),
            severity="warning",
            source="risk_llm_scorer",
            session_id=context.get("session_id"),
            metadata={"llm_request_id": request_id},
        )


def mark_late_llm_request_invalid(request_id, reason_code, result=None):
    with connect_db() as conn:
        conn.execute(
            """
            UPDATE llm_score_requests
            SET status = 'invalid', reason_code = ?, result_json = ?, updated_at = ?
            WHERE request_id = ? AND status IN ('pending', 'applied_default')
            """,
            (
                reason_code,
                json.dumps(result or {}, ensure_ascii=False),
                now_iso(),
                request_id,
            ),
        )


def expire_late_llm_request(request_id, reason_code, result=None):
    with connect_db() as conn:
        conn.execute(
            """
            UPDATE llm_score_requests
            SET status = 'expired', reason_code = ?, result_json = ?, updated_at = ?
            WHERE request_id = ? AND status IN ('pending', 'applied_default')
            """,
            (
                reason_code,
                json.dumps(result or {}, ensure_ascii=False),
                now_iso(),
                request_id,
            ),
        )


def apply_late_llm_score_result(request_id, result):
    if result.get("source") != "gemini":
        mark_late_llm_request_invalid(request_id, result.get("reason_code") or "fallback_invalid", result)
        return

    try:
        multiplier = float(result.get("multiplier"))
    except (TypeError, ValueError):
        mark_late_llm_request_invalid(request_id, "invalid_multiplier", result)
        return
    if multiplier < 0.25 or multiplier > 1.0:
        mark_late_llm_request_invalid(request_id, "out_of_range", result)
        return

    with connect_db() as conn:
        request_row = conn.execute(
            "SELECT * FROM llm_score_requests WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        if not request_row or request_row["status"] not in {"pending", "applied_default"}:
            return
        session = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (request_row["session_id"],),
        ).fetchone()
        if not session or session["status"] != "active" or not session["risk_started"]:
            conn.execute(
                """
                UPDATE llm_score_requests
                SET status = 'expired', reason_code = ?, result_json = ?, updated_at = ?
                WHERE request_id = ?
                """,
                (
                    "expired_cycle_inactive",
                    json.dumps(result, ensure_ascii=False),
                    now_iso(),
                    request_id,
                ),
            )
            return
        current_scope = cart_scope_key_from_session(session)
        if current_scope != (request_row["cart_scope_key"] or ""):
            conn.execute(
                """
                UPDATE llm_score_requests
                SET status = 'expired', reason_code = ?, result_json = ?, updated_at = ?
                WHERE request_id = ?
                """,
                (
                    "expired_cycle_changed",
                    json.dumps(result, ensure_ascii=False),
                    now_iso(),
                    request_id,
                ),
            )
            return

        max_delta = int(request_row["max_delta"] or 0)
        default_delta = int(request_row["default_score_delta"] or 0)
        llm_delta = -max(1, math.ceil(max_delta * multiplier))
        adjustment = llm_delta - default_delta
        next_score = max(0, min(100, int(session["current_score"]) + adjustment))
        timestamp = now_iso()
        reason = (
            "Late Gemini score correction applied; "
            f"llm_request_id={request_id}; "
            f"default_delta={default_delta}; llm_delta={llm_delta}; "
            f"multiplier={multiplier}; source=gemini"
        )
        conn.execute(
            """
            UPDATE sessions
            SET current_score = ?, last_seen_at = ?
            WHERE session_id = ?
            """,
            (next_score, timestamp, request_row["session_id"]),
        )
        conn.execute(
            """
            INSERT INTO score_history (
                session_id, timestamp, score, state, reason, event_id,
                score_delta, base_score_delta, risk_multiplier,
                risk_multiplier_source, llm_request_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_row["session_id"],
                timestamp,
                next_score,
                session["current_state"],
                reason,
                request_row["event_id"],
                adjustment,
                -max_delta,
                multiplier,
                "gemini_late_correction",
                request_id,
            ),
        )
        conn.execute(
            """
            UPDATE llm_score_requests
            SET status = 'applied_llm', llm_multiplier = ?, llm_score_delta = ?,
                reason_code = ?, result_json = ?, updated_at = ?
            WHERE request_id = ?
            """,
            (
                multiplier,
                llm_delta,
                result.get("reason_code") or "gemini",
                json.dumps(result, ensure_ascii=False),
                timestamp,
                request_id,
            ),
        )


def apply_analysis(session, payload, event_id):
    event = {
        "event_id": event_id,
        "event_type": (payload.get("event") or {}).get("type", ""),
        "page_type": (payload.get("source") or {}).get("pageType", ""),
        "raw_payload": payload,
    }
    recent_events = get_recent_events(session["session_id"])
    analysis = analyze_event(session, event, recent_events)
    was_risk_started = bool(session.get("risk_started"))
    if analysis.get("reset_risk_started"):
        next_risk_started = False
    else:
        next_risk_started = was_risk_started or bool(analysis.get("risk_started"))
    baseline_score = 100 if next_risk_started and not was_risk_started else int(session["current_score"])
    if analysis.get("reset_score"):
        next_score = 100
    else:
        next_score = max(0, min(100, baseline_score + int(analysis["score_delta"])))
    next_state = analysis["state"]
    debug = (
        f"base_delta={analysis.get('base_score_delta')}; "
        f"multiplier={analysis.get('risk_multiplier')}; "
        f"source={analysis.get('risk_multiplier_source')}; "
        f"risk_started={int(next_risk_started)}"
    )
    reason = "; ".join([*analysis["reasons"], debug])
    timestamp = now_iso()
    llm_request = analysis.get("llm_request")
    llm_request_id = (llm_request or {}).get("request_id")

    with connect_db() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET current_score = ?, current_state = ?, risk_started = ?
            WHERE session_id = ?
            """,
            (next_score, next_state, int(next_risk_started), session["session_id"]),
        )
        conn.execute(
            """
            INSERT INTO score_history (
                session_id, timestamp, score, state, reason, event_id,
                score_delta, base_score_delta, risk_multiplier,
                risk_multiplier_source, llm_request_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session["session_id"],
                timestamp,
                next_score,
                next_state,
                reason,
                event_id,
                int(analysis.get("score_delta") or 0),
                int(analysis.get("base_score_delta") or 0),
                float(analysis.get("risk_multiplier") or 1.0),
                analysis.get("risk_multiplier_source"),
                llm_request_id,
            ),
        )
        score_history_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]

    updated = {
        **session,
        "current_score": next_score,
        "current_state": next_state,
        "risk_started": int(next_risk_started),
    }
    if llm_request:
        save_and_start_late_llm_request(
            llm_request=llm_request,
            session=updated,
            event_id=event_id,
            score_history_id=score_history_id,
        )
    actions = persist_actions(
        updated,
        event_id,
        next_state,
        analysis["reasons"],
        analysis["recommended_actions"],
    )
    return {
        **analysis,
        "score": next_score,
        "state": next_state,
        "actions": actions,
        "llm_request_id": llm_request_id,
    }


def serialize_session(row):
    item = row_to_dict(row)
    if not item:
        return None
    item["cart_snapshot"] = decode_json(item.pop("cart_snapshot_json"), None)
    return item


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "agi", "database": str(DB_PATH)})


@app.post("/api/events")
def receive_event():
    payload = request.get_json(silent=True) or {}
    log_incoming_event(payload)
    event_type = (payload.get("event") or {}).get("type", "")
    session_id = (payload.get("user") or {}).get("sessionId")
    if event_type not in {"session_end", "logout"} and not has_scoring_cart(payload):
        return jsonify({"accepted": False, "reason": "cart_required_for_agi_scoring"}), 202
    if event_type in {"session_end", "logout"} and not session_exists(session_id):
        return jsonify({"accepted": False, "reason": "no_scoring_session_to_end"}), 202
    session = upsert_session(payload)

    if not session:
        return jsonify({"accepted": False, "reason": "anonymous_or_invalid_session"}), 202

    event_id = persist_event(payload)

    if event_type in {"session_end", "logout"}:
        analysis = None
        if session["status"] == "active":
            analysis = apply_analysis(session, payload, event_id)
        mark_session_ended(session["session_id"])
        return jsonify({"accepted": True, "sessionStatus": "ended", "analysis": analysis})

    if session["status"] != "active":
        return jsonify({"accepted": False, "reason": "session_not_active"}), 202

    analysis = apply_analysis(session, payload, event_id)
    agi_decision = None
    try:
        agent = get_agent()
        agent.observe(payload)
        agi_decision = agent.think(session["session_id"])
    except Exception as exc:
        agi_decision = {"error": str(exc), "llmStatus": "agi_pipeline_error"}
    llm_status = (
        (((agi_decision or {}).get("reasoning") or {}).get("llm") or {}).get("status")
        or (agi_decision or {}).get("llmStatus")
    )
    response = {
        "accepted": True,
        "sessionId": session["session_id"],
        "analysis": analysis,
        "agiDecision": agi_decision,
        "llmStatus": llm_status,
    }
    metadata = (payload.get("event") or {}).get("metadata") or {}
    if event_type == "clear_cart":
        response["sessionStatus"] = "cart_empty_paused"
    if event_type == "order_complete":
        if metadata.get("cartCleared", True):
            complete_scoring_session(session["session_id"])
            response["sessionStatus"] = "ended"
            response["analysis"]["score"] = 100
            response["analysis"]["state"] = "converted"
        else:
            reset_scoring_session(session["session_id"], "partial_order_reset")
            response["sessionStatus"] = "reset_for_remaining_cart"
            response["analysis"]["score"] = 100
            response["analysis"]["state"] = "partial_order_reset"
    return jsonify(
        response
    )


@app.get("/api/sessions")
def list_sessions():
    status = request.args.get("status", "active")
    user_id = request.args.get("user", "").strip()
    device_id = request.args.get("device", "").strip()
    state = request.args.get("state", "").strip()
    with connect_db() as conn:
        clauses = ["user_id != 'test123'"]
        params = []
        if status != "all":
            clauses.append("status = ?")
            params.append(status)
        if user_id:
            clauses.append("user_id LIKE ?")
            params.append(f"%{user_id}%")
        if device_id:
            clauses.append("COALESCE(device_id, '') LIKE ?")
            params.append(f"%{device_id}%")
        if state:
            clauses.append("current_state = ?")
            params.append(state)
        where_sql = " AND ".join(clauses)
        rows = conn.execute(
            f"SELECT * FROM sessions WHERE {where_sql} ORDER BY last_seen_at DESC",
            params,
        ).fetchall()
        if status == "all":
            pass
        ended_count = conn.execute(
            "SELECT COUNT(*) AS count FROM sessions WHERE status = 'ended' AND user_id != 'test123'"
        ).fetchone()["count"]
    return jsonify({"sessions": [serialize_session(row) for row in rows], "endedCount": ended_count})


@app.get("/api/sessions/<session_id>")
def session_detail(session_id):
    with connect_db() as conn:
        session = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ? AND user_id != 'test123'", (session_id,)
        ).fetchone()
        scores = conn.execute(
            "SELECT * FROM score_history WHERE session_id = ? ORDER BY id DESC LIMIT 30",
            (session_id,),
        ).fetchall()
        actions = conn.execute(
            "SELECT * FROM actions WHERE session_id = ? ORDER BY timestamp DESC",
            (session_id,),
        ).fetchall()
        feedback = conn.execute(
            "SELECT * FROM action_feedback WHERE session_id = ? ORDER BY id DESC LIMIT 30",
            (session_id,),
        ).fetchall()
        errors = conn.execute(
            "SELECT * FROM error_logs WHERE session_id = ? ORDER BY id DESC LIMIT 30",
            (session_id,),
        ).fetchall()
        llm_requests = conn.execute(
            "SELECT * FROM llm_score_requests WHERE session_id = ? ORDER BY updated_at DESC LIMIT 30",
            (session_id,),
        ).fetchall()
    if not session:
        return jsonify({"message": "Session not found"}), 404
    return jsonify(
        {
            "session": serialize_session(session),
            "events": get_recent_events(session_id, 50),
            "scoreHistory": [row_to_dict(row) for row in scores],
            "actions": [row_to_dict(row) for row in actions],
            "actionFeedback": [row_to_dict(row) for row in feedback],
            "errors": [row_to_dict(row) for row in errors],
            "llmScoreRequests": [row_to_dict(row) for row in llm_requests],
        }
    )


@app.get("/api/actions")
def list_actions():
    with connect_db() as conn:
        rows = conn.execute(
            "SELECT * FROM actions WHERE user_id != 'test123' ORDER BY timestamp DESC"
        ).fetchall()
    return jsonify({"actions": [row_to_dict(row) for row in rows]})


@app.post("/agi/observe")
def agi_observe():
    payload = request.get_json(silent=True) or {}
    session_id = ((payload.get("user") or {}).get("sessionId")) or payload.get("session_id")
    if not session_id:
        return jsonify({"accepted": False, "reason": "missing_session_id"}), 400
    get_agent().observe(payload)
    return jsonify({"accepted": True, "sessionId": session_id})


@app.post("/agi/think")
def agi_think():
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id") or payload.get("sessionId")
    if not session_id:
        return jsonify({"message": "session_id is required"}), 400
    decision = get_agent().think(session_id)
    return jsonify({"decision": decision})


@app.post("/agi/feedback")
def agi_feedback():
    payload = request.get_json(silent=True) or {}
    try:
        record = get_agent().receive_feedback(payload)
        save_action_feedback_record(record)
        feedback_type = payload.get("feedback_type") or payload.get("type")
        if feedback_type in {"action_blocked_by_safety", "action_render_failed"}:
            log_error_event(
                feedback_type,
                f"Frontend reported {feedback_type}",
                severity="warning",
                source="frontend_action_runtime",
                session_id=payload.get("session_id") or payload.get("sessionId"),
                device_id=payload.get("device_id") or payload.get("deviceId"),
                metadata=payload.get("metadata") or {},
            )
    except Exception as exc:
        log_error_event(
            "feedback_save_failure",
            str(exc),
            severity="error",
            source="agi_feedback",
            session_id=payload.get("session_id") or payload.get("sessionId"),
            device_id=payload.get("device_id") or payload.get("deviceId"),
            metadata={"payload_keys": list(payload.keys())},
        )
        raise
    return jsonify({"feedback": record})


@app.get("/agi/state/<session_id>")
def agi_state(session_id):
    with connect_db() as conn:
        world = conn.execute(
            "SELECT * FROM world_states WHERE session_id = ? ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        belief = conn.execute(
            "SELECT * FROM belief_states WHERE session_id = ? ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
    return jsonify(
        {
            "sessionId": session_id,
            "worldState": decode_json(world["world_state_json"], {}) if world else {},
            "beliefState": decode_json(belief["belief_state_json"], {}) if belief else {},
        }
    )


@app.get("/agi/decision/<session_id>")
def agi_decision(session_id):
    with connect_db() as conn:
        row = conn.execute(
            "SELECT * FROM agent_decisions WHERE session_id = ? ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
    if not row:
        return jsonify({"message": "Decision not found"}), 404
    item = row_to_dict(row)
    return jsonify(
        {
            "decision": {
                "decision_id": item["id"],
                "session_id": item["session_id"],
                "world_state": decode_json(item["world_state_json"], {}),
                "belief_state": decode_json(item["belief_state_json"], {}),
                "reasoning": decode_json(item["reasoning_json"], {}),
                "plan": decode_json(item["plan_json"], {}),
                "action": decode_json(item["action_payload_json"], {}),
                "confidence": item["confidence"],
                "safety_status": item["safety_status"],
                "llm": {
                    "provider": item["llm_provider"],
                    "model": item["llm_model"],
                    "status": item["llm_status"],
                    "latency_ms": item["llm_latency_ms"],
                },
                "timestamp": item["timestamp"],
            }
        }
    )


@app.get("/agi/evaluation")
def agi_evaluation():
    return jsonify({"metrics": get_agent().evaluator.compute_metrics()})


@app.get("/agi/evolution")
def agi_evolution():
    with connect_db() as conn:
        rows = conn.execute("SELECT * FROM agent_evolution ORDER BY id DESC LIMIT 20").fetchall()
    return jsonify({"evolution": [row_to_dict(row) for row in rows]})


@app.get("/agi/error-logs")
def agi_error_logs():
    severity = request.args.get("severity", "").strip()
    source = request.args.get("source", "").strip()
    session_id = request.args.get("session_id", "").strip()
    clauses = []
    params = []
    if severity:
        clauses.append("severity = ?")
        params.append(severity)
    if source:
        clauses.append("source = ?")
        params.append(source)
    if session_id:
        clauses.append("session_id = ?")
        params.append(session_id)
    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with connect_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM error_logs {where_sql} ORDER BY id DESC LIMIT 100",
            params,
        ).fetchall()
    return jsonify({"errors": [row_to_dict(row) for row in rows]})


@app.post("/api/sessions/<session_id>/end")
def end_session(session_id):
    mark_session_ended(session_id)
    return jsonify({"status": "ended", "sessionId": session_id})


@app.post("/api/reset")
def reset():
    with connect_db() as conn:
        for table in (
            "action_feedback",
            "error_logs",
            "llm_score_requests",
            "agent_evolution",
            "agent_feedback",
            "agent_decisions",
            "agent_memory",
            "belief_states",
            "world_states",
            "user_events",
            "actions",
            "score_history",
            "events",
            "sessions",
        ):
            conn.execute(f"DELETE FROM {table}")
    return jsonify({"status": "reset"})


@app.get("/")
def dashboard():
    return render_dashboard_html()


def render_dashboard_html():
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AGI Cart Abandonment Monitor</title>
  <style>
    body { margin: 0; font-family: Inter, system-ui, Segoe UI, sans-serif; background: #f5f7f8; color: #172026; }
    header { padding: 24px 32px; background: #102a43; color: white; display: flex; justify-content: space-between; align-items: center; }
    main { padding: 24px 32px; display: grid; grid-template-columns: 360px 1fr; gap: 20px; }
    button, select { border: 1px solid #bcccdc; border-radius: 6px; padding: 9px 12px; background: white; }
    .panel, .session { background: white; border: 1px solid #d9e2ec; border-radius: 8px; padding: 16px; }
    .sessions { display: grid; gap: 12px; }
    .session { cursor: pointer; }
    .session.active { border-color: #0b7285; box-shadow: 0 0 0 2px rgba(11,114,133,.12); }
    .score { font-size: 34px; font-weight: 800; }
    .state { color: #b15229; font-weight: 800; }
    .timeline { display: grid; gap: 10px; max-height: 430px; overflow: auto; }
    .event { border-left: 4px solid #0b7285; background: #f8fafc; padding: 10px 12px; }
    .muted { color: #64748b; }
    .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px; }
    .metric { background: #f8fafc; border-radius: 8px; padding: 14px; }
    @media (max-width: 900px) { main { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>AGI Cart Abandonment Monitor</h1>
      <p>Live rule-based backend with SQLite session storage</p>
    </div>
    <div>
      <select id="statusFilter"><option value="active">Active</option><option value="all">All</option><option value="ended">Ended</option></select>
      <button onclick="resetAll()">Reset</button>
    </div>
  </header>
  <main>
    <section class="panel">
      <h2>Sessions</h2>
      <p class="muted" id="endedCount"></p>
      <div class="sessions" id="sessions"></div>
    </section>
    <section class="panel" id="detail">
      <h2>Select a session</h2>
      <p class="muted">Browse the shopping web after login to create AGI events.</p>
    </section>
  </main>
  <script>
    let selectedId = null;
    async function loadSessions() {
      const status = document.getElementById('statusFilter').value;
      const res = await fetch('/api/sessions?status=' + status);
      const data = await res.json();
      document.getElementById('endedCount').textContent = data.endedCount + ' ended sessions retained until reset';
      const root = document.getElementById('sessions');
      root.innerHTML = data.sessions.map(s => `
        <div class="session ${s.session_id === selectedId ? 'active' : ''}" onclick="selectSession('${s.session_id}')">
          <strong>${s.user_id}</strong>
          <div class="muted">${s.latest_page_type || 'unknown'} / ${s.status}</div>
          <div>Score <strong>${s.current_score}</strong> · <span class="state">${s.current_state}</span></div>
        </div>
      `).join('') || '<p class="muted">No sessions.</p>';
      if (!selectedId && data.sessions[0]) selectSession(data.sessions[0].session_id);
    }
    async function selectSession(id) {
      selectedId = id;
      const res = await fetch('/api/sessions/' + id);
      const data = await res.json();
      const s = data.session;
      document.getElementById('detail').innerHTML = `
        <h2>${s.user_id}</h2>
        <div class="grid">
          <div class="metric"><div class="muted">Risk Score</div><div class="score">${s.current_score}</div></div>
          <div class="metric"><div class="muted">State</div><div class="state">${s.current_state}</div></div>
          <div class="metric"><div class="muted">Status</div><strong>${s.status}</strong></div>
        </div>
        <p class="muted">Latest page: ${s.latest_url || ''}</p>
        <h3>Actions</h3>
        <div class="timeline">${data.actions.map(a => `<div class="event"><strong>${a.action_type}</strong><br>${a.message}<br><span class="muted">${a.reason}</span></div>`).join('') || '<p class="muted">No actions yet.</p>'}</div>
        <h3>Event Timeline</h3>
        <div class="timeline">${data.events.map(e => `<div class="event"><strong>${e.event_type}</strong> · ${e.page_type}<br><span class="muted">${e.timestamp}</span></div>`).join('')}</div>
      `;
      loadSessions();
    }
    async function resetAll() {
      await fetch('/api/reset', { method: 'POST' });
      selectedId = null;
      await loadSessions();
      document.getElementById('detail').innerHTML = '<h2>Select a session</h2><p class="muted">Data reset.</p>';
    }
    document.getElementById('statusFilter').addEventListener('change', () => { selectedId = null; loadSessions(); });
    loadSessions();
    setInterval(() => { loadSessions(); if (selectedId) selectSession(selectedId); }, 2000);
  </script>
</body>
</html>
"""


def render_dashboard_html():
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AGI Cart Abandonment Monitor</title>
  <style>
    body { margin: 0; font-family: Inter, system-ui, Segoe UI, sans-serif; background: #f5f7f8; color: #172026; }
    header { padding: 24px 32px; background: #102a43; color: white; display: flex; justify-content: space-between; align-items: center; gap: 20px; }
    header .controls { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }
    main { padding: 24px 32px; display: grid; grid-template-columns: 360px 1fr; gap: 20px; }
    button, select, input { border: 1px solid #bcccdc; border-radius: 6px; padding: 9px 12px; background: white; }
    .panel, .session { background: white; border: 1px solid #d9e2ec; border-radius: 8px; padding: 16px; }
    .sessions { display: grid; gap: 12px; }
    .session { cursor: pointer; }
    .session.active { border-color: #0b7285; box-shadow: 0 0 0 2px rgba(11,114,133,.12); }
    .score { font-size: 34px; font-weight: 800; }
    .state { color: #b15229; font-weight: 800; }
    .timeline { display: grid; gap: 10px; max-height: 430px; overflow: auto; }
    .event { border-left: 4px solid #0b7285; background: #f8fafc; padding: 10px 12px; }
    .muted { color: #64748b; }
    .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px; }
    .metric { background: #f8fafc; border-radius: 8px; padding: 14px; }
    .wide { grid-column: 1 / -1; }
    @media (max-width: 900px) { main { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>AGI Cart Abandonment Monitor</h1>
      <p>Live agent decisions, action feedback, evaluation, and error logs</p>
    </div>
    <div class="controls">
      <select id="statusFilter"><option value="active">Active</option><option value="all">All</option><option value="ended">Ended</option></select>
      <input id="userFilter" placeholder="User" />
      <input id="deviceFilter" placeholder="Device" />
      <button onclick="resetAll()">Reset</button>
    </div>
  </header>
  <main>
    <section class="panel">
      <h2>Sessions</h2>
      <p class="muted" id="endedCount"></p>
      <div class="sessions" id="sessions"></div>
    </section>
    <section class="panel" id="detail">
      <h2>Select a session</h2>
      <p class="muted">Browse the shopping web after login to create AGI events.</p>
    </section>
    <section class="panel wide">
      <h2>Evaluation</h2>
      <div class="grid" id="metrics"></div>
      <h3>Tool Performance</h3>
      <div class="timeline" id="toolMetrics"></div>
      <h3>Error Logs</h3>
      <div class="timeline" id="errorLogs"></div>
    </section>
  </main>
  <script>
    let selectedId = null;
    async function loadSessions() {
      const status = document.getElementById('statusFilter').value;
      const params = new URLSearchParams({ status });
      const user = document.getElementById('userFilter').value.trim();
      const device = document.getElementById('deviceFilter').value.trim();
      if (user) params.set('user', user);
      if (device) params.set('device', device);
      const res = await fetch('/api/sessions?' + params.toString());
      const data = await res.json();
      document.getElementById('endedCount').textContent = data.endedCount + ' ended sessions retained until reset';
      const root = document.getElementById('sessions');
      root.innerHTML = data.sessions.map(s => `
        <div class="session ${s.session_id === selectedId ? 'active' : ''}" onclick="selectSession('${s.session_id}')">
          <strong>${s.user_id}</strong>
          <div class="muted">${s.latest_page_type || 'unknown'} / ${s.status}</div>
          <div class="muted">Device ${s.device_id || 'unknown'}</div>
          <div>Score <strong>${s.current_score}</strong> / <span class="state">${s.current_state}</span></div>
        </div>
      `).join('') || '<p class="muted">No sessions.</p>';
      if (!selectedId && data.sessions[0]) selectSession(data.sessions[0].session_id);
    }
    async function selectSession(id) {
      selectedId = id;
      const res = await fetch('/api/sessions/' + id);
      const data = await res.json();
      const s = data.session;
      document.getElementById('detail').innerHTML = `
        <h2>${s.user_id}</h2>
        <div class="grid">
          <div class="metric"><div class="muted">Risk Score</div><div class="score">${s.current_score}</div></div>
          <div class="metric"><div class="muted">State</div><div class="state">${s.current_state}</div></div>
          <div class="metric"><div class="muted">Status</div><strong>${s.status}</strong></div>
        </div>
        <p class="muted">Latest page: ${s.latest_url || ''}<br>Device: ${s.device_id || 'unknown'}</p>
        <h3>Actions</h3>
        <div class="timeline">${data.actions.map(a => `<div class="event"><strong>${a.action_type}</strong><br>${a.message}<br><span class="muted">${a.reason}</span></div>`).join('') || '<p class="muted">No actions yet.</p>'}</div>
        <h3>Action Feedback</h3>
        <div class="timeline">${(data.actionFeedback || []).map(f => `<div class="event"><strong>${f.feedback_type}</strong> / ${f.tool_name || 'unknown'}<br><span class="muted">${f.timestamp} / reward ${f.reward}</span></div>`).join('') || '<p class="muted">No action feedback yet.</p>'}</div>
        <h3>Session Errors</h3>
        <div class="timeline">${(data.errors || []).map(e => `<div class="event"><strong>${e.error_type}</strong> / ${e.severity}<br>${e.message}<br><span class="muted">${e.timestamp}</span></div>`).join('') || '<p class="muted">No errors.</p>'}</div>
        <h3>Event Timeline</h3>
        <div class="timeline">${data.events.map(e => `<div class="event"><strong>${e.event_type}</strong> / ${e.page_type}<br><span class="muted">${e.timestamp}</span></div>`).join('')}</div>
      `;
      loadSessions();
    }
    async function loadEvaluation() {
      const res = await fetch('/agi/evaluation');
      const data = await res.json();
      const m = data.metrics || {};
      const metricKeys = ['decision_count','feedback_count','action_feedback_count','action_click_rate','action_dismiss_rate','action_blocked_rate','safety_violation_count','error_count','average_reward'];
      document.getElementById('metrics').innerHTML = metricKeys.map(k => `<div class="metric"><div class="muted">${k}</div><strong>${m[k] ?? 0}</strong></div>`).join('');
      document.getElementById('toolMetrics').innerHTML = (m.tool_performance || []).map(t => `<div class="event"><strong>${t.tool_name}</strong><br>shown ${t.shown}, clicked ${t.clicked}, dismissed ${t.dismissed}, blocked ${t.blocked}<br><span class="muted">click rate ${t.click_rate}, avg reward ${t.average_reward}</span></div>`).join('') || '<p class="muted">No tool feedback yet.</p>';
      const errRes = await fetch('/agi/error-logs');
      const errData = await errRes.json();
      document.getElementById('errorLogs').innerHTML = (errData.errors || []).map(e => `<div class="event"><strong>${e.error_type}</strong> / ${e.severity}<br>${e.message}<br><span class="muted">${e.source} / ${e.timestamp}</span></div>`).join('') || '<p class="muted">No error logs.</p>';
    }
    async function resetAll() {
      await fetch('/api/reset', { method: 'POST' });
      selectedId = null;
      await loadSessions();
      await loadEvaluation();
      document.getElementById('detail').innerHTML = '<h2>Select a session</h2><p class="muted">Data reset.</p>';
    }
    document.getElementById('statusFilter').addEventListener('change', () => { selectedId = null; loadSessions(); });
    document.getElementById('userFilter').addEventListener('input', () => { selectedId = null; loadSessions(); });
    document.getElementById('deviceFilter').addEventListener('input', () => { selectedId = null; loadSessions(); });
    loadSessions();
    loadEvaluation();
    setInterval(() => { loadSessions(); loadEvaluation(); if (selectedId) selectSession(selectedId); }, 2000);
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=8001, debug=True)
