import json
import logging
from pathlib import Path
from typing import Any

from delta import configure_spark_with_delta_pip
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DateType,
    DecimalType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

LOGGER = logging.getLogger("fabric_lakehouse")

CUSTOMER_SCHEMA = StructType(
    [
        StructField("customer_id", IntegerType(), False),
        StructField("customer_name", StringType(), False),
        StructField("segment", StringType(), False),
        StructField("region", StringType(), False),
        StructField("signup_date", DateType(), False),
    ]
)
PRODUCT_SCHEMA = StructType(
    [
        StructField("product_id", IntegerType(), False),
        StructField("product_name", StringType(), False),
        StructField("category", StringType(), False),
        StructField("subcategory", StringType(), False),
        StructField("unit_price", DecimalType(12, 2), False),
    ]
)
SALES_SCHEMA = StructType(
    [
        StructField("sale_id", IntegerType(), False),
        StructField("order_date", DateType(), False),
        StructField("customer_id", IntegerType(), False),
        StructField("product_id", IntegerType(), False),
        StructField("quantity", IntegerType(), False),
        StructField("unit_price", DecimalType(12, 2), False),
        StructField("discount_pct", DecimalType(5, 4), False),
        StructField("channel", StringType(), False),
    ]
)


def create_spark(app_name: str = "FabricMedallionLakehouse") -> SparkSession:
    builder = (
        SparkSession.builder.appName(app_name)
        .master("local[2]")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config(
            "spark.sql.catalog.spark_catalog",
            "org.apache.spark.sql.delta.catalog.DeltaCatalog",
        )
    )
    return configure_spark_with_delta_pip(builder).getOrCreate()


def _read_csv(spark: SparkSession, path: Path, schema: StructType) -> DataFrame:
    return (
        spark.read.option("header", True)
        .option("dateFormat", "yyyy-MM-dd")
        .schema(schema)
        .csv(str(path))
    )


def _write_delta(frame: DataFrame, path: Path) -> None:
    frame.write.format("delta").mode("overwrite").option("overwriteSchema", "true").save(
        str(path)
    )


def _assert_unique(frame: DataFrame, key: str, table: str) -> None:
    duplicate = frame.groupBy(key).count().filter(F.col("count") > 1).limit(1).count()
    if duplicate:
        raise ValueError(f"{table} contains duplicate {key} values.")


