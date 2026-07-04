import math
import uuid


DEDUCTION_RULES = {
    "product_view": 1,
    "product_info_view": 1,
    "shipping_info_view": 2,
    "merchant_info_view": 2,
    "review_view": 2,
    "warranty_view": 2,
    "long_dwell": 3,
    "repeated_product_attention": 2,
    "similar_product_view": 2,
    "cheaper_alternative_view": 4,
    "search_after_cart": 1,
    "filter_after_cart": 1,
    "sort_price_low_after_cart": 2,
    "cart_view": 1,
    "coupon_failed": 3,
    "shipping_fee_visible": 2,
    "remove_from_cart": 4,
    "clear_cart": 8,
    "cart_long_dwell": 3,
    "checkout_long_dwell": 4,
    "return_to_cart_from_checkout": 3,
    "return_to_product_from_checkout": 4,
    "repeat_shipping_view": 3,
    "repeat_review_or_info_view": 2,
    "comparison_loop": 3,
    "site_exit_cart": 4,
    "site_exit_checkout": 6,
    "site_exit_product": 3,
    "checkout_exit": 6,
    "page_exit_cart_or_checkout": 3,
}


def analyze_event(session, event, recent_events):
    event_type = event.get("event_type", "")
    page_type = event.get("page_type", "")
    raw = event.get("raw_payload", {}) or {}
    event_body = raw.get("event", {}) or {}
    cart = raw.get("cart") or {}
    product = raw.get("product") or {}
    metadata = event_body.get("metadata", {}) or {}

    risk_started = bool(session.get("risk_started"))
    is_cart_start = page_type == "cart" and event_type in {"page_view", "cart_view"}
    is_cart_exit = page_type == "cart" and event_type == "page_exit"
    is_checkout_start = event_type == "checkout_start"
    is_checkout_leave = event_type == "checkout_exit" or (
        event_type == "page_exit" and page_type == "checkout"
    )
    duplicate_checkout_page_exit = (
        event_type == "page_exit"
        and page_type == "checkout"
        and has_recent_explicit_checkout_exit(recent_events)
    )

    state = session.get("current_state") or "browsing_uncertain"
    reasons = []
    recommended_actions = []
    risk_multiplier = 1.0
    risk_multiplier_source = "positive_or_zero"
    base_score_delta = 0
    score_delta = 0

    if event_type == "clear_cart":
        return {
            "score_delta": 0,
            "base_score_delta": 0,
            "risk_multiplier": 1.0,
            "risk_multiplier_source": "cart_scope_paused",
            "risk_started": False,
            "reset_risk_started": True,
            "reset_score": True,
            "state": "cart_empty_paused",
            "reasons": ["Cart was cleared; risk scoring is paused and reset to 100."],
            "recommended_actions": [],
        }

    if duplicate_checkout_page_exit:
        return {
            "score_delta": 0,
            "base_score_delta": 0,
            "risk_multiplier": 1.0,
            "risk_multiplier_source": "duplicate_checkout_exit_ignored",
            "risk_started": risk_started,
            "state": state,
            "reasons": ["Checkout page exit was recorded after checkout_exit; duplicate scoring skipped."],
            "recommended_actions": [],
        }

    if is_cart_start and not risk_started:
        return {
            "score_delta": 0,
            "base_score_delta": 0,
            "risk_multiplier": 1.0,
            "risk_multiplier_source": "cart_observed",
            "risk_started": False,
            "state": "cart_observed",
            "reasons": ["Cart entered; score remains 100 until the user leaves the cart with items."],
            "recommended_actions": [],
        }

    if not risk_started and not is_cart_exit:
        return {
            "score_delta": 0,
            "base_score_delta": 0,
            "risk_multiplier": 1.0,
            "risk_multiplier_source": "not_started",
            "risk_started": False,
            "state": state,
            "reasons": ["Event recorded; risk scoring starts when the user leaves the cart with items."],
            "recommended_actions": [],
        }

    if is_checkout_start:
        return {
            "score_delta": 0,
            "base_score_delta": 0,
            "risk_multiplier": 1.0,
            "risk_multiplier_source": "checkout_started",
            "risk_started": risk_started,
            "state": "checkout_monitoring",
            "reasons": ["Checkout entered; monitoring remains active without changing score."],
            "recommended_actions": [],
        }

    context = build_event_context(event_body, cart, product, metadata, page_type, recent_events)
    duration_ms = context["duration_ms"]
    shipping_fee = context["shipping_fee"]
    cart_product_ids = context["cart_product_ids"]
    product_id = context["product_id"]
    product_in_cart = context["product_in_cart"]
    product_related_to_cart = context["product_related_to_cart"]
    cart_context = context["cart_context"]
    same_product_views = context["same_product_views"]
    checkout_recent = context["checkout_recent"]
    comparison_recent_count = context["comparison_recent_count"]

    candidates = []

    if event_type == "product_view" and product_in_cart:
        candidates.append(
            deduction(
                "product_view",
                "browsing_uncertain",
                "Cart product overview was viewed after cart monitoring started.",
            )
        )

    if event_type == "product_view" and product_in_cart and checkout_recent:
        candidates.append(
            deduction(
                "return_to_product_from_checkout",
                "checkout_friction",
                "User returned from checkout to a cart product page, suggesting unresolved checkout friction.",
                [
                    {
                        "action_type": "checkout_help",
                        "message": "Offer help for checkout questions before the user leaves.",
                    }
                ],
            )
        )

    if event_type == "product_view" and product_related_to_cart:
        candidates.append(
            deduction(
                "similar_product_view",
                "comparison_hesitation",
                "A product related to the current cart item was viewed, suggesting comparison hesitation.",
                [
                    {
                        "action_type": "product_comparison_help",
                        "message": "Show a concise comparison against the cart item.",
                    }
                ],
            )
        )

    if event_type == "product_info_view" and product_in_cart:
        candidates.append(
            deduction(
                "product_info_view",
                "product_uncertainty",
                "Cart product information page was viewed, suggesting product uncertainty.",
                [
                    {
                        "action_type": "product_review_or_specs_help",
                        "message": "Show concise product specs or review highlights for the cart item.",
                    }
                ],
            )
        )

    if event_type == "shipping_info_view" and product_in_cart:
        candidates.append(
            deduction(
                "shipping_info_view",
                "shipping_fee_blocked",
                "Cart product shipping page was viewed, suggesting shipping concern.",
                [
                    {
                        "action_type": "free_shipping_offer",
                        "message": "Clarify shipping cost, ETA, and any free-shipping threshold.",
                    }
                ],
            )
        )

    if event_type == "shipping_info_view" and product_in_cart and count_recent_events(
        recent_events, {"shipping_info_view"}
    ) >= 1:
        candidates.append(
            deduction(
                "repeat_shipping_view",
                "shipping_fee_blocked",
                "Shipping information was checked repeatedly for a cart item.",
                [
                    {
                        "action_type": "shipping_clarity_message",
                        "message": "Show shipping ETA, cost, and threshold in a compact message.",
                    }
                ],
            )
        )

    if event_type == "shipping_info_view" and product_in_cart and checkout_recent:
        candidates.append(
            deduction(
                "return_to_product_from_checkout",
                "shipping_fee_blocked",
                "User returned from checkout to shipping details, suggesting shipping concern.",
            )
        )

    if event_type == "merchant_info_view" and product_in_cart:
        candidates.append(
            deduction(
                "merchant_info_view",
                "trust_concern",
                "Cart product merchant page was viewed, suggesting seller trust concern.",
                [
                    {
                        "action_type": "trust_message",
                        "message": "Show merchant verification, rating, and support promise.",
                    }
                ],
            )
        )

    if event_type == "review_view" and product_in_cart:
        candidates.append(
            deduction(
                "review_view",
                "product_uncertainty",
                "Cart product reviews were viewed, suggesting product confidence checking.",
                [
                    {
                        "action_type": "review_summary",
                        "message": "Show a balanced review summary for the cart item.",
                    }
                ],
            )
        )

    if event_type in {"product_info_view", "review_view", "warranty_view"} and product_in_cart and count_recent_events(
        recent_events, {"product_info_view", "review_view", "warranty_view"}
    ) >= 2:
        candidates.append(
            deduction(
                "repeat_review_or_info_view",
                "product_uncertainty",
                "Product information, reviews, or warranty were checked repeatedly for a cart item.",
                [
                    {
                        "action_type": "confidence_summary",
                        "message": "Show a short confidence summary with specs, reviews, and return policy.",
                    }
                ],
            )
        )

    if event_type == "warranty_view" and product_in_cart:
        candidates.append(
            deduction(
                "warranty_view",
                "trust_concern",
                "Cart product warranty page was viewed, suggesting return or after-sales concern.",
                [
                    {
                        "action_type": "return_policy_message",
                        "message": "Clarify warranty coverage and return window for the cart item.",
                    }
                ],
            )
        )

    if event_type == "dwell_update" and page_type == "product_detail" and product_in_cart and duration_ms >= 30000:
        candidates.append(
            deduction(
                "long_dwell",
                "browsing_uncertain",
                "Long dwell on product detail after checkout hesitation started.",
            )
        )

    if event_type == "dwell_update" and page_type == "cart" and duration_ms >= 30000:
        candidates.append(
            deduction(
                "cart_long_dwell",
                "cart_hesitation",
                "User stayed on the cart for a long time without moving forward.",
                [
                    {
                        "action_type": "cart_reminder",
                        "message": "Reassure the user that their cart is saved and checkout remains available.",
                    }
                ],
            )
        )

    if event_type == "dwell_update" and page_type == "checkout" and duration_ms >= 30000:
        candidates.append(
            deduction(
                "checkout_long_dwell",
                "checkout_friction",
                "User stayed on checkout for a long time without completing order.",
                [
                    {
                        "action_type": "checkout_help",
                        "message": "Offer concise checkout support.",
                    }
                ],
            )
        )

    if product_in_cart and same_product_views >= 3:
        candidates.append(
            deduction(
                "repeated_product_attention",
                "browsing_uncertain",
                "Repeated attention on the same cart product suggests hesitation.",
            )
        )

    if event_type in {"similar_product_view", "cheaper_alternative_view"} and (
        product_in_cart or product_related_to_cart or cart_context
    ):
        candidates.append(
            deduction(
                event_type,
                "price_sensitive" if event_type == "cheaper_alternative_view" else "comparison_hesitation",
                "User is comparing products related to a current cart item.",
                [
                    {
                        "action_type": "discount_or_cheaper_recommendation",
                        "message": "Send a targeted discount or recommend the lower-priced similar product.",
                    }
                ],
            )
        )

    if event_type in {"product_view", "similar_product_view", "cheaper_alternative_view"} and comparison_recent_count >= 3 and (
        product_in_cart or product_related_to_cart
    ):
        candidates.append(
            deduction(
                "comparison_loop",
                "comparison_hesitation",
                "User is looping through related products instead of returning to checkout.",
                [
                    {
                        "action_type": "product_comparison_help",
                        "message": "Show a compact comparison between the cart item and viewed alternatives.",
                    }
                ],
            )
        )

    if event_type == "cart_view":
        candidates.append(
            deduction(
                "cart_view",
                "cart_hesitation",
                "Cart was opened after checkout hesitation started.",
                [
                    {
                        "action_type": "cart_reminder",
                        "message": "Keep the cart saved and remind the user before intent fades.",
                    }
                ],
            )
        )

    if event_type == "cart_view" and checkout_recent:
        candidates.append(
            deduction(
                "return_to_cart_from_checkout",
                "checkout_friction",
                "User returned from checkout to cart, suggesting checkout friction.",
                [
                    {
                        "action_type": "checkout_help",
                        "message": "Ask whether shipping, payment, or product details are blocking checkout.",
                    }
                ],
            )
        )

    if event_type == "coupon_attempt" and not metadata.get("success", False):
        candidates.append(
            deduction(
                "coupon_failed",
                "price_sensitive",
                "Coupon failure indicates price sensitivity.",
                [
                    {
                        "action_type": "discount_email",
                        "message": "Offer a small recovery discount after failed coupon attempt.",
                    }
                ],
            )
        )

    if event_type == "search" and (metadata.get("search") or "").strip():
        candidates.append(
            deduction(
                "search_after_cart",
                "comparison_hesitation",
                "User searched after cart monitoring started, suggesting comparison or uncertainty.",
            )
        )

    if event_type == "filter" and metadata.get("category") and metadata.get("category") != "All":
        candidates.append(
            deduction(
                "filter_after_cart",
                "comparison_hesitation",
                "User filtered products after cart monitoring started, suggesting comparison shopping.",
            )
        )

    if event_type == "filter" and metadata.get("sort") == "price_asc":
        candidates.append(
            deduction(
                "sort_price_low_after_cart",
                "price_sensitive",
                "User sorted products by lowest price after cart monitoring started.",
                [
                    {
                        "action_type": "price_reassurance",
                        "message": "Clarify value, sale price, or available lower-cost alternatives.",
                    }
                ],
            )
        )

    if event_type == "remove_from_cart":
        candidates.append(
            deduction(
                "remove_from_cart",
                "cart_weakening",
                "User removed an item from the cart.",
                [
                    {
                        "action_type": "cart_recovery_message",
                        "message": "Confirm the cart update and keep checkout easy for remaining items.",
                    }
                ],
            )
        )

    if shipping_fee > 0 and page_type in {"cart", "checkout"}:
        candidates.append(
            deduction(
                "shipping_fee_visible",
                "shipping_fee_blocked",
                "Shipping fee is visible during cart or checkout.",
                [
                    {
                        "action_type": "free_shipping_offer",
                        "message": "Offer free shipping or show a free-shipping threshold.",
                    }
                ],
            )
        )

    if event_type == "checkout_exit":
        candidates.append(
            deduction(
                "checkout_exit",
                "checkout_friction",
                "User exited checkout before completing order.",
                [
                    {
                        "action_type": "customer_service_contact",
                        "message": "Trigger customer service help for checkout friction.",
                    }
                ],
            )
        )

    if event_type == "page_exit" and page_type in {"cart", "checkout"}:
        candidates.append(
            deduction(
                "page_exit_cart_or_checkout",
                "cart_hesitation" if page_type == "cart" else "checkout_friction",
                f"User left the {page_type} page.",
            )
        )

    if event_type in {"session_end", "logout"}:
        exit_rule = {
            "cart": ("site_exit_cart", "cart_hesitation", "User left the site from the cart."),
            "checkout": ("site_exit_checkout", "checkout_friction", "User left the site from checkout."),
            "product_detail": ("site_exit_product", "browsing_uncertain", "User left the site from a cart-related product page."),
            "product_info": ("site_exit_product", "product_uncertainty", "User left the site from a product info page."),
            "product_shipping": ("site_exit_product", "shipping_fee_blocked", "User left the site from a shipping details page."),
            "product_reviews": ("site_exit_product", "product_uncertainty", "User left the site from a reviews page."),
            "product_warranty": ("site_exit_product", "trust_concern", "User left the site from a warranty page."),
        }.get(page_type)
        if exit_rule:
            rule_name, exit_state, reason = exit_rule
            candidates.append(deduction(rule_name, exit_state, reason))

    if event_type == "order_complete":
        return {
            "score_delta": 0,
            "base_score_delta": 0,
            "risk_multiplier": 1.0,
            "risk_multiplier_source": "order_complete_reset",
            "risk_started": risk_started,
            "state": "converted",
            "reasons": ["Order completed; score is reset or session is ended by cart scope."],
            "recommended_actions": [],
        }

    if candidates:
        scoring = apply_risk_multiplier(
            session=session,
            event_id=event.get("event_id"),
            event_type=event_type,
            page_type=page_type,
            cart_product_ids=cart_product_ids,
            product_in_cart=product_in_cart,
            duration_ms=duration_ms,
            shipping_fee=shipping_fee,
            recent_events=recent_events,
            candidates=candidates,
        )
        base_score_delta = scoring["base_score_delta"]
        risk_multiplier = scoring["risk_multiplier"]
        risk_multiplier_source = scoring["risk_multiplier_source"]
        score_delta = scoring["score_delta"]
        llm_request = scoring.get("llm_request")
        state = candidates[-1]["state"]
        reasons.extend(item["reason"] for item in candidates)
        for item in candidates:
            recommended_actions.extend(item["recommended_actions"])

    projected_score = max(0, min(100, int(session.get("current_score", 100)) + score_delta))
    if projected_score <= 45 and state != "converted":
        state = "high_abandonment_risk"
        recommended_actions.append(
            {
                "action_type": "urgent_retention_message",
                "message": "Send urgent retention message before cart abandonment.",
            }
        )
        reasons.append("Risk score crossed high-risk threshold.")

    if not reasons:
        reasons.append("Event recorded; no strong abandonment signal.")

    return {
        "score_delta": score_delta,
        "base_score_delta": base_score_delta,
        "risk_multiplier": risk_multiplier,
        "risk_multiplier_source": risk_multiplier_source,
        "llm_request": llm_request if candidates else None,
        "risk_started": risk_started or is_cart_exit,
        "state": state,
        "reasons": reasons,
        "recommended_actions": recommended_actions,
    }


