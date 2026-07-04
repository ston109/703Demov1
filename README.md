# 703DEMOV1: AGI Cart Abandonment Agent Demo

## Overview

703DEMOV1 is a runnable course demo of a Compound AI System / autonomous agent for e-commerce cart abandonment recovery. It is not a chatbot. The system observes user behavior in a simulated online shopping website, builds an internal world model, estimates abandonment risk, selects safe interventions, executes non-blocking website actions, collects feedback, and updates evaluation/evolution records.

The business goal is to reduce cart abandonment and improve checkout conversion while controlling token cost, respecting user safety, and avoiding annoying interventions.

## Course Requirement Alignment

| Requirement | Current Status |
| --- | --- |
| Real runnable or simulated AI system | Implemented with shopping frontend, shopping backend, AGI backend, SQLite persistence, and AGI Monitor. |
| Not a normal chatbot | Implemented as a structured agent system with world model, belief state, memory, planner, tools, safety guard, feedback, evaluation, and evolution. |
| Receives external input | Receives login, product, cart, checkout, product-section, similar-product, coupon, dwell, and page-exit events. |
| Automatically diagnoses problems | Infers shipping concern, product uncertainty, price sensitivity, trust concern, checkout friction, and comparison hesitation. |
| Selects action | Planner chooses tools such as shipping info, review summary, support highlight, demo incentive, or related recommendations. |
| Executes action in a system | Frontend action runtime executes safe, non-blocking UI actions in the shopping website. |
| Commercial value | Targets lower abandonment, higher conversion, reduced support burden, and better recovery of high-intent shoppers. |
| Token/cost awareness | Gemini is only used as a bounded low-score risk multiplier helper; AGI planning does not depend on LLM calls. |
| Safety and reliability | Includes safety guard, frontend allowlist, discount cap, no auto-purchase, no payment collection, no email/SMS, cart/account isolation, fallback logic, and error logs. |
| Edge cases | Handles anonymous users, empty carts, clear cart, partial checkout, full checkout, repeated popups, duplicate actions, multi-device sessions, and AGI unavailable states. |

The code demo satisfies the technical demo expectations. Final assignment compliance still depends on the written PDF report following the required format, page limit, references, appendix, and checklist.

## Teacher Requirement Summary

The final assignment asks for a final report and a 3-minute demo video. The demo should be a road-show or product-launch style pitch, not a long technical walkthrough.

The system should demonstrate:

- Agentic autonomy beyond a simple chat interface.
- Generalization through external inputs, tool use, planning, and multi-step reasoning.
- A profit or cost-saving logic.
- Trust, robustness, and safety evaluation.
- A commercial stress test such as token cost or execution cost.
- Clear reproducibility and an attractive road-show demo.

## System Architecture

```text
Online Shopping Web
  -> user behavior events
  -> shopping backend cart/session gateway
  -> AGI backend
  -> risk engine signal
  -> world model
  -> belief state
  -> memory retrieval
  -> goal manager
  -> reasoning module
  -> planner
  -> tool registry
  -> safety guard
  -> action executor
  -> frontend web actions
  -> feedback
  -> evaluation logger
  -> evolution engine
```

The LLM is not the AGI brain. Gemini, if configured, is only used for risk multiplier estimation when the risk score is already low. If Gemini is unavailable or returns invalid data, the system falls back to deterministic scoring.

## Main Components

- `online_shopping_web/frontend`: React shopping website with product pages, cart, checkout, action runtime, and tracking.
- `online_shopping_web/backend`: Flask shopping backend with local registration/login, account-isolated carts, product APIs, checkout, and AGI event proxy.
- `agi`: Flask AGI backend with risk scoring, AGI Monitor, world model, memory, planning, safety, action execution, feedback, evaluation, and evolution.
- SQLite databases:
  - `online_shopping_web/backend/shop_data.sqlite`
  - `agi/agi_data.sqlite`

## Run Instructions

Open three PowerShell windows.

### 1. Start AGI backend

```powershell
cd C:\Users\21956\Desktop\703DemoV1\agi
python app.py
```

AGI Monitor:

```text
http://127.0.0.1:8001
```

Optional Gemini config:

1. Copy `agi/llm_config.example.json` to `agi/llm_config.local.json`.
2. Put your Gemini API key in `GEMINI_API_KEY`.
3. Start the AGI backend normally with `python app.py`.

The local config is read only by the AGI backend process. It is not sent to the frontend, shopping backend, or SQLite database. Existing system environment variables take priority over the local file.

Example:

