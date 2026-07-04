import { useEffect, useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { fetchMe } from "./api";
import { AgiActionRuntime } from "./components/AgiActionRuntime";
import { sendAgiBeacon, sendAgiEvent } from "./tracking/agiClient";

export default function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const [userId, setUserId] = useState(() => localStorage.getItem("demoUserId"));
  const [supportHighlighted, setSupportHighlighted] = useState(false);
  const [supportOpen, setSupportOpen] = useState(false);

  function clearLocalUser() {
    localStorage.removeItem("demoUserId");
    localStorage.removeItem("demoUserName");
    localStorage.removeItem("demoSessionId");
    localStorage.removeItem("demoCartIncentiveMultiplier");
    setUserId(null);
    window.dispatchEvent(new Event("demo-auth-changed"));
  }

  function logout() {
    sendAgiEvent({ type: "logout", pageType: "app_shell" });
    sendAgiBeacon({ type: "session_end", pageType: "app_shell" });
    clearLocalUser();
    navigate("/login");
  }

  useEffect(() => {
    if (!userId) return;
    fetchMe()
      .then((response) => {
        localStorage.setItem("demoUserId", response.user.id);
        localStorage.setItem("demoUserName", response.user.name);
        setUserId(response.user.id);
      })
      .catch(() => {
        clearLocalUser();
      });
  }, [userId]);

  useEffect(() => {
    function syncAuth() {
      setUserId(localStorage.getItem("demoUserId"));
    }

    window.addEventListener("demo-auth-changed", syncAuth);
    window.addEventListener("storage", syncAuth);
    return () => {
      window.removeEventListener("demo-auth-changed", syncAuth);
      window.removeEventListener("storage", syncAuth);
    };
  }, []);

  useEffect(() => {
    function handleUnload() {
      if (localStorage.getItem("demoUserId")) {
        sendAgiBeacon({ type: "session_end", pageType: pageTypeFromPath(location.pathname), url: location.pathname });
      }
    }

    window.addEventListener("beforeunload", handleUnload);
    return () => window.removeEventListener("beforeunload", handleUnload);
  }, [location.pathname]);

  useEffect(() => {
    function highlightSupport() {
      setSupportHighlighted(true);
    }
    function openSupport() {
      setSupportOpen(true);
      setSupportHighlighted(false);
    }

    window.addEventListener("agi-support-highlight", highlightSupport);
    window.addEventListener("agi-open-support", openSupport as EventListener);
    return () => {
      window.removeEventListener("agi-support-highlight", highlightSupport);
      window.removeEventListener("agi-open-support", openSupport as EventListener);
    };
  }, []);

  return (
    <div className="app-shell">
      <header className="topbar">
        <Link className="brand" to="/products">
          MockMart
        </Link>
        <nav>
          <Link to="/products">Products</Link>
          <Link to="/cart">Cart</Link>
          {userId ? (
            <>
              <button
                className={`link-button support-link ${supportHighlighted ? "attention" : ""}`}
                onClick={() => {
                  setSupportOpen(true);
                  setSupportHighlighted(false);
                }}
              >
                Contact support
              </button>
              <button className="link-button" onClick={logout}>
                Logout
              </button>
            </>
          ) : (
            <Link to="/login">Login</Link>
          )}
        </nav>
      </header>
      <main>
        <Outlet />
      </main>
      {supportOpen ? <SupportPanel onClose={() => setSupportOpen(false)} /> : null}
      <AgiActionRuntime />
    </div>
  );
}

function SupportPanel({ onClose }: { onClose: () => void }) {
  return (
    <aside className="support-panel">
      <button className="agi-runtime-close" onClick={onClose}>
        Close
      </button>
      <h2>MockMart support</h2>
      <p>
        This is an on-site demo support panel. It can help with shipping, returns, checkout confidence,
        and product comparison without sending email or external messages.
      </p>
      <div className="support-grid">
        <span>Shipping cost is shown in cart before checkout.</span>
        <span>Demo checkout does not process real payment.</span>
        <span>Reviews, warranty, and merchant details are available on product pages.</span>
      </div>
    </aside>
  );
}

function pageTypeFromPath(pathname: string) {
  if (pathname === "/cart") return "cart";
  if (pathname === "/checkout") return "checkout";
  if (pathname.includes("/shipping")) return "product_shipping";
  if (pathname.includes("/reviews")) return "product_reviews";
  if (pathname.includes("/warranty")) return "product_warranty";
  if (pathname.includes("/info")) return "product_info";
  if (pathname.includes("/merchant")) return "product_merchant";
  if (pathname.startsWith("/products/")) return "product_detail";
  if (pathname.startsWith("/products")) return "product_list";
  return "app_shell";
}