def deduction(rule_name, state, reason, recommended_actions=None):
    return {
        "rule": rule_name,
        "max_delta": DEDUCTION_RULES[rule_name],
        "state": state,
        "reason": reason,
        "recommended_actions": recommended_actions or [],
    }


def build_event_context(event_body, cart, product, metadata, page_type, recent_events):
    duration_ms = int(event_body.get("durationMs") or 0)
    shipping_fee = float(cart.get("shippingFee") or cart.get("shipping") or 0)
    item_count = int(cart.get("itemCount") or 0)
    cart_product_ids = extract_cart_product_ids(cart, metadata)
    product_id = product.get("productId")
    product_in_cart = bool(product_id and product_id in cart_product_ids)
    product_related_to_cart = is_product_related_to_cart(product, product_in_cart, cart_product_ids)
    recent_event_types = [item.get("event_type") for item in recent_events if item.get("event_type")]
    recent_page_types = [item.get("page_type") for item in recent_events if item.get("page_type")]

    return {
        "duration_ms": duration_ms,
        "shipping_fee": shipping_fee,
        "cart_product_ids": cart_product_ids,
        "product_id": product_id,
        "product_in_cart": product_in_cart,
        "product_related_to_cart": product_related_to_cart,
        "cart_context": item_count > 0 and page_type in {"cart", "checkout"},
        "same_product_views": count_same_product_views(product_id, recent_events),
        "checkout_recent": "checkout_start" in recent_event_types[1:] or "checkout" in recent_page_types[1:],
        "comparison_recent_count": count_comparison_loop_events(recent_events),
    }


