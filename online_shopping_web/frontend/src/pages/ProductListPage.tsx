import { useEffect, useMemo, useState } from "react";
import { fetchCategories, fetchProducts } from "../api";
import { ProductCard } from "../components/ProductCard";
import { sendAgiEvent } from "../tracking/agiClient";
import { usePageTracking } from "../tracking/usePageTracking";
import type { Product } from "../types";

export function ProductListPage() {
  usePageTracking("product_list");
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("All");
  const [sort, setSort] = useState("featured");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchCategories().then((response) => setCategories(response.categories));
  }, []);

  useEffect(() => {
    setLoading(true);
    fetchProducts({ search, category, sort })
      .then((response) => setProducts(response.products))
      .finally(() => setLoading(false));
  }, [search, category, sort]);

  const saleCount = useMemo(
    () => products.filter((product) => product.originalPrice > product.price).length,
    [products],
  );

  function updateSearch(value: string) {
    setSearch(value);
    sendAgiEvent({
      type: "search",
      pageType: "product_list",
      metadata: { search: value },
    });
  }

  function updateCategory(value: string) {
    setCategory(value);
    sendAgiEvent({
      type: "filter",
      pageType: "product_list",
      metadata: { category: value },
    });
  }

  function updateSort(value: string) {
    setSort(value);
    sendAgiEvent({
      type: "filter",
      pageType: "product_list",
      metadata: { sort: value },
    });
  }

  return (
    <section className="page">
      <div className="hero-band">
        <div>
          <p className="eyebrow">Mixed-category demo store</p>
          <h1>Products ready for abandonment testing</h1>
          <p>
            Browse, compare cheaper alternatives, add to cart, and move through checkout. Every
            key action is ready to send a future AGI event.
          </p>
        </div>
        <div className="stat-strip">
          <span>{products.length} items</span>
          <span>{saleCount} on sale</span>
          <span>Free shipping over $150</span>
        </div>
      </div>

      <div className="toolbar">
        <input
          placeholder="Search products, brands, descriptions"
          value={search}
          onChange={(event) => updateSearch(event.target.value)}
        />
        <select value={category} onChange={(event) => updateCategory(event.target.value)}>
          <option>All</option>
          {categories.map((item) => (
            <option key={item}>{item}</option>
          ))}
        </select>
        <select value={sort} onChange={(event) => updateSort(event.target.value)}>
          <option value="featured">Featured</option>
          <option value="price_asc">Price: low to high</option>
          <option value="price_desc">Price: high to low</option>
          <option value="rating">Top rated</option>
        </select>
      </div>

      {loading ? <p>Loading products...</p> : null}
      <div className="product-grid">
        {products.map((product) => (
          <ProductCard key={product.id} product={product} />
        ))}
      </div>
    </section>
  );
}
