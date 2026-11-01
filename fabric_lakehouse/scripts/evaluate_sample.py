import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

from fabric_lakehouse.sample_data import SALES_COUNT, generate_sample_data

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def evaluate(
    input_dir: Path,
    sales_count: int = SALES_COUNT,
    spark_metrics_path: Path = Path("output/lakehouse/metrics.json"),
) -> dict[str, Any]:
    generate_sample_data(input_dir, sales_count)
    customers = _read_rows(input_dir / "customers.csv")
    products = _read_rows(input_dir / "products.csv")
    sales = _read_rows(input_dir / "sales.csv")
    customer_ids = {row["customer_id"] for row in customers}
    product_ids = {row["product_id"] for row in products}

    checks = {
        "unique_customer_keys": len(customer_ids) == len(customers),
        "unique_product_keys": len(product_ids) == len(products),
        "unique_sales_keys": len({row["sale_id"] for row in sales}) == len(sales),
        "sales_customer_keys_resolve": all(
            row["customer_id"] in customer_ids for row in sales
        ),
        "sales_product_keys_resolve": all(
            row["product_id"] in product_ids for row in sales
        ),
        "positive_quantities": all(int(row["quantity"]) > 0 for row in sales),
        "discounts_in_range": all(
            0 <= float(row["discount_pct"]) <= 1 for row in sales
        ),
        "nonnegative_prices": all(
            float(row["unit_price"]) >= 0 for row in products + sales
        ),
    }

    definition = PROJECT_ROOT / "powerbi" / "Sales.SemanticModel" / "definition"
    model_text = (definition / "model.tmdl").read_text(encoding="utf-8")
    fact_text = (definition / "tables" / "FactSales.tmdl").read_text(
        encoding="utf-8"
    )
    relationships_text = (definition / "relationships.tmdl").read_text(
        encoding="utf-8"
    )
    dimensions = re.findall(r"^\s*ref table (Dim\w+)$", model_text, re.MULTILINE)
    facts = re.findall(r"^\s*ref table (Fact\w+)$", model_text, re.MULTILINE)
    measures = re.findall(r"^\s+measure ", fact_text, re.MULTILINE)
    relationships = re.findall(
        r"^relationship ", relationships_text, re.MULTILINE
    )

    spark_metrics = (
        json.loads(spark_metrics_path.read_text(encoding="utf-8"))
        if spark_metrics_path.is_file()
        else None
    )
    return {
        "dataset": "deterministic synthetic retail sales",
        "source_sales_rows": len(sales),
        "source_customer_rows": len(customers),
        "source_product_rows": len(products),
        "fact_tables_in_model": len(facts),
        "dimension_tables_in_model": len(dimensions),
        "dax_measures_in_model": len(measures),
        "relationships_in_model": len(relationships),
        "source_data_quality_checks_passed": sum(checks.values()),
        "source_data_quality_checks_total": len(checks),
        "source_data_quality_pass_rate": sum(checks.values()) / len(checks),
        "source_data_checks": checks,
        "spark_delta_pipeline_executed": spark_metrics is not None,
        "spark_delta_metrics": spark_metrics,
        "note": (
            "Source fixture and model metadata metrics only. Spark/Delta output "
            "metrics are included only after a successful pipeline run."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure sample data quality and semantic-model structure."
    )
    parser.add_argument("--input-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--sales-rows", type=int, default=SALES_COUNT)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation-results.json"),
    )
    parser.add_argument(
        "--spark-metrics",
        type=Path,
        default=Path("output/lakehouse/metrics.json"),
    )
    args = parser.parse_args()
    metrics = evaluate(args.input_dir, args.sales_rows, args.spark_metrics)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    if metrics["source_data_quality_pass_rate"] != 1.0:
        raise SystemExit("Synthetic source data failed a quality check.")


if __name__ == "__main__":
    main()