def extract_cart_product_ids(cart, metadata):
    cart_product_ids = set(cart.get("cartProductIds") or metadata.get("cartProductIds") or [])
    for item in cart.get("items") or []:
        item_product = item.get("product") or {}
        if item_product.get("id"):
            cart_product_ids.add(item_product["id"])
    return cart_product_ids


def is_product_related_to_cart(product, product_in_cart, cart_product_ids):
    product_id = product.get("productId")
    similar_product_ids = set(product.get("similarProductIds") or [])
    cheaper_alternative_ids = set(product.get("cheaperAlternativeIds") or [])
    return bool(
        not product_in_cart
        and product_id
        and (
            similar_product_ids.intersection(cart_product_ids)
            or cheaper_alternative_ids.intersection(cart_product_ids)
        )
    )


def count_same_product_views(product_id, recent_events):
    if not product_id:
        return 0
    return sum(
        1
        for item in recent_events
        if (item.get("raw_payload", {}).get("product") or {}).get("productId") == product_id
        and item.get("event_type") in {"product_view", "page_view", "dwell_update"}
    )


def count_comparison_loop_events(recent_events):
    return sum(
        1
        for item in recent_events[1:8]
        if item.get("event_type") in {"similar_product_view", "cheaper_alternative_view"}
        or item.get("page_type") == "product_detail"
    )


