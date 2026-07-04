import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { completeCheckout, fetchCart } from "../api";
import { getLatestAgiDecision, sendAgiEvent, sendAgiFeedback, startNewAgiSession } from "../tracking/agiClient";
import { usePageTracking } from "../tracking/usePageTracking";
import type { Cart } from "../types";

export function CheckoutPage() {
  usePageTracking("checkout");
  const navigate = useNavigate();
  const [cart, setCart] = useState<Cart | null>(null);
  const [selectedProductIds, setSelectedProductIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchCart()
      .then((nextCart) => {
        setCart(nextCart);
        setSelectedProductIds(nextCart.items.map((item) => item.product.id));
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Please log in first."));
  }, []);

  async function complete(event: FormEvent) {
    event.preventDefault();
    if (selectedProductIds.length === 0) {
      setError("Select at least one item to complete checkout.");
      return;
    }
    setBusy(true);
    const response = await completeCheckout(selectedProductIds);
    const remainingCartProductIds = response.remainingCart.items.map((item) => item.product.id);
    await sendAgiEvent({
      type: "order_complete",
      pageType: "checkout",
      cart: response.order,
      metadata: {
        orderId: response.orderId,
        completedProductIds: response.completedProductIds,
        remainingCartProductIds,
        cartCleared: response.cartCleared,
        partialOrder: !response.cartCleared,
      },
    });
    void sendAgiFeedback("purchase_completed", getLatestAgiDecision());
    localStorage.removeItem("demoCartIncentiveMultiplier");
    if (response.cartCleared) {
      startNewAgiSession();
    }
    navigate("/order-success", { state: { orderId: response.orderId } });
  }

  async function exitCheckout() {
    await sendAgiEvent({ type: "checkout_exit", pageType: "checkout", cart: cart || undefined });
    navigate("/cart");
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

  if (!cart) return <section className="page">Loading checkout...</section>;

  if (cart.items.length === 0) {
    return (
      <section className="page empty-state">
        <h1>No items ready for checkout</h1>
        <Link className="secondary-button" to="/products">
          Return to products
        </Link>
      </section>
    );
  }

  function toggleProduct(productId: string) {
    setSelectedProductIds((current) =>
      current.includes(productId)
        ? current.filter((item) => item !== productId)
        : [...current, productId],
    );
  }

  return (
    <section className="page">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Checkout simulation</p>
          <h1>Shipping and payment</h1>
        </div>
        <button className="secondary-button" onClick={exitCheckout}>
          Exit checkout
        </button>
      </div>

      <form className="checkout-layout" onSubmit={complete}>
        <div className="checkout-form">
          <h2>Items in this order</h2>
          <div className="checkout-items">
            {cart.items.map((item) => (
              <label className="checkout-item-row" key={item.product.id}>
                <input
                  type="checkbox"
                  checked={selectedProductIds.includes(item.product.id)}
                  onChange={() => toggleProduct(item.product.id)}
                />
                <img src={item.product.image} alt={item.product.name} />
                <span>{item.product.name}</span>
                <strong>${item.lineTotal.toFixed(2)}</strong>
              </label>
            ))}
          </div>
          <h2>Shipping details</h2>
          <label>
            Full name
            <input defaultValue="Demo Shopper" />
          </label>
          <label>
            Address
            <input defaultValue="42 Demo Street" />
          </label>
          <label>
            Delivery method
            <select defaultValue="standard">
              <option value="standard">Standard delivery</option>
              <option value="express">Express delivery</option>
            </select>
          </label>
          <h2>Payment</h2>
          <label>
            Card number
            <input defaultValue="4242 4242 4242 4242" />
          </label>
          <label>
            Expiry
            <input defaultValue="12/28" />
          </label>
        </div>

        <aside className="summary-panel">
          <h2>Final total</h2>
          <div className="summary-line">
            <span>Subtotal</span>
            <strong>${cart.subtotal.toFixed(2)}</strong>
          </div>
          <div className="summary-line">
            <span>Shipping</span>
            <strong>{cart.shipping === 0 ? "Free" : `$${cart.shipping.toFixed(2)}`}</strong>
          </div>
          <div className="summary-line total">
            <span>Total</span>
            <strong>${cart.total.toFixed(2)}</strong>
          </div>
          <button disabled={busy}>{busy ? "Placing order..." : "Complete order"}</button>
        </aside>
      </form>
    </section>
  );
}
