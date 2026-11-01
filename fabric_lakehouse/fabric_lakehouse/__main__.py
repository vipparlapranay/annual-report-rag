import argparse
import json
from pathlib import Path

from fabric_lakehouse.pipeline import run_pipeline
from fabric_lakehouse.sample_data import generate_sample_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the sample medallion lakehouse.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-dir", type=Path, default=Path("output/lakehouse"))
    parser.add_argument("--sales-rows", type=int, default=5000)
    parser.add_argument(
        "--generate-sample-data",
        action="store_true",
        help="Generate deterministic sample CSV files before running Spark.",
    )
    args = parser.parse_args()
    sample_counts = None
    if args.generate_sample_data:
        sample_counts = generate_sample_data(args.input_dir, args.sales_rows)
        print(json.dumps(sample_counts, indent=2))
    result = run_pipeline(
        args.input_dir,
        args.output_dir,
        sample_counts["sales_rows"] if sample_counts else None,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
