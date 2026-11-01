import json
import tempfile
from pathlib import Path

from app.answering import ReportAnswerer
from app.config import Settings
from app.documents import chunk_text
from app.vector_store import ReportStore

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    questions = json.loads(
        (ROOT / "data" / "evaluation" / "questions.json").read_text(
            encoding="utf-8"
        )
    )
    report_path = ROOT / "data" / "demo" / "fictional_annual_report.md"
    text = report_path.read_text(encoding="utf-8")
    results = []
    with tempfile.TemporaryDirectory(prefix="annual-report-eval-") as temp_dir:
        for chunk_size in (500, 900, 1300):
            for top_k in (2, 4):
                config = Settings(
                    chroma_path=Path(temp_dir) / f"chunk-{chunk_size}-top-{top_k}",
                    collection_name=f"eval-{chunk_size}-{top_k}",
                    chunk_size=chunk_size,
                    top_k=top_k,
                )
                store = ReportStore(config, ephemeral=True)
                store.add(
                    chunk_text(
                        text,
                        report_path.name,
                        None,
                        config.chunk_size,
                        config.chunk_overlap,
                    )
                )
                answerer = ReportAnswerer(store, config)
                correct = faithful = retrieved = 0
                for item in questions:
                    response = answerer.ask(item["question"])
                    expected = item["answer_contains"].lower()
                    correct += int(expected in response.answer.lower())
                    faithful += int(
                        bool(response.citations)
                        and response.answer == response.citations[0].excerpt
                        and any(
                            response.answer in chunk.text
                            and response.citations[0].document == chunk.source
                            for chunk in store.search(
                                item["question"], config.top_k
                            )
                        )
                    )
                    retrieved += int(
                        any(
                            expected in chunk.text.lower()
                            for chunk in store.search(item["question"], config.top_k)
                        )
                    )
                results.append(
                    {
                        "chunk_size": chunk_size,
                        "top_k": top_k,
                        "answer_accuracy": round(correct / len(questions), 4),
                        "citation_faithfulness": round(
                            faithful / len(questions), 4
                        ),
                        "retrieval_recall_at_k": round(
                            retrieved / len(questions), 4
                        ),
                    }
                )
    selected = max(
        results,
        key=lambda item: (
            item["answer_accuracy"],
            item["citation_faithfulness"],
            item["retrieval_recall_at_k"],
            -item["top_k"],
            -item["chunk_size"],
        ),
    )
    metrics = {
        "reports_evaluated": 1,
        "evaluation_questions": len(questions),
        "answer_accuracy": selected["answer_accuracy"],
        "citation_faithfulness": selected["citation_faithfulness"],
        f"retrieval_recall_at_{selected['top_k']}": selected[
            "retrieval_recall_at_k"
        ],
        "selected_chunk_size": selected["chunk_size"],
        "selected_top_k": selected["top_k"],
        "configuration_results": results,
        "dataset": "fictional Northstar Components FY2024 report",
        "note": "Synthetic single-document benchmark; not a real-world accuracy claim.",
    }
    print(json.dumps(metrics, indent=2))
    (ROOT / "evaluation-results.json").write_text(
        json.dumps(metrics, indent=2) + "\n", encoding="utf-8"
    )
    if (
        selected["answer_accuracy"] < 0.8
        or selected["citation_faithfulness"] < 1.0
        or selected["retrieval_recall_at_k"] < 0.8
    ):
        raise SystemExit("Evaluation did not meet the minimum quality thresholds.")


if __name__ == "__main__":
    main()