```json
{
  "AGI_LLM_PROVIDER": "gemini",
  "GEMINI_API_KEY": "YOUR_GEMINI_API_KEY_HERE",
  "AGI_GEMINI_MODEL": "gemini-3.5-flash",
  "AGI_LLM_TIMEOUT_SECONDS": "8",
  "AGI_LLM_MAX_OUTPUT_TOKENS": "10"
}
```

### 2. Start shopping backend

```powershell
cd C:\Users\21956\Desktop\703DemoV1\online_shopping_web\backend
python app.py
```

Shopping backend:

```text
http://127.0.0.1:5000
```

### 3. Start frontend

```powershell
cd C:\Users\21956\Desktop\703DemoV1\online_shopping_web\frontend
npm.cmd run dev
```

Shopping website:

```text
http://127.0.0.1:5173
```

## Demo Scenario

1. Register a new account and log in.
2. Open product `p001`.
3. Add the product to cart.
4. Visit the cart page.
5. Leave the cart page. This starts risk scoring from 100.
6. Browse similar or cheaper products such as `p002` and `p003`.
7. Visit product info, shipping, reviews, merchant, or warranty pages.
8. Watch the AGI Monitor update world state, risk state, events, actions, feedback, and evaluation.
9. When risk score is at or below 80, safe web actions may appear in the shopping site:
   - support highlight
   - demo cart incentive capped at 5% off
   - shipping or review banner
   - related product recommendation strip
10. Complete checkout or partial checkout and observe score reset/end behavior.

## Commercial Value

Cart abandonment is a direct revenue-loss problem. A shopper who adds an item to cart and then hesitates is high intent, but may be blocked by shipping cost, product uncertainty, trust, price sensitivity, or checkout friction.

This system creates value by:

- Detecting high-risk cart behavior earlier.
- Selecting targeted, low-annoyance interventions.
- Reducing unnecessary human support work.
- Recovering carts with safe incentives and information.
- Producing evaluation metrics for tool success and user annoyance.

Example business framing: if a store recovers even a small percentage of abandoned high-intent carts, the recovered revenue can exceed the low compute and token cost of the agent.

## Token and Cost Strategy

The system avoids expensive prompt-everything design.

- AGI planning and action selection are deterministic/state-based.
- World state, belief state, memory, safety, and tool execution are maintained by the system itself.
- Gemini is optional and only used for low-score risk multiplier estimation.
- Gemini output is capped with `AGI_LLM_MAX_OUTPUT_TOKENS` and defaults to `10`.
- If Gemini is unavailable, missing, slow, or invalid, scoring immediately falls back to default deterministic logic.
- Late valid Gemini scoring results can correct the matching cart-scoped score event, but Gemini still cannot choose website actions.
- Frontend and SQLite never store the Gemini API key.

This keeps token usage bounded and prevents the LLM from becoming the whole agent.

## Safety, Reliability, and Edge Cases

Safety controls include:

- No auto-purchase.
- No real price modification.
- Demo incentive is capped at 5% off and does not change catalog price.
- No collection or storage of payment data.
- No email, SMS, or external support messages.
- Safety Guard checks plans and payloads.
- Frontend action runtime uses an allowlist before showing actions.
- Repeated popups are throttled by score threshold, cooldown, and duplicate-content filtering.

Reliability and edge-case handling include:

- Anonymous users do not create scoring sessions.
- Empty carts do not trigger scoring.
- Risk starts only after leaving cart with items.
- Clear cart pauses scoring and resets score to 100.
- Full checkout ends the scoring scope.
- Partial checkout resets remaining cart scoring to 100.
- Account carts are isolated.
- Multi-device sessions include `deviceId`.
- AGI unavailable responses do not break the shopping website.
- Error logs and action feedback are visible in AGI Monitor.

## Manual Testing Checklist

- Register/login works and old demo users do not persist after backend restart.
- Cart is account-isolated.
- Browsing without cart does not trigger scoring.
- Entering cart keeps score at 100.
- Leaving cart with items starts risk scoring.
- Similar/cheaper product browsing affects cart risk only when related to cart products.
- Score above 80 does not show visible action cards.
- Score at or below 80 allows safe action cards.
- Duplicate action content does not repeat within the cooldown window.
- Contact support opens an on-site panel only.
- Demo incentive is capped at 5% and only affects cart summary.
- AGI Monitor shows sessions, actions, feedback, evaluation, and error logs.

## Demo Readiness Conclusion

The code demo is ready to support the 3-minute road-show video requirement. It clearly demonstrates a compound autonomous agent that observes external input, diagnoses e-commerce risk, chooses and executes safe actions, tracks feedback, controls token cost, and handles commercial edge cases.
