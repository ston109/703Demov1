import { NavLink } from "react-router-dom";

const sections = [
  { label: "Overview", path: "" },
  { label: "Info", path: "info" },
  { label: "Shipping", path: "shipping" },
  { label: "Merchant", path: "merchant" },
  { label: "Reviews", path: "reviews" },
  { label: "Warranty", path: "warranty" },
];

export function ProductSectionNav({ productId }: { productId: string }) {
  return (
    <nav className="product-section-nav">
      {sections.map((section) => (
        <NavLink
          key={section.label}
          to={section.path ? `/products/${productId}/${section.path}` : `/products/${productId}`}
          end={!section.path}
        >
          {section.label}
        </NavLink>
      ))}
    </nav>
  );
}
