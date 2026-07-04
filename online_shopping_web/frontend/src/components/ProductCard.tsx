import { Link } from "react-router-dom";
import type { Product } from "../types";

type Props = {
  product: Product;
  label?: string;
  onClick?: () => void;
};

export function ProductCard({ product, label, onClick }: Props) {
  const discount = Math.round(((product.originalPrice - product.price) / product.originalPrice) * 100);

  return (
    <Link className="product-card" to={`/products/${product.id}`} onClick={onClick}>
      <div className="image-wrap">
        <img src={product.image} alt={product.name} />
        {label ? <span className="card-label">{label}</span> : null}
      </div>
      <div className="product-card-body">
        <p className="eyebrow">{product.brand}</p>
        <h3>{product.name}</h3>
        <p className="muted">{product.category}</p>
        <div className="price-row">
          <strong>${product.price.toFixed(2)}</strong>
          <span>${product.originalPrice.toFixed(2)}</span>
          <em>{discount}% off</em>
        </div>
        <p className="rating">Rating {product.rating.toFixed(1)} / 5</p>
      </div>
    </Link>
  );
}
