import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import App from "./App";
import { CartPage } from "./pages/CartPage";
import { CheckoutPage } from "./pages/CheckoutPage";
import { LoginPage } from "./pages/LoginPage";
import { OrderSuccessPage } from "./pages/OrderSuccessPage";
import { ProductDetailPage } from "./pages/ProductDetailPage";
import { ProductListPage } from "./pages/ProductListPage";
import { ProductSectionPage } from "./pages/ProductSectionPage";
import "./styles/main.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<App />}>
          <Route index element={<Navigate to="/products" replace />} />
          <Route path="login" element={<LoginPage />} />
          <Route path="products" element={<ProductListPage />} />
          <Route path="products/:productId" element={<ProductDetailPage />} />
          <Route path="products/:productId/info" element={<ProductSectionPage section="info" />} />
          <Route path="products/:productId/shipping" element={<ProductSectionPage section="shipping" />} />
          <Route path="products/:productId/merchant" element={<ProductSectionPage section="merchant" />} />
          <Route path="products/:productId/reviews" element={<ProductSectionPage section="reviews" />} />
          <Route path="products/:productId/warranty" element={<ProductSectionPage section="warranty" />} />
          <Route path="cart" element={<CartPage />} />
          <Route path="checkout" element={<CheckoutPage />} />
          <Route path="order-success" element={<OrderSuccessPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
