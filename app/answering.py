import re
import time
from typing import TypedDict

import boto3
from langgraph.graph import END, START, StateGraph

from app.config import Settings, settings
from app.documents import DocumentChunk
from app.schemas import AskResponse, Citation
from app.vector_store import ReportStore, _terms

_WORD_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


class AnswerState(TypedDict, total=False):
    question: str
    top_k: int
    chunks: list[DocumentChunk]
    answer: str
    citations: list[Citation]
    abstained: bool
    input_tokens: int
    output_tokens: int


def _tokens(text: str) -> int:
    return len(_WORD_PATTERN.findall(text))


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def _answer_sentence(question: str, chunks: list[DocumentChunk]) -> tuple[str, DocumentChunk] | None:
    terms = _terms(question) - {"company", "report", "annual", "fiscal", "its"}
    best: tuple[float, str, DocumentChunk] | None = None
    for chunk in chunks:
        for sentence in _sentences(chunk.text):
            sentence_terms = _terms(sentence)
            overlap = len(terms & sentence_terms)
            if not overlap:
                continue
            score = overlap / max(len(terms), 1)
            candidate = (score, sentence, chunk)
            if best is None or candidate[0] > best[0]:
                best = candidate
    if best is None:
        return None
    return best[1], best[2]


class ReportAnswerer:
    def __init__(self, store: ReportStore, config: Settings = settings) -> None:
        self.store = store
        self.config = config
        self.bedrock = (
            boto3.client("bedrock-runtime", region_name=config.aws_region)
            if config.bedrock_model_id
            else None
        )
        graph = StateGraph(AnswerState)
        graph.add_node("retrieve", self._retrieve)
        graph.add_node("generate", self._generate)
        graph.add_node("verify", self._verify)
        graph.add_edge(START, "retrieve")
        graph.add_edge("retrieve", "generate")
        graph.add_edge("generate", "verify")
        graph.add_edge("verify", END)
        self.graph = graph.compile()

    def _retrieve(self, state: AnswerState) -> AnswerState:
        return {
            "chunks": self.store.search(state["question"], state["top_k"]),
        }

    def _generate(self, state: AnswerState) -> AnswerState:
        selected = _answer_sentence(state["question"], state.get("chunks", []))
        if selected is None:
            return {
                "answer": "I couldn't find supporting information in the indexed reports.",
                "citations": [],
                "abstained": True,
            }
        sentence, chunk = selected
        input_tokens = 0
        output_tokens = 0
        if self.bedrock is not None:
            context = "\n\n".join(
                f"[{item.source}]\n{item.text}" for item in state.get("chunks", [])
            )
            response = self.bedrock.converse(
                modelId=self.config.bedrock_model_id,
                system=[
                    {
                        "text": (
                            "Answer using one complete sentence copied verbatim from "
                            "the supplied report excerpts. Do not add any text, "
                            "interpretation, or citations. If unsupported, return UNKNOWN."
                        )
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "text": (
                                    f"Question: {state['question']}\n\n"
                                    f"Report excerpts:\n{context}"
                                )
                            }
                        ],
                    }
                ],
                inferenceConfig={"maxTokens": 256, "temperature": 0},
            )
            generated = response["output"]["message"]["content"][0]["text"].strip()
            generated = generated.strip('"')
            exact_source = next(
                (
                    candidate
                    for item in state.get("chunks", [])
                    for candidate in _sentences(item.text)
                    if candidate == generated
                ),
                None,
            )
            usage = response.get("usage", {})
            input_tokens = int(usage.get("inputTokens", 0))
            output_tokens = int(usage.get("outputTokens", 0))
            if exact_source is None:
                return {
                    "answer": "I couldn't verify a supported answer in the indexed reports.",
                    "citations": [],
                    "abstained": True,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                }
            sentence = exact_source
            chunk = next(item for item in state.get("chunks", []) if sentence in item.text)
        return {
            "answer": sentence,
            "citations": [
                Citation(
                    document=chunk.source,
                    page=chunk.page,
                    excerpt=sentence,
                )
            ],
            "abstained": False,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

    def _verify(self, state: AnswerState) -> AnswerState:
        answer = state.get("answer", "")
        citations = state.get("citations", [])
        if not citations or not any(
            citation.excerpt == answer
            and any(
                citation.document == chunk.source
                and answer in chunk.text
                for chunk in state.get("chunks", [])
            )
            for citation in citations
        ):
            return {
                "answer": "I couldn't verify a supported answer in the indexed reports.",
                "citations": [],
                "abstained": True,
            }
        return {}

    def ask(self, question: str, top_k: int | None = None) -> AskResponse:
        started = time.perf_counter()
        result = self.graph.invoke(
            {"question": question, "top_k": top_k or self.config.top_k}
        )
        input_tokens = result.get("input_tokens") or (
            _tokens(question)
            + sum(_tokens(chunk.text) for chunk in result.get("chunks", []))
        )
        output_tokens = result.get("output_tokens") or _tokens(result["answer"])
        cost = (
            input_tokens / 1000 * self.config.bedrock_input_cost_per_1k_tokens
            + output_tokens / 1000 * self.config.bedrock_output_cost_per_1k_tokens
        )
        return AskResponse(
            answer=result["answer"],
            citations=result.get("citations", []),
            abstained=result.get("abstained", True),
            latency_ms=(time.perf_counter() - started) * 1000,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=cost,
        )
