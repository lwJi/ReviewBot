# agents.py
import json
from typing import List, Dict, Any, Optional
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential_jitter
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

from prompts import (
    WORKER_PROMPT_GENERIC,
    WORKER_PROMPT_CPP,
    WORKER_PROMPT_PY,
    SUPERVISOR_PROMPT,
    SYNTHESIZER_PROMPT,
    JSON_WORKER_SCHEMA,
    JSON_SUPERVISOR_SCHEMA,
)
from utils import extract_json_from_text


async def _ainvoke_with_retry(chain, inputs: dict, attempts: int = 4) -> str:
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential_jitter(initial=1, max=8)
    ):
        with attempt:
            return await chain.ainvoke(inputs)
    raise RuntimeError("Exhausted retries")

def render_worker_prompt_text(
    *, language: str, file_path: str, chunk_index: int, total_chunks: int, code_with_line_numbers: str
) -> str:
    worker_prompt = _pick_worker_prompt(language)
    return worker_prompt.format(
        **(
            {"language": language} if worker_prompt is WORKER_PROMPT_GENERIC else {}
        ),
        file_path=file_path,
        chunk_index=chunk_index,
        total_chunks=total_chunks,
        code_with_line_numbers=code_with_line_numbers,
        json_schema=JSON_WORKER_SCHEMA,
    )

def render_supervisor_prompt_text(*, reviews_text_block: str) -> str:
    return SUPERVISOR_PROMPT.format(reviews=reviews_text_block, json_schema=JSON_SUPERVISOR_SCHEMA)

def render_synthesizer_prompt_text(*, chunk_summaries_jsonl: str) -> str:
    return SYNTHESIZER_PROMPT.format(chunk_summaries=chunk_summaries_jsonl)

def _pick_worker_prompt(language: str):
    if language == "cpp":
        return WORKER_PROMPT_CPP
    if language == "python":
        return WORKER_PROMPT_PY
    return WORKER_PROMPT_GENERIC


async def run_worker_agent(
    llm: ChatOpenAI,
    *,
    language: str,
    file_path: str,
    chunk_index: int,
    total_chunks: int,
    code_with_line_numbers: str
) -> Dict[str, Any]:
    """
    Returns parsed JSON dict following the worker schema.
    """
    worker_prompt = _pick_worker_prompt(language)
    chain = worker_prompt | llm | StrOutputParser()
    rendered = await _ainvoke_with_retry(
        chain,
        {
            "language": language,
            "file_path": file_path,
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "code_with_line_numbers": code_with_line_numbers,
            "json_schema": JSON_WORKER_SCHEMA,
        }
        if worker_prompt is WORKER_PROMPT_GENERIC else
        {
            "file_path": file_path,
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "code_with_line_numbers": code_with_line_numbers,
            "json_schema": JSON_WORKER_SCHEMA,
        }
    )
    json_text = extract_json_from_text(rendered)
    try:
        return json.loads(json_text)
    except Exception:
        # Last-ditch: ask model to output only JSON (repair step)
        repair_chain = (worker_prompt | llm | StrOutputParser())
        repaired = await _ainvoke_with_retry(
            repair_chain,
            {
                **(
                    {
                        "language": language,
                        "file_path": file_path,
                        "chunk_index": chunk_index,
                        "total_chunks": total_chunks,
                        "code_with_line_numbers": code_with_line_numbers,
                        "json_schema": JSON_WORKER_SCHEMA,
                    }
                    if worker_prompt is WORKER_PROMPT_GENERIC
                    else {
                        "file_path": file_path,
                        "chunk_index": chunk_index,
                        "total_chunks": total_chunks,
                        "code_with_line_numbers": code_with_line_numbers,
                        "json_schema": JSON_WORKER_SCHEMA,
                    }
                ),
            },
        )
        repaired_json = extract_json_from_text(repaired)
        return json.loads(repaired_json)


async def run_supervisor_agent(
    llm: ChatOpenAI,
    *,
    reviews_text_block: str
) -> Dict[str, Any]:
    """
    Returns parsed JSON dict following the supervisor schema.
    """
    chain = SUPERVISOR_PROMPT | llm | StrOutputParser()
    rendered = await _ainvoke_with_retry(
        chain,
        {"reviews": reviews_text_block, "json_schema": JSON_SUPERVISOR_SCHEMA}
    )
    json_text = extract_json_from_text(rendered)
    try:
        return json.loads(json_text)
    except Exception:
        # Small repair by asking again (rare)
        rendered2 = await _ainvoke_with_retry(
            chain,
            {"reviews": reviews_text_block, "json_schema": JSON_SUPERVISOR_SCHEMA}
        )
        return json.loads(extract_json_from_text(rendered2))


async def run_synthesizer_agent(
    llm: ChatOpenAI,
    *,
    chunk_summaries_jsonl: str
) -> str:
    """
    Returns final Markdown string synthesizing chunk winners for the whole file.
    """
    chain = SYNTHESIZER_PROMPT | llm | StrOutputParser()
    md = await _ainvoke_with_retry(chain, {"chunk_summaries": chunk_summaries_jsonl})
    return md


def format_reviews_for_supervisor(worker_jsons: List[dict]) -> str:
    """
    Convert worker JSON dicts back into readable, labeled text blocks for the supervisor.
    """
    blocks = []
    for i, j in enumerate(worker_jsons, start=1):
        # Compact rendering, but keep original JSON to preserve fidelity
        blocks.append(
            f"--- Review {i} JSON ---\n{json.dumps(j, ensure_ascii=False, indent=2)}")
    return "\n\n".join(blocks)
