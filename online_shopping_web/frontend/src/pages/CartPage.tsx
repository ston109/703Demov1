import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { clearCart, fetchCart, removeFromCart, startCheckout, updateCart } from "../api";
import { getLatestAgiDecision, sendAgiEvent, sendAgiFeedback } from "../tracking/agiClient";
import { usePageTracking } from "../tracking/usePageTracking";
import type { Cart } from "../types";

export function CartPage() {
  const navigate = useNavigate();
  const [cart, setCart] = useState<Cart | null>(null);
  const cartRef = useRef<Cart | null>(null);
  const [coupon, setCoupon] = useState("");
  const [couponMessage, setCouponMessage] = useState("");
  const [error, setError] = useState("");
  const [incentiveMultiplier, setIncentiveMultiplier] = useState(() =>
    Number(localStorage.getItem("demoCartIncentiveMultiplier") || 1),
  );
  usePageTracking("cart", { getCart: () => cartRef.current });

  useEffect(() => {
    cartRef.current = cart;
  }, [cart]);

  useEffect(() => {
    function syncIncentive() {
      setIncentiveMultiplier(Number(localStorage.getItem("demoCartIncentiveMultiplier") || 1));
    }
    window.addEventListener("agi-cart-incentive", syncIncentive);
    return () => window.removeEventListener("agi-cart-incentive", syncIncentive);
  }, []);

  useEffect(() => {
    fetchCart()
      .then((response) => {
        setCart(response);
        sendAgiEvent({ type: "cart_view", pageType: "cart", cart: response });
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Please log in first."));
  }, []);

  async function changeQuantity(productId: string, quantity: number) {
    const next = await updateCart(productId, quantity);
    setCart(next);
  }

  async function remove(productId: string) {
    if (cart) {
      await sendAgiEvent({
        type: "remove_from_cart",
        pageType: "cart",
        cart,
        metadata: { removedProductId: productId },
      });
    }
    const next = await removeFromCart(productId);
    setCart(next);
  }

  async function clear() {
    if (cart) {
      await sendAgiEvent({ type: "clear_cart", pageType: "cart", cart });
    }
    const next = await clearCart();
    localStorage.removeItem("demoCartIncentiveMultiplier");
    setIncentiveMultiplier(1);
    setCart(next);
  }

  function attemptCoupon() {
    const success = coupon.trim().toUpperCase() === "SAVE10";
    setCouponMessage(success ? "Coupon accepted for demo intent." : "Coupon not recognized.");
    sendAgiEvent({
      type: "coupon_attempt",
      pageType: "cart",
      cart: cart || undefined,
      metadata: { coupon, success },
    });
  }

  async function checkout() {
    try {
      const response = await startCheckout();
      await sendAgiEvent({ type: "checkout_start", pageType: "cart", cart: response.cart });
      void sendAgiFeedback("checkout_continued", getLatestAgiDecision());
      navigate("/checkout");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Please log in first.");
    }
  }

  if (error) {
    return (
      <section className="page empty-state">
        <h1>{error}</h1>
        <Link className="secondary-button" to="/login">
          Login or register
        </Link>
      </section>
    );
  }

  if (!cart) return <section className="page">Loading cart...</section>;
  const safeMultiplier = incentiveMultiplier >= 0.95 && incentiveMultiplier < 1 ? incentiveMultiplier : 1;
  const incentiveAmount = safeMultiplier < 1 ? cart.subtotal * (1 - safeMultiplier) : 0;
  const demoTotal = Math.max(0, cart.total - incentiveAmount);

  return (
    <section className="page">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Cart</p>
          <h1>Your shopping cart</h1>
        </div>
        <button className="secondary-button" onClick={clear} disabled={cart.items.length === 0}>
          Clear cart
        </button>
      </div>

      {cart.items.length === 0 ? (
        <div className="empty-state">
          <h2>Your cart is empty</h2>
          <Link className="secondary-button" to="/products">
            Browse products
          </Link>
        </div>
      ) : (
        <div className="cart-layout">
          <div className="cart-items">
            {cart.items.map((item) => (
              <div className="cart-row" key={item.product.id}>
                <img src={item.product.image} alt={item.product.name} />
                <div>
                  <h3>{item.product.name}</h3>
                  <p className="muted">{item.product.brand}</p>
                  <button className="text-action" onClick={() => remove(item.product.id)}>
                    Remove
                  </button>
                </div>
                <input
                  type="number"
                  min={1}
                  max={item.product.stock}
                  value={item.quantity}
                  onChange={(event) => changeQuantity(item.product.id, Number(event.target.value))}
                />
                <strong>${item.lineTotal.toFixed(2)}</strong>
              </div>
            ))}
          </div>

          <aside className="summary-panel">
            <h2>Order summary</h2>
            <div className="summary-line">
              <span>Subtotal</span>
              <strong>${cart.subtotal.toFixed(2)}</strong>
            </div>
            <div className="summary-line">
              <span>Shipping</span>
              <strong>{cart.shipping === 0 ? "Free" : `$${cart.shipping.toFixed(2)}`}</strong>
            </div>
            {incentiveAmount > 0 ? (
              <div className="summary-line incentive">
                <span>Demo AGI incentive</span>
                <strong>-${incentiveAmount.toFixed(2)}</strong>
              </div>
            ) : null}
            <div className="summary-line total">
              <span>Total</span>
              <strong>${demoTotal.toFixed(2)}</strong>
            </div>
            <div className="coupon-row">
              <input
                placeholder="Try coupon SAVE10"
                value={coupon}
                onChange={(event) => setCoupon(event.target.value)}
              />
              <button className="secondary-button" onClick={attemptCoupon}>
                Apply
              </button>
            </div>
            {couponMessage ? <p className="muted">{couponMessage}</p> : null}
            <button onClick={checkout}>Start checkout</button>
          </aside>
        </div>
      )}
    </section>
  );
}
