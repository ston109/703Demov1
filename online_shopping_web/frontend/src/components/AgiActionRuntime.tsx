import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { sendAgiActionFeedback } from "../tracking/agiClient";
import type { AgiWebAction } from "../types";

const POPUP_SCORE_THRESHOLD = 80;
const COOLDOWN_MS = 30_000;
const ALLOWED_TOOLS = new Set([
  "show_shipping_info",
  "show_return_policy",
  "show_product_reviews",
  "show_product_comparison",
  "show_coupon",
  "offer_small_discount",
  "highlight_support",
  "show_related_recommendations",
  "show_trust_message",
]);

export function AgiActionRuntime() {
  const location = useLocation();
  const [actions, setActions] = useState<AgiWebAction[]>([]);

  useEffect(() => {
    function handleActions(event: Event) {
      const detail = (event as CustomEvent<{ actions: AgiWebAction[]; context?: { score?: number } }>).detail;
      const incomingActions = Array.isArray(detail) ? detail : detail?.actions || [];
      const score = Array.isArray(detail) ? undefined : detail?.context?.score;
      const validActions = incomingActions.filter(validateAction);
      const pageActions = validActions.filter((action) => pageMatches(action, location.pathname));
      const uniqueActions = dedupeByContent(pageActions);
      const currentKeys = new Set(actions.map(contentKey));
      const suppressed: Array<{ action: AgiWebAction; reason: string }> = [];

      for (const action of incomingActions.filter((action) => !validateAction(action))) {
        suppressed.push({ action, reason: "frontend_allowlist" });
      }

      let nextActions: AgiWebAction[] = [];
      if (shouldSuppressForScore(score)) {
        suppressed.push(...uniqueActions.map((action) => ({ action, reason: "score_above_popup_threshold" })));
      } else {
        nextActions = uniqueActions.filter((action) => {
          if (currentKeys.has(contentKey(action))) {
            suppressed.push({ action, reason: "duplicate_content" });
            return false;
          }
          if (isCoolingDown(action)) {
            suppressed.push({ action, reason: "cooldown" });
            return false;
          }
          return true;
        });
      }

      for (const action of nextActions) {
        markCoolingDown(action);
        if (action.tool_name === "highlight_support") {
          window.dispatchEvent(new CustomEvent("agi-support-highlight", { detail: action }));
        }
        if (action.tool_name === "offer_small_discount") {
          localStorage.setItem("demoCartIncentiveMultiplier", String(action.discountMultiplier || 0.95));
          window.dispatchEvent(new CustomEvent("agi-cart-incentive", { detail: action }));
        }
        void sendAgiActionFeedback("action_shown", action, { metadata: { page: location.pathname } });
      }

      for (const item of suppressed) {
        void sendAgiActionFeedback(
          item.reason === "frontend_allowlist" ? "action_blocked_by_safety" : "action_expired",
          item.action,
          {
            renderStatus: item.reason === "frontend_allowlist" ? "blocked" : "suppressed",
            metadata: { suppressedReason: item.reason, score, page: location.pathname },
          },
        );
      }

      if (nextActions.length) {
        setActions((current) => mergeActions(current, nextActions));
      }
    }

    window.addEventListener("agi-web-actions", handleActions);
    return () => window.removeEventListener("agi-web-actions", handleActions);
  }, [actions, location.pathname]);

  const visible = useMemo(
    () => actions.filter((action) => pageMatches(action, location.pathname)),
    [actions, location.pathname],
  );

  if (!visible.length) return null;

  return (
    <div className="agi-runtime">
      {visible.map((action) => (
        <article className={`agi-runtime-card ${action.priority}`} key={action.action_id}>
          <button className="agi-runtime-close" onClick={() => dismiss(action)}>
            Close
          </button>
          <strong>{titleFor(action)}</strong>
          <p>{action.message}</p>
          <ActionControls action={action} />
        </article>
      ))}
    </div>
  );

  function dismiss(action: AgiWebAction) {
    setActions((current) => current.filter((item) => item.action_id !== action.action_id));
    void sendAgiActionFeedback("action_dismissed", action);
  }
}

