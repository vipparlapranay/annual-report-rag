import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    chroma_path: Path = Path(os.getenv("CHROMA_PATH", ".chroma"))
    collection_name: str = os.getenv("COLLECTION_NAME", "annual_reports")
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "500"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "120"))
    top_k: int = int(os.getenv("TOP_K", "2"))
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", "20000000"))
    aws_region: str = os.getenv("AWS_REGION", "us-east-1")
    bedrock_model_id: str = os.getenv("BEDROCK_MODEL_ID", "")
    bedrock_input_cost_per_1k_tokens: float = float(
        os.getenv("BEDROCK_INPUT_COST_PER_1K_TOKENS", "0")
    )
    bedrock_output_cost_per_1k_tokens: float = float(
        os.getenv("BEDROCK_OUTPUT_COST_PER_1K_TOKENS", "0")
    )

    def __post_init__(self) -> None:
        if self.chunk_size <= 0 or self.chunk_overlap < 0:
            raise ValueError("Chunk size must be positive and overlap non-negative.")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("Chunk overlap must be smaller than chunk size.")
        if self.top_k <= 0 or self.max_upload_bytes <= 0:
            raise ValueError("top_k and max_upload_bytes must be positive.")
        if (
            self.bedrock_input_cost_per_1k_tokens < 0
            or self.bedrock_output_cost_per_1k_tokens < 0
        ):
            raise ValueError("Token pricing rates cannot be negative.")


settings = Settings()
