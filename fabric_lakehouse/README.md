# Microsoft Fabric Lakehouse + Power BI CI/CD

This self-contained project builds a deterministic **synthetic retail dataset** into a Delta bronze/silver/gold lakehouse, exposes a one-fact/three-dimension star schema, provides a PBIP/TMDL semantic-model starter, and includes Azure DevOps validation and Fabric deployment-pipeline stages.

It does not connect to a tenant or claim that a Fabric workspace deployment has already happened. Actual Dev/Test promotion requires Fabric capacity/workspaces, a Fabric deployment pipeline, Azure DevOps service connection, Git integration, and environment approvals.

## Reproducible local run

Requirements: Python 3.10+, Java 17+, and network access on the first run for Spark/Delta dependencies. On Windows, run Spark through WSL2 or a Linux container; native Spark also requires Hadoop's Windows utilities (`winutils.exe`), which are not bundled here.

```powershell
cd fabric_lakehouse
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m fabric_lakehouse --generate-sample-data --sales-rows 5000
python scripts/evaluate_sample.py
python -m pytest -q
```

By default the CLI reads `data/raw` and writes `output/lakehouse`. The generator emits the source CSVs with fixed seeds. Spark creates:

- Bronze: raw customer, product, and sales Delta tables.
- Silver: typed, deduplicated and validated sales/customer/product Delta tables.
- Gold: `fact_sales`, `dim_date`, `dim_customer`, and `dim_product` Delta tables under `gold/Tables`.
- `output/lakehouse/metrics.json`: actual row counts and data-quality check results.

`python scripts/evaluate_sample.py` writes `evaluation-results.json` with measured source-fixture quality, model table/relationship/measure counts, and (when present) the Spark run metrics. It does not report Spark success when no Delta pipeline metrics exist.

The gold tables are a local Delta Lake layout. To use the semantic model, place/import those tables into a Fabric Lakehouse and connect its SQL endpoint; the local run does not publish to OneLake.

## Power BI semantic model

Open `powerbi/Sales.pbip` in a recent Power BI Desktop version with PBIP/TMDL support. The TMDL semantic model includes the sales star schema, three one-to-many relationships, and six DAX measures. Configure the `LakehouseSqlEndpoint` and `LakehouseDatabase` model parameters for the Fabric SQL endpoint and refresh credentials after importing the gold tables.

The `.Report` folder is a PBIR report-to-model reference with a blank Sales Overview page shell. Add visuals in Power BI Desktop; this starter does not claim prebuilt visual pages or report screenshots.

## Azure DevOps pipeline

`azure-pipelines.yml` runs tests and the local Spark pipeline on PRs and `main`, then publishes Delta tables and measured metrics. On `main`, it promotes the connected Dev workspace into Test through the Fabric Deployment Pipelines API when the pipeline/stage ID variables are configured. Configure the Dev workspace's Git integration to the repository and keep it synchronized before promotion. Before enabling deployments:

1. Connect the Dev workspace to Azure Repos and sync the PBIP semantic model.
2. Create and configure a Fabric deployment pipeline with Dev and Test stages.
3. Configure `FABRIC_AZURE_SERVICE_CONNECTION` as an Azure Resource Manager service connection whose service principal has Fabric API access and the required workspace/pipeline roles.
4. Define secure pipeline variables `FABRIC_DEPLOYMENT_PIPELINE_ID`, `FABRIC_DEV_STAGE_ID`, and `FABRIC_TEST_STAGE_ID`.
5. Create the Azure DevOps environment `Fabric-Test` and configure its approvals/checks.
6. Confirm the Azure identity can request a token for `https://api.fabric.microsoft.com` and call the Fabric deployment API.

The deployment helper sends a promotion request and waits for an asynchronous Fabric operation to complete; API failures fail the pipeline. No credentials or tenant-specific IDs belong in source control.

## Measured demo results

The checked-in evaluation measures the deterministic input fixture and checked-in semantic-model metadata:

| Metric | Measured result |
|---|---:|
| Synthetic sales rows | 5,000 |
| Customer / product records | 500 / 50 |
| Star schema | 1 fact + 3 dimensions |
| DAX measures / relationships | 6 / 3 |
| Source data quality checks | 8/8 passed |
| Fabric project tests | 9 passed |

These are fixture/model validation metrics, not production throughput or evidence of a Fabric workspace deployment. This Windows environment lacks Hadoop's `winutils.exe`, so the Spark/Delta write itself could not be run locally; the Azure DevOps Linux job is configured to run and publish that separate result. Delta output results are reported only after the Spark pipeline successfully runs.
