import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import { sendAgiEvent } from "./agiClient";
import type { Cart } from "../types";

type PageTrackingOptions = {
  getCart?: () => Cart | null;
};

export function usePageTracking(pageType: string, options: PageTrackingOptions = {}) {
  const location = useLocation();
  const startedAt = useRef(Date.now());
  const optionsRef = useRef(options);

  optionsRef.current = options;

  useEffect(() => {
    startedAt.current = Date.now();
    sendAgiEvent({ type: "page_view", pageType, url: location.pathname });

    const dwellTimer = window.setInterval(() => {
      sendAgiEvent({
        type: "dwell_update",
        pageType,
        url: location.pathname,
        durationMs: Date.now() - startedAt.current,
      });
    }, 10000);

    return () => {
      window.clearInterval(dwellTimer);
      sendAgiEvent({
        type: "page_exit",
        pageType,
        url: location.pathname,
        durationMs: Date.now() - startedAt.current,
        cart: optionsRef.current.getCart?.() || undefined,
      });
    };
  }, [location.pathname, pageType]);
}