function ActionControls({ action }: { action: AgiWebAction }) {
  if (action.tool_name === "offer_small_discount") {
    return (
      <button
        className="secondary-button"
        onClick={() => {
          localStorage.setItem("demoCartIncentiveMultiplier", String(action.discountMultiplier || 0.95));
          window.dispatchEvent(new CustomEvent("agi-cart-incentive", { detail: action }));
          void sendAgiActionFeedback("discount_applied", action);
        }}
      >
        Apply demo incentive
      </button>
    );
  }

  if (action.tool_name === "highlight_support") {
    return (
      <button
        className="secondary-button"
        onClick={() => {
          window.dispatchEvent(new CustomEvent("agi-open-support", { detail: action }));
          void sendAgiActionFeedback("action_clicked", action);
        }}
      >
        Contact support
      </button>
    );
  }

  if (action.tool_name === "show_related_recommendations") {
    return (
      <div className="agi-runtime-products">
        {(action.products || []).map((product) => (
          <Link
            key={product.id}
            to={`/products/${product.id}`}
            onClick={() => void sendAgiActionFeedback("action_clicked", action, { metadata: { productId: product.id } })}
          >
            <span>{product.name}</span>
            <strong>${product.price.toFixed(2)}</strong>
          </Link>
        ))}
        {!action.products?.length ? (
          <Link to="/products" onClick={() => void sendAgiActionFeedback("action_clicked", action)}>
            View related products
          </Link>
        ) : null}
      </div>
    );
  }

  const target = targetLink(action);
  if (!target) return null;
  return (
    <Link className="secondary-button" to={target} onClick={() => void sendAgiActionFeedback("action_clicked", action)}>
      View details
    </Link>
  );
}

function validateAction(action: AgiWebAction) {
  if (!action?.action_id || !ALLOWED_TOOLS.has(action.tool_name)) return false;
  if (action.tool_name === "offer_small_discount") {
    return Boolean(action.demoIncentive) && Number(action.discountMultiplier || 1) >= 0.95;
  }
  if (action.tool_name === "highlight_support" && action.externalContact) return false;
  return !/auto_purchase|modify_price|credit card|send_email|send_sms/i.test(JSON.stringify(action));
}

export function shouldSuppressForScore(score?: number) {
  return typeof score === "number" && score > POPUP_SCORE_THRESHOLD;
}

function pageMatches(action: AgiWebAction, pathname: string) {
  const target = action.target_page || "any";
  if (target === "any" || target === "cart_or_checkout") return target === "any" || pathname === "/cart" || pathname === "/checkout";
  if (target === "cart") return pathname === "/cart";
  if (target === "checkout") return pathname === "/checkout";
  if (target === "product_detail") return pathname.startsWith("/products/");
  return true;
}

function isCoolingDown(action: AgiWebAction) {
  const key = `agiActionCooldown:${contentKey(action)}`;
  const previous = Number(sessionStorage.getItem(key) || 0);
  return Date.now() - previous < COOLDOWN_MS;
}

function markCoolingDown(action: AgiWebAction) {
  const key = `agiActionCooldown:${contentKey(action)}`;
  sessionStorage.setItem(key, String(Date.now()));
}

function mergeActions(current: AgiWebAction[], next: AgiWebAction[]) {
  const byId = new Map(current.map((action) => [contentKey(action), action]));
  for (const action of next) byId.set(contentKey(action), action);
  return Array.from(byId.values()).slice(-3);
}

export function dedupeByContent(actions: AgiWebAction[]) {
  const byContent = new Map<string, AgiWebAction>();
  for (const action of actions) {
    const key = contentKey(action);
    const existing = byContent.get(key);
    if (!existing || priorityRank(action.priority) > priorityRank(existing.priority)) {
      byContent.set(key, action);
    }
  }
  return Array.from(byContent.values());
}

function contentKey(action: AgiWebAction) {
  return [
    action.tool_name,
    action.target_page || "any",
    normalizeMessage(action.message),
  ].join(":");
}

function normalizeMessage(message: string) {
  return (message || "").trim().toLowerCase().replace(/\s+/g, " ");
}

function priorityRank(priority: string) {
  return { high: 3, medium: 2, low: 1 }[priority] || 0;
}

function titleFor(action: AgiWebAction) {
  return {
    show_shipping_info: "Shipping help",
    show_return_policy: "Return policy",
    show_product_reviews: "Review summary",
    show_product_comparison: "Compare options",
    show_coupon: "Coupon help",
    offer_small_discount: "Demo cart incentive",
    highlight_support: "Checkout support",
    show_related_recommendations: "Related products",
    show_trust_message: "Checkout reassurance",
  }[action.tool_name] || "Shopping assist";
}

function targetLink(action: AgiWebAction) {
  if (action.tool_name === "show_shipping_info") return "/cart";
  if (action.tool_name === "show_return_policy") return "/products";
  if (action.tool_name === "show_product_reviews") return "/products";
  return null;
}