def apply_risk_multiplier(
    session,
    event_id,
    event_type,
    page_type,
    cart_product_ids,
    product_in_cart,
    duration_ms,
    shipping_fee,
    recent_events,
    candidates,
):
    total_max_delta = sum(item["max_delta"] for item in candidates)
    multiplier_result = choose_risk_multiplier(
        session=session,
        event_id=event_id,
        event_type=event_type,
        page_type=page_type,
        cart_product_ids=cart_product_ids,
        product_in_cart=product_in_cart,
        duration_ms=duration_ms,
        shipping_fee=shipping_fee,
        recent_events=recent_events,
        max_delta=total_max_delta,
    )
    risk_multiplier = multiplier_result["multiplier"]
    return {
        "base_score_delta": -total_max_delta,
        "risk_multiplier": risk_multiplier,
        "risk_multiplier_source": multiplier_result["source"],
        "score_delta": -max(1, math.ceil(total_max_delta * risk_multiplier)),
        "llm_request": multiplier_result.get("llm_request"),
    }


def has_recent_explicit_checkout_exit(recent_events):
    for item in recent_events[1:6]:
        if item.get("event_type") == "checkout_exit":
            return True
    return False


def count_recent_events(recent_events, event_types, limit=8):
    return sum(
        1
        for item in recent_events[1 : limit + 1]
        if item.get("event_type") in event_types
    )


