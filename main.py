# main.py
import os
import argparse
import asyncio
import json
from typing import List, Dict
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from langchain_openai import ChatOpenAI

from utils import (
    list_source_files, detect_language_from_extension, chunk_code_by_lines,
    add_line_numbers_preserve, safe_filename_from_path,
    save_json, save_text, load_models_config, ensure_dir, content_hash
)
from agents import (
    run_worker_agent, run_supervisor_agent, run_synthesizer_agent, format_reviews_for_supervisor
)

console = Console()

DEFAULT_MAX_LINES = 500  # chunking threshold
DEFAULT_CHUNK_SIZE = 400


def build_llms(models_cfg: dict) -> Dict[str, ChatOpenAI]:
    """
    models.yaml (optional) example:
    workers:
      - model: gpt-4o
        temperature: 0.2
      - model: gpt-4o
        temperature: 0.7
    supervisor:
      model: gpt-4o
      temperature: 0.1
    """
    workers = []
    for w in (models_cfg.get("workers") or []):
        workers.append(ChatOpenAI(
            model=w["model"], temperature=w.get("temperature", 0.3)))
    if not workers:
        # Fall back if no config
        workers = [
            ChatOpenAI(model="gpt-4o-mini", temperature=0.7),
            ChatOpenAI(model="gpt-4o", temperature=0.2),
        ]
    sup_cfg = models_cfg.get("supervisor") or {
        "model": "gpt-4o", "temperature": 0.1}
    supervisor = ChatOpenAI(
        model=sup_cfg["model"], temperature=sup_cfg.get("temperature", 0.1))
    synthesizer = supervisor  # reuse for now
    return {"workers": workers, "supervisor": supervisor, "synthesizer": synthesizer}


async def review_chunk_for_file(
    *,
    llms: Dict[str, ChatOpenAI],
    file_path: str,
    language: str,
    chunk_index: int,
    total_chunks: int,
    code_chunk: str
):
    # Prepare numbered code
    start_line = (chunk_index - 1) * DEFAULT_CHUNK_SIZE + 1
    numbered = add_line_numbers_preserve(code_chunk, start_line=start_line)

    # Run workers
    tasks = [
        run_worker_agent(
            llm=w,
            language=language,
            file_path=file_path,
            chunk_index=chunk_index,
            total_chunks=total_chunks,
            code_with_line_numbers=numbered,
        )
        for w in llms["workers"]
    ]
    worker_jsons = await asyncio.gather(*tasks)

    # Supervisor decision
    reviews_for_sup = format_reviews_for_supervisor(worker_jsons)
    sup_json = await run_supervisor_agent(llms["supervisor"], reviews_text_block=reviews_for_sup)

    # Compose a JSON summary to feed to the file-level synthesizer later
    summary = {
        "file": file_path,
        "chunk_index": chunk_index,
        "total_chunks": total_chunks,
        "winner_index": sup_json.get("winner_index"),
        "scores": sup_json.get("scores", []),
        "merged_takeaways": sup_json.get("merged_takeaways", []),
        "winning_review_text": sup_json.get("winning_review_text", ""),
    }
    return summary, worker_jsons, sup_json


async def review_single_file(
    *,
    llms: Dict[str, ChatOpenAI],
    file_path: str,
    save_dir: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    max_lines_before_chunk: int = DEFAULT_MAX_LINES
):
    # Read file
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()
    except Exception as e:
        console.print(f"[red]Error reading {file_path}: {e}[/red]")
        return

    language = detect_language_from_extension(os.path.splitext(file_path)[1])
    lines = code.splitlines()
    if len(lines) > max_lines_before_chunk:
        chunks = chunk_code_by_lines(code, max_lines=chunk_size)
    else:
        chunks = [(1, code)]

    total_chunks = len(chunks)
    summaries = []
    all_workers_json = []
    all_sup_json = []

    # Progress per file
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
        task = progress.add_task(f"Reviewing {os.path.basename(file_path)} ({
                                 total_chunks} chunk{'s' if total_chunks > 1 else ''})", total=total_chunks)
        for idx, (_start, chunk_text) in enumerate(chunks, start=1):
            summary, worker_jsons, sup_json = await review_chunk_for_file(
                llms=llms,
                file_path=file_path,
                language=language,
                chunk_index=idx,
                total_chunks=total_chunks,
                code_chunk=chunk_text
            )
            summaries.append(summary)
            all_workers_json.append(worker_jsons)
            all_sup_json.append(sup_json)
            progress.update(task, advance=1)

    # Synthesize final Markdown across chunks
    chunk_summaries_jsonl = "\n".join(
        [json.dumps(s, ensure_ascii=False) for s in summaries])
    final_markdown = await run_synthesizer_agent(llms["synthesizer"], chunk_summaries_jsonl=chunk_summaries_jsonl)

    # Persist outputs
    ensure_dir(save_dir)
    base = safe_filename_from_path(os.path.relpath(file_path))
    run_id = content_hash(file_path, "".join(lines))

    json_path = os.path.join(save_dir, f"{base}.{run_id}.reviews.json")
    md_path = os.path.join(save_dir, f"{base}.{run_id}.review.md")

    payload = {
        "file": file_path,
        "language": language,
        "chunks": summaries,
        "workers_raw": all_workers_json,
        "supervisor_raw": all_sup_json,
        "final_markdown_path": md_path,
    }
    save_json(json_path, payload)
    save_text(md_path, final_markdown)

    console.print(f"\n[bold green]✓ Saved[/bold green] JSON: {json_path}")
    console.print(f"[bold green]✓ Saved[/bold green] Markdown: {md_path}\n")


async def main():
    parser = argparse.ArgumentParser(
        description="AI Multi-Agent Code Review Tool (Improved)")
    parser.add_argument("directory", type=str, help="Root directory to review")
    parser.add_argument("--extensions", nargs="+",
                        default=[".cpp", ".hpp", ".h", ".py"], help="File extensions to include")
    parser.add_argument("--save-dir", type=str,
                        default="reviews", help="Directory to save results")
    parser.add_argument("--models", type=str, default="models.yaml",
                        help="Optional models config file")
    parser.add_argument("--chunk-size", type=int,
                        default=DEFAULT_CHUNK_SIZE, help="Max lines per chunk")
    parser.add_argument("--chunk-threshold", type=int, default=DEFAULT_MAX_LINES,
                        help="If file exceeds this many lines, chunk it")
    args = parser.parse_args()

    console.print(
        "[bold cyan]🤖 Initializing Improved ReviewBot...[/bold cyan]")

    # Env
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        console.print(
            "[red]Error: OPENAI_API_KEY not found. Set it in your .env.[/red]")
        return

    # LLMs
    models_cfg = load_models_config(args.models)
    llms = build_llms(models_cfg)

    # Files to review
    files = list_source_files(args.directory, args.extensions)
    if not files:
        console.print(f"[yellow]No files with {args.extensions} under '{
                      args.directory}'.[/yellow]")
        return

    console.print(f"Found {len(files)} file(s).")

    for fp in files:
        await review_single_file(
            llms=llms,
            file_path=fp,
            save_dir=args.save_dir,
            chunk_size=args.chunk_size,
            max_lines_before_chunk=args.chunk_threshold
        )

if __name__ == "__main__":
    asyncio.run(main())
