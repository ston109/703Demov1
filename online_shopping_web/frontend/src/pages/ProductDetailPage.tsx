import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { addToCart, fetchProduct } from "../api";
import { ProductCard } from "../components/ProductCard";
import { ProductSectionNav } from "../components/ProductSectionNav";
import { sendAgiEvent } from "../tracking/agiClient";
import { usePageTracking } from "../tracking/usePageTracking";
import type { Product } from "../types";

export function ProductDetailPage() {
  usePageTracking("product_detail");
  const { productId = "" } = useParams();
  const navigate = useNavigate();
  const [product, setProduct] = useState<Product | null>(null);
  const [similar, setSimilar] = useState<Product[]>([]);
  const [cheaper, setCheaper] = useState<Product[]>([]);
  const [status, setStatus] = useState("");

  useEffect(() => {
    fetchProduct(productId).then((response) => {
      setProduct(response.product);
      setSimilar(response.similarProducts);
      setCheaper(response.cheaperAlternatives);
      sendAgiEvent({
        type: "product_view",
        pageType: "product_detail",
        product: response.product,
      });
    });
  }, [productId]);

  async function handleAddToCart() {
    if (!product) return;
    const cart = await addToCart(product.id, 1);
    setStatus("Added to cart");
    sendAgiEvent({
      type: "add_to_cart",
      pageType: "product_detail",
      product,
      cart,
    });
  }

  if (!product) {
    return <section className="page">Loading product...</section>;
  }

  const discount = Math.round(((product.originalPrice - product.price) / product.originalPrice) * 100);

  return (
    <section className="page">
      <button className="text-action" onClick={() => navigate(-1)}>
        Back
      </button>
      <ProductSectionNav productId={product.id} />
      <div className="detail-layout">
        <div className="detail-image">
          <img src={product.image} alt={product.name} />
        </div>
        <div className="detail-info">
          <p className="eyebrow">
            {product.brand} / {product.category}
          </p>
          <h1>{product.name}</h1>
          <p className="detail-description">{product.description}</p>
          <div className="detail-price">
            <strong>${product.price.toFixed(2)}</strong>
            <span>${product.originalPrice.toFixed(2)}</span>
            <em>{discount}% off</em>
          </div>
          <div className="detail-meta">
            <span>Rating {product.rating.toFixed(1)} / 5</span>
            <span>{product.stock} left in stock</span>
            <span>{product.cheaperAlternativeIds.length} cheaper alternatives</span>
          </div>
          <ul className="feature-list">
            {product.features.map((feature) => (
              <li key={feature}>{feature}</li>
            ))}
          </ul>
          <div className="action-row">
            <button onClick={handleAddToCart}>Add to cart</button>
            <Link className="secondary-button" to="/cart">
              View cart
            </Link>
          </div>
          {status ? <p className="success">{status}</p> : null}
        </div>
      </div>

      {cheaper.length > 0 ? (
        <section className="recommendation-section">
          <h2>Cheaper alternatives</h2>
          <div className="product-grid compact">
            {cheaper.map((item) => (
              <ProductCard
                key={item.id}
                product={item}
                label="Lower price"
                onClick={() =>
                  sendAgiEvent({
                    type: "cheaper_alternative_view",
                    pageType: "product_detail",
                    product: item,
                    targetUrl: `/products/${item.id}`,
                    targetPageType: "product_detail",
                  })
                }
              />
            ))}
          </div>
        </section>
      ) : null}

      {similar.length > 0 ? (
        <section className="recommendation-section">
          <h2>Similar products</h2>
          <div className="product-grid compact">
            {similar.map((item) => (
              <ProductCard
                key={item.id}
                product={item}
                label="Similar"
                onClick={() =>
                  sendAgiEvent({
                    type: "similar_product_view",
                    pageType: "product_detail",
                    product: item,
                    targetUrl: `/products/${item.id}`,
                    targetPageType: "product_detail",
                  })
                }
              />
            ))}
          </div>
        </section>
      ) : null}
    </section>
  );
}
