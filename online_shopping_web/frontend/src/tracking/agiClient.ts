import type { AgiDecision, AgiWebAction, Cart, Product } from "../types";

const AGI_ENDPOINT = "http://127.0.0.1:5000/api/agi/events";
const API_BASE = "http://127.0.0.1:5000";
let latestDecision: AgiDecision | null = null;

export type AgiEventType =
  | "session_start"
  | "session_end"
  | "logout"
  | "register_success"
  | "register_failed"
  | "dwell_update"
  | "page_view"
  | "page_exit"
  | "product_view"
  | "product_info_view"
  | "shipping_info_view"
  | "merchant_info_view"
  | "review_view"
  | "warranty_view"
  | "faq_view"
  | "similar_product_view"
  | "cheaper_alternative_view"
  | "add_to_cart"
  | "remove_from_cart"
  | "clear_cart"
  | "cart_view"
  | "checkout_start"
  | "checkout_exit"
  | "coupon_attempt"
  | "search"
  | "filter"
  | "order_complete";

export type AgiEventInput = {
  type: AgiEventType;
  pageType: string;
  url?: string;
  referrer?: string;
  durationMs?: number;
  targetUrl?: string;
  targetPageType?: string;
  product?: Product;
  cart?: Cart;
  metadata?: Record<string, unknown>;
};

function buildPayload(input: AgiEventInput) {
  const userId = localStorage.getItem("demoUserId") || "anonymous";
  const deviceId = getDeviceId();
  const product = input.product;
  const cart = input.cart;
  return {
    schemaVersion: "1.0",
    eventId: crypto.randomUUID(),
    timestamp: new Date().toISOString(),
    source: {
      siteId: "mock-shop",
      pageType: input.pageType,
      url: input.url || window.location.pathname,
      referrer: input.referrer || document.referrer || "",
    },
    user: {
      userId,
      sessionId: getSessionId(),
      deviceId,
      isLoggedIn: userId !== "anonymous",
    },
    event: {
      type: input.type,
      durationMs: input.durationMs || 0,
      targetUrl: input.targetUrl || "",
      targetPageType: input.targetPageType || "",
      metadata: input.metadata || {},
    },
    product: product
      ? {
          productId: product.id,
          category: product.category,
          price: product.price,
          discountPrice: product.price,
          hasCheaperAlternatives: product.cheaperAlternativeIds.length > 0,
          similarProductIds: product.similarProductIds,
          cheaperAlternativeIds: product.cheaperAlternativeIds,
        }
      : null,
    cart: cart
      ? {
          itemCount: cart.items.reduce((sum, item) => sum + item.quantity, 0),
          subtotal: cart.subtotal,
          shippingFee: cart.shipping,
          couponApplied: Boolean(input.metadata?.couponApplied),
          checkoutStep: input.pageType,
        }
      : null,
    clientSignals: {
      scrollDepth: Math.min(
        1,
        (window.scrollY + window.innerHeight) / Math.max(document.body.scrollHeight, 1),
      ),
      activeTimeMs: input.durationMs || 0,
      idleTimeMs: 0,
      tabHidden: document.hidden,
      deviceId,
    },
  };
}

export function getSessionId() {
  const key = "demoSessionId";
  const existing = localStorage.getItem(key);
  if (existing) return existing;
  const next = crypto.randomUUID();
  localStorage.setItem(key, next);
  return next;
}

export function startNewAgiSession() {
  const next = crypto.randomUUID();
  localStorage.setItem("demoSessionId", next);
  latestDecision = null;
  return next;
}

export function getDeviceId() {
  const key = "demoDeviceId";
  const existing = localStorage.getItem(key);
  if (existing) return existing;
  const next = crypto.randomUUID();
  localStorage.setItem(key, next);
  return next;
}

export async function sendAgiEvent(input: AgiEventInput) {
  const userId = localStorage.getItem("demoUserId");
  const protectedEvents: AgiEventType[] = [
    "add_to_cart",
    "remove_from_cart",
    "clear_cart",
    "cart_view",
    "checkout_start",
    "checkout_exit",
    "coupon_attempt",
    "order_complete",
  ];
  if (!userId && protectedEvents.includes(input.type)) {
    return null;
  }
  const payload = buildPayload(input);

  try {
    const response = await fetch(AGI_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (data.agiDecision && !data.agiDecision.error) {
      setLatestDecision(data.agiDecision);
    }
    dispatchWebActions(data.webActions || [], data.actionRuntimeContext || { score: data.riskScore });
    return data;
  } catch {
    console.warn("[AGI tracking] AGI backend is offline; event skipped.", input.type);
    return null;
  }
}

export function sendAgiBeacon(input: AgiEventInput) {
  const payload = buildPayload(input);
  const blob = new Blob([JSON.stringify(payload)], { type: "application/json" });
  const sent = navigator.sendBeacon?.(AGI_ENDPOINT, blob);
  if (!sent) {
    void sendAgiEvent(input);
  }
}

export function getLatestAgiDecision() {
  return latestDecision;
}

export async function sendAgiFeedback(feedbackType: string, decision: AgiDecision | null) {
  if (!decision?.decision_id) return;
  try {
    await fetch(`${API_BASE}/api/agi/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: decision.session_id,
        decision_id: decision.decision_id,
        feedback_type: feedbackType,
        page: window.location.pathname,
      }),
    });
  } catch {
    console.warn("[AGI tracking] feedback skipped.", feedbackType);
  }
}

export async function sendAgiActionFeedback(
  feedbackType: string,
  action: AgiWebAction,
  options: { renderStatus?: string; metadata?: Record<string, unknown> } = {},
) {
  try {
    await fetch(`${API_BASE}/api/agi/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: action.session_id,
        decision_id: action.decision_id,
        action_id: action.action_id,
        tool_name: action.tool_name,
        action_type: action.action_type,
        feedback_type: feedbackType,
        render_status: options.renderStatus || "ok",
        device_id: getDeviceId(),
        page: window.location.pathname,
        metadata: options.metadata || {},
      }),
    });
  } catch {
    console.warn("[AGI tracking] action feedback skipped.", feedbackType);
  }
}

function setLatestDecision(decision: AgiDecision) {
  latestDecision = decision;
}

function dispatchWebActions(actions: AgiWebAction[], context: { score?: number } = {}) {
  if (!actions.length) return;
  window.dispatchEvent(new CustomEvent("agi-web-actions", { detail: { actions, context } }));
}
