import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "powerbi" / "Sales.SemanticModel" / "definition"


def test_tmdl_model_has_star_schema_and_six_measures() -> None:
    model = MODEL / "model.tmdl"
    relationships = MODEL / "relationships.tmdl"
    fact = MODEL / "tables" / "FactSales.tmdl"
    assert model.is_file()
    assert relationships.read_text(encoding="utf-8").count("relationship ") == 3
    fact_text = fact.read_text(encoding="utf-8")
    assert len(re.findall(r"^\s+measure ", fact_text, re.MULTILINE)) == 6


def test_pbip_model_metadata_is_valid_json() -> None:
    metadata = ROOT / "powerbi" / "Sales.SemanticModel" / "definition.pbism"
    assert json.loads(metadata.read_text(encoding="utf-8"))["version"] == "1.0"


def test_pbip_report_has_a_page_and_relative_model_reference() -> None:
    report_root = ROOT / "powerbi" / "Sales.Report"
    reference = json.loads((report_root / "definition.pbir").read_text(encoding="utf-8"))
    report = json.loads(
        (report_root / "definition" / "report.json").read_text(encoding="utf-8")
    )
    page = json.loads(
        (
            report_root
            / "definition"
            / "pages"
            / "SalesOverview"
            / "page.json"
        ).read_text(encoding="utf-8")
    )
    assert reference["datasetReference"]["byPath"]["path"] == "../Sales.SemanticModel"
    assert report["layoutOptimization"] == "None"
    assert page["displayName"] == "Sales Overview"
