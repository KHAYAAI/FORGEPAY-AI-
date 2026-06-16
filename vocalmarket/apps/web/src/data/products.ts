import type { Product } from "@/types";

export const CATEGORIES: Array<{ id: string; label: string; icon: string }> = [
  { id: "all", label: "All", icon: "🛍️" },
  { id: "dairy", label: "Dairy", icon: "🥛" },
  { id: "produce", label: "Produce", icon: "🥦" },
  { id: "bakery", label: "Bakery", icon: "🍞" },
  { id: "meat", label: "Meat", icon: "🥩" },
  { id: "pantry", label: "Pantry", icon: "🥫" },
];

export const PRODUCT_CATALOG: Product[] = [
  { id: "p1", name: "Full Cream Milk 2L", price: 32.99, currency: "R", inStock: true, category: "dairy", emoji: "🥛", rating: 4.6, unit: "2L" },
  { id: "p2", name: "Free Range Eggs (18)", price: 54.99, currency: "R", inStock: true, category: "dairy", emoji: "🥚", rating: 4.8, unit: "18 pack" },
  { id: "p3", name: "Cheddar Cheese Block", price: 89.99, currency: "R", inStock: true, category: "dairy", emoji: "🧀", rating: 4.5, unit: "400g" },
  { id: "p4", name: "Avocados", price: 24.99, currency: "R", inStock: true, category: "produce", emoji: "🥑", rating: 4.7, unit: "4 pack" },
  { id: "p5", name: "Bananas", price: 19.99, currency: "R", inStock: true, category: "produce", emoji: "🍌", rating: 4.4, unit: "1kg" },
  { id: "p6", name: "Tomatoes", price: 22.99, currency: "R", inStock: false, category: "produce", emoji: "🍅", rating: 4.3, unit: "1kg" },
  { id: "p7", name: "Sourdough Loaf", price: 38.5, currency: "R", inStock: true, category: "bakery", emoji: "🍞", rating: 4.9, unit: "600g" },
  { id: "p8", name: "Croissants", price: 45.0, currency: "R", inStock: true, category: "bakery", emoji: "🥐", rating: 4.6, unit: "6 pack" },
  { id: "p9", name: "Chicken Breasts", price: 109.99, currency: "R", inStock: true, category: "meat", emoji: "🍗", rating: 4.5, unit: "1kg" },
  { id: "p10", name: "Beef Mince", price: 129.99, currency: "R", inStock: true, category: "meat", emoji: "🥩", rating: 4.4, unit: "500g" },
  { id: "p11", name: "Basmati Rice", price: 64.99, currency: "R", inStock: true, category: "pantry", emoji: "🍚", rating: 4.7, unit: "2kg" },
  { id: "p12", name: "Olive Oil", price: 79.99, currency: "R", inStock: true, category: "pantry", emoji: "🫒", rating: 4.8, unit: "750ml" },
];
