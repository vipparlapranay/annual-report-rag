from scripts.evaluate_sample import evaluate


def test_evaluation_reports_measured_fixture_and_model_metrics(tmp_path) -> None:
    metrics = evaluate(tmp_path / "input", sales_count=30)

    assert metrics["source_sales_rows"] == 30
    assert metrics["source_customer_rows"] == 500
    assert metrics["source_product_rows"] == 50
    assert metrics["fact_tables_in_model"] == 1
    assert metrics["dimension_tables_in_model"] == 3
    assert metrics["dax_measures_in_model"] == 6
    assert metrics["relationships_in_model"] == 3
    assert metrics["source_data_quality_checks_passed"] == 8
    assert metrics["source_data_quality_checks_total"] == 8
    assert metrics["spark_delta_pipeline_executed"] is False
