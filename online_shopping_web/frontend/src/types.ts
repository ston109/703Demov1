export type Product = {
  id: string;
  name: string;
  category: string;
  brand: string;
  price: number;
  originalPrice: number;
  stock: number;
  rating: number;
  image: string;
  description: string;
  features: string[];
  similarProductIds: string[];
  cheaperAlternativeIds: string[];
};

export type User = {
  id: string;
  username: string;
  name: string;
};

export type CartItem = {
  product: Product;
  quantity: number;
  lineTotal: number;
};

export type Cart = {
  items: CartItem[];
  subtotal: number;
  shipping: number;
  total: number;
};

export type AgiWebAction = {
  action_id: string;
  decision_id?: number;
  session_id?: string;
  source: string;
  action_type: string;
  tool_name: string;
  message: string;
  target_page: string;
  priority: "low" | "medium" | "high" | string;
  discountMultiplier?: number;
  demoIncentive?: boolean;
  externalContact?: boolean;
  products?: Array<{
    id: string;
    name: string;
    price: number;
    originalPrice: number;
    rating: number;
    image: string;
  }>;
};

export type ProductDetailResponse = {
  product: Product;
  similarProducts: Product[];
  cheaperAlternatives: Product[];
};

export type ProductInfo = {
  productId: string;
  title: string;
  specifications: Array<{ label: string; value: string }>;
  packageContents: string[];
  bestFor: string[];
  careNotes: string[];
};

export type ProductShipping = {
  productId: string;
  title: string;
  shipsFrom: string;
  freeShippingThreshold: number;
  standard: { name: string; eta: string; cost: number };
  express: { name: string; eta: string; cost: number };
  handlingTime: string;
  limitations: string[];
};

export type ProductMerchant = {
  productId: string;
  merchantName: string;
  verified: boolean;
  merchantRating: number;
  responseTime: string;
  dispatchReliability: string;
  sellerSince: string;
  servicePromises: string[];
};

export type ProductReviews = {
  productId: string;
  averageRating: number;
  totalReviews: number;
  ratingBreakdown: Record<string, number>;
  highlights: string[];
  reviews: Array<{ author: string; rating: number; title: string; body: string }>;
};

export type ProductWarranty = {
  productId: string;
  title: string;
  returnWindow: string;
  warrantyPeriod: string;
  supportFlow: string[];
  exceptions: string[];
};

export type AgiWorldState = {
  session_id: string;
  current_page: string;
  current_stage: string;
  inferred_user_intent: string;
  possible_blockers: Array<{ type: string; probability: number; evidence: string[] }>;
  predicted_next_action: { action: string; probability: number };
  uncertainty: number;
};

export type AgiBeliefState = {
  session_id: string;
  stage_belief: Record<string, number>;
  intent_belief: Record<string, number>;
  blocker_belief: Record<string, number>;
  abandonment_risk: number;
  confidence: number;
};

export type AgiDecision = {
  decision_id?: number;
  session_id: string;
  world_state: AgiWorldState;
  belief_state: AgiBeliefState;
  reasoning: {
    situation_summary: string;
    main_hypothesis: string;
    recommended_planning_direction: string;
    used_fallback?: boolean;
    llm?: {
      provider: string;
      model: string;
      status: string;
      latency_ms: number;
    };
    llm_input_summary?: { redaction_applied?: boolean };
  };
  plan: {
    plan_id: string;
    target_blocker: string;
    tool_required: string;
    expected_effect: string;
    confidence?: number;
    score?: number;
  };
  action: {
    tool_name: string;
    payload: {
      action_type: string;
      tool_name: string;
      message: string;
      target_page: string;
      priority: string;
    };
    status: string;
  };
  safety: {
    allowed: boolean;
    status: string;
    reason: string;
  };
};
