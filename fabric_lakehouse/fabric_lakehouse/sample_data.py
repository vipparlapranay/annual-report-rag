import csv
import random
from datetime import date, timedelta
from pathlib import Path

CUSTOMER_COUNT = 500
PRODUCT_COUNT = 50
SALES_COUNT = 5000
START_DATE = date(2024, 1, 1)
END_DATE = date(2025, 12, 31)

_SEGMENTS = ("Consumer", "Corporate", "Small Business")
_REGIONS = ("North", "South", "East", "West")
_CATEGORIES = {
    "Electronics": ("Audio", "Computing", "Accessories"),
    "Home": ("Kitchen", "Decor", "Furniture"),
    "Outdoor": ("Camping", "Fitness", "Travel"),
    "Office": ("Writing", "Storage", "Furniture"),
    "Apparel": ("Footwear", "Outerwear", "Basics"),
}
_CHANNELS = ("Online", "Store", "Partner")


def generate_sample_data(output_dir: Path, sales_count: int = SALES_COUNT) -> dict[str, int]:
    if sales_count <= 0:
        raise ValueError("sales_count must be positive.")
    output_dir.mkdir(parents=True, exist_ok=True)
    customers_path = output_dir / "customers.csv"
    products_path = output_dir / "products.csv"
    sales_path = output_dir / "sales.csv"

    customer_rng = random.Random(202501)
    with customers_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(
            ["customer_id", "customer_name", "segment", "region", "signup_date"]
        )
        for customer_id in range(1, CUSTOMER_COUNT + 1):
            writer.writerow(
                [
                    customer_id,
                    f"Customer {customer_id:04d}",
                    customer_rng.choice(_SEGMENTS),
                    customer_rng.choice(_REGIONS),
                    (START_DATE - timedelta(days=customer_rng.randint(0, 1500))).isoformat(),
                ]
            )

    product_rng = random.Random(202502)
    products: list[tuple[int, float]] = []
    with products_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["product_id", "product_name", "category", "subcategory", "unit_price"])
        categories = list(_CATEGORIES)
        for product_id in range(1, PRODUCT_COUNT + 1):
            category = categories[(product_id - 1) % len(categories)]
            subcategory = _CATEGORIES[category][(product_id - 1) % 3]
            price = round(product_rng.uniform(8.0, 650.0), 2)
            products.append((product_id, price))
            writer.writerow(
                [
                    product_id,
                    f"{subcategory} Product {product_id:03d}",
                    category,
                    subcategory,
                    f"{price:.2f}",
                ]
            )

    sales_rng = random.Random(202503)
    date_span = (END_DATE - START_DATE).days
    with sales_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "sale_id",
                "order_date",
                "customer_id",
                "product_id",
                "quantity",
                "unit_price",
                "discount_pct",
                "channel",
            ]
        )
        for sale_id in range(1, sales_count + 1):
            product_id, price = sales_rng.choice(products)
            order_date = START_DATE + timedelta(days=sales_rng.randint(0, date_span))
            writer.writerow(
                [
                    sale_id,
                    order_date.isoformat(),
                    sales_rng.randint(1, CUSTOMER_COUNT),
                    product_id,
                    sales_rng.randint(1, 8),
                    f"{price:.2f}",
                    f"{sales_rng.choice((0, 0, 0.05, 0.10, 0.15)):.2f}",
                    sales_rng.choice(_CHANNELS),
                ]
            )

    return {
        "sales_rows": sales_count,
        "customer_rows": CUSTOMER_COUNT,
        "product_rows": PRODUCT_COUNT,
    }
