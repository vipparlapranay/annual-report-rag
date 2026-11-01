import csv

import pytest

from fabric_lakehouse.sample_data import (
    CUSTOMER_COUNT,
    PRODUCT_COUNT,
    generate_sample_data,
)


def test_sample_data_is_reproducible_and_has_expected_row_counts(tmp_path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_counts = generate_sample_data(first, sales_count=40)
    second_counts = generate_sample_data(second, sales_count=40)

    assert first_counts == {
        "sales_rows": 40,
        "customer_rows": CUSTOMER_COUNT,
        "product_rows": PRODUCT_COUNT,
    }
    for name in ("customers.csv", "products.csv", "sales.csv"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    with (first / "sales.csv").open(encoding="utf-8", newline="") as file:
        assert len(list(csv.DictReader(file))) == 40


def test_sample_data_rejects_non_positive_sales_count(tmp_path) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        generate_sample_data(tmp_path, sales_count=0)
