import type {
  Cart,
  Product,
  ProductDetailResponse,
  ProductInfo,
  ProductMerchant,
  ProductReviews,
  ProductShipping,
  ProductWarranty,
  User,
} from "./types";

const API_BASE = "http://127.0.0.1:5000";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const user = localStorage.getItem("demoUserId");
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (user) {
    headers["X-Demo-User"] = user;
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.message || (response.status === 401 ? "Please log in first." : `Request failed: ${response.status}`));
  }

  return response.json();
}

export async function register(username: string, password: string, name: string) {
  return request<{ user: User }>("/api/register", {
    method: "POST",
    body: JSON.stringify({ username, password, name }),
  });
}

export async function login(username: string, password: string) {
  return request<{ user: User }>("/api/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export async function fetchMe() {
  return request<{ user: User }>("/api/me");
}

export async function fetchProducts(params: { search?: string; category?: string; sort?: string }) {
  const query = new URLSearchParams();
  if (params.search) query.set("search", params.search);
  if (params.category && params.category !== "All") query.set("category", params.category);
  if (params.sort) query.set("sort", params.sort);
  return request<{ products: Product[] }>(`/api/products?${query.toString()}`);
}

export async function fetchCategories() {
  return request<{ categories: string[] }>("/api/categories");
}

export async function fetchProduct(productId: string) {
  return request<ProductDetailResponse>(`/api/products/${productId}`);
}

export async function fetchProductInfo(productId: string) {
  return request<{ product: Product; info: ProductInfo }>(`/api/products/${productId}/info`);
}

export async function fetchProductShipping(productId: string) {
  return request<{ product: Product; shipping: ProductShipping }>(`/api/products/${productId}/shipping`);
}

export async function fetchProductMerchant(productId: string) {
  return request<{ product: Product; merchant: ProductMerchant }>(`/api/products/${productId}/merchant`);
}

export async function fetchProductReviews(productId: string) {
  return request<{ product: Product; reviews: ProductReviews }>(`/api/products/${productId}/reviews`);
}

export async function fetchProductWarranty(productId: string) {
  return request<{ product: Product; warranty: ProductWarranty }>(`/api/products/${productId}/warranty`);
}

export async function fetchCart() {
  return request<Cart>("/api/cart");
}

export async function addToCart(productId: string, quantity = 1) {
  return request<Cart>("/api/cart/add", {
    method: "POST",
    body: JSON.stringify({ productId, quantity }),
  });
}

export async function updateCart(productId: string, quantity: number) {
  return request<Cart>("/api/cart/update", {
    method: "POST",
    body: JSON.stringify({ productId, quantity }),
  });
}

export async function removeFromCart(productId: string) {
  return request<Cart>("/api/cart/remove", {
    method: "POST",
    body: JSON.stringify({ productId }),
  });
}

export async function clearCart() {
  return request<Cart>("/api/cart/clear", { method: "POST" });
}

export async function startCheckout() {
  return request<{ checkoutId: string; cart: Cart }>("/api/checkout/start", { method: "POST" });
}

export async function completeCheckout(productIds: string[]) {
  return request<{
    orderId: string;
    completedProductIds: string[];
    order: Cart;
    remainingCart: Cart;
    cartCleared: boolean;
  }>("/api/checkout/complete", {
    method: "POST",
    body: JSON.stringify({ productIds }),
  });
}