def run_pipeline(input_dir: Path, output_dir: Path, sales_count: int | None = None) -> dict[str, Any]:
    required_inputs = ("customers.csv", "products.csv", "sales.csv")
    missing = [name for name in required_inputs if not (input_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing input CSV files: {', '.join(missing)}")

    spark = create_spark()
    try:
        customers_raw = _read_csv(spark, input_dir / "customers.csv", CUSTOMER_SCHEMA)
        products_raw = _read_csv(spark, input_dir / "products.csv", PRODUCT_SCHEMA)
        sales_raw = _read_csv(spark, input_dir / "sales.csv", SALES_SCHEMA)

        bronze = output_dir / "bronze"
        silver = output_dir / "silver"
        gold = output_dir / "gold" / "Tables"
        for name, frame in (
            ("customers", customers_raw),
            ("products", products_raw),
            ("sales", sales_raw),
        ):
            _write_delta(frame, bronze / "Tables" / name)

        customers = customers_raw.dropna(
            subset=["customer_id", "customer_name", "segment", "region"]
        ).dropDuplicates(["customer_id"])
        products = products_raw.filter(F.col("unit_price") >= 0).dropna(
            subset=["product_id", "product_name", "category"]
        ).dropDuplicates(["product_id"])
        sales_validity = (
            F.col("sale_id").isNotNull()
            & F.col("order_date").isNotNull()
            & F.col("customer_id").isNotNull()
            & F.col("product_id").isNotNull()
            & (F.col("quantity") > 0)
            & (F.col("unit_price") >= 0)
            & (F.col("discount_pct") >= 0)
            & (F.col("discount_pct") <= 1)
        )
        valid_sales = sales_raw.filter(sales_validity)
        valid_sales = valid_sales.join(
            customers.select("customer_id"), "customer_id", "inner"
        ).join(products.select("product_id"), "product_id", "inner")
        sales = valid_sales.dropDuplicates(["sale_id"])

        _assert_unique(customers, "customer_id", "silver.dim_customer")
        _assert_unique(products, "product_id", "silver.dim_product")
        _assert_unique(sales, "sale_id", "silver.sales")
        for name, frame in (
            ("dim_customer", customers),
            ("dim_product", products),
            ("sales", sales),
        ):
            _write_delta(frame, silver / "Tables" / name)

        date_bounds = sales.agg(
            F.min("order_date").alias("min_date"),
            F.max("order_date").alias("max_date"),
        ).first()
        if date_bounds["min_date"] is None:
            raise ValueError("No valid sales rows remain after silver quality checks.")

        dim_date = (
            spark.range(1)
            .select(
                F.explode(
                    F.sequence(
                        F.lit(date_bounds["min_date"]),
                        F.lit(date_bounds["max_date"]),
                        F.expr("INTERVAL 1 DAY"),
                    )
                ).alias("date")
            )
            .select(
                F.date_format("date", "yyyyMMdd").cast("int").alias("date_key"),
                "date",
                F.year("date").alias("year"),
                F.quarter("date").alias("quarter"),
                F.month("date").alias("month"),
                F.date_format("date", "MMMM").alias("month_name"),
                F.dayofmonth("date").alias("day"),
                F.dayofweek("date").alias("day_of_week"),
            )
        )
        dim_customer = customers.select(
            "customer_id", "customer_name", "segment", "region", "signup_date"
        )
        dim_product = products.select(
            "product_id", "product_name", "category", "subcategory", "unit_price"
        )
        fact_sales = (
            sales.withColumn(
                "date_key", F.date_format("order_date", "yyyyMMdd").cast("int")
            )
            .select(
                "sale_id",
                "date_key",
                "customer_id",
                "product_id",
                "quantity",
                "unit_price",
                "discount_pct",
                "channel",
            )
        )

        dimensions = {
            "dim_date": dim_date,
            "dim_customer": dim_customer,
            "dim_product": dim_product,
        }
        for name, frame in dimensions.items():
            _write_delta(frame, gold / name)
        _write_delta(fact_sales, gold / "fact_sales")

        checks = {
            "unique_sale_id": sales.count()
            == sales.select("sale_id").distinct().count(),
            "positive_quantity": sales.filter(F.col("quantity") <= 0).count() == 0,
            "valid_discount_range": sales.filter(
                (F.col("discount_pct") < 0) | (F.col("discount_pct") > 1)
            ).count()
            == 0,
            "fact_customer_referential_integrity": fact_sales.join(
                dim_customer.select("customer_id"), "customer_id", "left_anti"
            ).count()
            == 0,
            "fact_product_referential_integrity": fact_sales.join(
                dim_product.select("product_id"), "product_id", "left_anti"
            ).count()
            == 0,
            "fact_date_referential_integrity": fact_sales.join(
                dim_date.select("date_key"), "date_key", "left_anti"
            ).count()
            == 0,
        }
        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            raise ValueError(f"Gold data quality checks failed: {', '.join(failed)}")

        metrics = {
            "dataset": "deterministic synthetic retail sales",
            "input_sales_rows": sales_count or sales_raw.count(),
            "fact_sales_rows": fact_sales.count(),
            "dim_customer_rows": dim_customer.count(),
            "dim_product_rows": dim_product.count(),
            "dim_date_rows": dim_date.count(),
            "fact_table_count": 1,
            "dimension_table_count": len(dimensions),
            "data_quality_checks_passed": sum(checks.values()),
            "data_quality_checks_total": len(checks),
            "data_quality_pass_rate": sum(checks.values()) / len(checks),
            "checks": checks,
            "storage_format": "Delta",
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "metrics.json").write_text(
            json.dumps(metrics, indent=2) + "\n", encoding="utf-8"
        )
        LOGGER.info("Pipeline completed: %s", json.dumps(metrics, sort_keys=True))
        return metrics
    finally:
        spark.stop()