def choose_risk_multiplier(
    session,
    event_id,
    event_type,
    page_type,
    cart_product_ids,
    product_in_cart,
    duration_ms,
    shipping_fee,
    recent_events,
    max_delta,
):
    current_score = int(session.get("current_score", 100))
    if current_score >= 70:
        return {"multiplier": 0.5, "source": "default_half", "reason_code": "score_not_low_enough"}
    request_id = str(uuid.uuid4())
    context = {
        "llm_request_id": request_id,
        "session_id": session.get("session_id"),
        "event_id": event_id,
        "current_score": current_score,
        "event_type": event_type,
        "page_type": page_type,
        "cart_product_ids": sorted(cart_product_ids),
        "product_in_cart": product_in_cart,
        "duration_ms": duration_ms,
        "shipping_fee": shipping_fee,
        "recent_cart_events": [
            item.get("event_type")
            for item in recent_events[:8]
            if item.get("event_type")
        ],
        "max_delta": max_delta,
    }
    return {
        "multiplier": 0.5,
        "source": "default_half_pending_llm",
        "reason_code": "llm_async_pending",
        "llm_request": {
            "request_id": request_id,
            "context": context,
            "max_delta": max_delta,
            "default_multiplier": 0.5,
            "default_score_delta": -max(1, math.ceil(max_delta * 0.5)),
            "cart_scope_key": "|".join(sorted(cart_product_ids)),
        },
    }
