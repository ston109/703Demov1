import { Link, useLocation } from "react-router-dom";
import { usePageTracking } from "../tracking/usePageTracking";

export function OrderSuccessPage() {
  usePageTracking("order_success");
  const location = useLocation();
  const orderId = (location.state as { orderId?: string } | null)?.orderId || "ORD-DEMO-1001";

  return (
    <section className="page success-page">
      <p className="eyebrow">Order complete</p>
      <h1>Thanks, your order is confirmed.</h1>
      <p>Order ID: {orderId}</p>
      <Link className="secondary-button" to="/products">
        Continue shopping
      </Link>
    </section>
  );
}
