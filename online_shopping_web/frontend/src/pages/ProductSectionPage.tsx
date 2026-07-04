import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  fetchProductInfo,
  fetchProductMerchant,
  fetchProductReviews,
  fetchProductShipping,
  fetchProductWarranty,
} from "../api";
import { ProductSectionNav } from "../components/ProductSectionNav";
import { sendAgiEvent } from "../tracking/agiClient";
import { usePageTracking } from "../tracking/usePageTracking";
import type {
  Product,
  ProductInfo,
  ProductMerchant,
  ProductReviews,
  ProductShipping,
  ProductWarranty,
} from "../types";

type Section = "info" | "shipping" | "merchant" | "reviews" | "warranty";

type SectionData = ProductInfo | ProductShipping | ProductMerchant | ProductReviews | ProductWarranty;

const config: Record<
  Section,
  {
    pageType: string;
    eventType: "product_info_view" | "shipping_info_view" | "merchant_info_view" | "review_view" | "warranty_view";
    endpoint: string;
    fetcher: (productId: string) => Promise<Record<string, unknown>>;
  }
> = {
  info: {
    pageType: "product_info",
    eventType: "product_info_view",
    endpoint: "info",
    fetcher: fetchProductInfo as (productId: string) => Promise<Record<string, unknown>>,
  },
  shipping: {
    pageType: "product_shipping",
    eventType: "shipping_info_view",
    endpoint: "shipping",
    fetcher: fetchProductShipping as (productId: string) => Promise<Record<string, unknown>>,
  },
  merchant: {
    pageType: "product_merchant",
    eventType: "merchant_info_view",
    endpoint: "merchant",
    fetcher: fetchProductMerchant as (productId: string) => Promise<Record<string, unknown>>,
  },
  reviews: {
    pageType: "product_reviews",
    eventType: "review_view",
    endpoint: "reviews",
    fetcher: fetchProductReviews as (productId: string) => Promise<Record<string, unknown>>,
  },
  warranty: {
    pageType: "product_warranty",
    eventType: "warranty_view",
    endpoint: "warranty",
    fetcher: fetchProductWarranty as (productId: string) => Promise<Record<string, unknown>>,
  },
};

export function ProductSectionPage({ section }: { section: Section }) {
  const { productId = "" } = useParams();
  const current = config[section];
  usePageTracking(current.pageType);
  const [product, setProduct] = useState<Product | null>(null);
  const [data, setData] = useState<SectionData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    current
      .fetcher(productId)
      .then((response) => {
        setProduct(response.product as Product);
        setData(response[section] as SectionData);
        sendAgiEvent({
          type: current.eventType,
          pageType: current.pageType,
          product: response.product as Product,
          metadata: {
            productId,
            section,
            requestEndpoint: `/api/products/${productId}/${current.endpoint}`,
          },
        });
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Product section failed to load."));
  }, [current, productId, section]);

  if (error) {
    return (
      <section className="page empty-state">
        <h1>{error}</h1>
        <Link className="secondary-button" to="/products">
          Back to products
        </Link>
      </section>
    );
  }

  if (!product || !data) {
    return <section className="page">Loading product {section}...</section>;
  }

  return (
    <section className="page">
      <div className="section-heading">
        <div>
          <p className="eyebrow">{product.brand} / {product.category}</p>
          <h1>{product.name}</h1>
        </div>
        <Link className="secondary-button" to={`/products/${product.id}`}>
          Overview
        </Link>
      </div>
      <ProductSectionNav productId={product.id} />
      {renderSection(section, data)}
    </section>
  );
}

function renderSection(section: Section, data: SectionData) {
  if (section === "info") {
    const info = data as ProductInfo;
    return (
      <div className="section-card-grid">
        <article className="detail-panel wide">
          <h2>{info.title}</h2>
          <div className="spec-table">
            {info.specifications.map((item) => (
              <div key={item.label}>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
              </div>
            ))}
          </div>
        </article>
        <InfoList title="Package contents" items={info.packageContents} />
        <InfoList title="Best for" items={info.bestFor} />
        <InfoList title="Care notes" items={info.careNotes} />
      </div>
    );
  }

  if (section === "shipping") {
    const shipping = data as ProductShipping;
    return (
      <div className="section-card-grid">
        <article className="detail-panel wide">
          <h2>{shipping.title}</h2>
          <p className="muted">Ships from {shipping.shipsFrom}</p>
          <div className="shipping-options">
            <div>
              <strong>{shipping.standard.name}</strong>
              <span>{shipping.standard.eta}</span>
              <em>${shipping.standard.cost.toFixed(2)}</em>
            </div>
            <div>
              <strong>{shipping.express.name}</strong>
              <span>{shipping.express.eta}</span>
              <em>${shipping.express.cost.toFixed(2)}</em>
            </div>
          </div>
          <p>Free shipping applies from ${shipping.freeShippingThreshold} cart subtotal.</p>
          <p>{shipping.handlingTime}</p>
        </article>
        <InfoList title="Delivery limitations" items={shipping.limitations} />
      </div>
    );
  }

  if (section === "merchant") {
    const merchant = data as ProductMerchant;
    return (
      <div className="section-card-grid">
        <article className="detail-panel wide">
          <h2>{merchant.merchantName}</h2>
          <div className="metric-row">
            <span>Verified {merchant.verified ? "Yes" : "No"}</span>
            <span>Rating {merchant.merchantRating}/5</span>
            <span>Seller since {merchant.sellerSince}</span>
          </div>
          <p>{merchant.responseTime}</p>
          <p>{merchant.dispatchReliability}</p>
        </article>
        <InfoList title="Service promises" items={merchant.servicePromises} />
      </div>
    );
  }

  if (section === "reviews") {
    const reviews = data as ProductReviews;
    return (
      <div className="section-card-grid">
        <article className="detail-panel wide">
          <h2>Customer reviews</h2>
          <div className="metric-row">
            <span>{reviews.averageRating}/5 average</span>
            <span>{reviews.totalReviews} reviews</span>
          </div>
          <InfoList title="Highlights" items={reviews.highlights} />
        </article>
        {reviews.reviews.map((review) => (
          <article className="detail-panel" key={`${review.author}-${review.title}`}>
            <p className="eyebrow">{review.rating}/5 / {review.author}</p>
            <h3>{review.title}</h3>
            <p>{review.body}</p>
          </article>
        ))}
      </div>
    );
  }

  const warranty = data as ProductWarranty;
  return (
    <div className="section-card-grid">
      <article className="detail-panel wide">
        <h2>{warranty.title}</h2>
        <div className="metric-row">
          <span>{warranty.returnWindow}</span>
          <span>{warranty.warrantyPeriod}</span>
        </div>
      </article>
      <InfoList title="Support flow" items={warranty.supportFlow} />
      <InfoList title="Exceptions" items={warranty.exceptions} />
    </div>
  );
}

function InfoList({ title, items }: { title: string; items: string[] }) {
  return (
    <article className="detail-panel">
      <h2>{title}</h2>
      <ul className="feature-list">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </article>
  );
}
