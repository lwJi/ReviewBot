# agents.py
from langchain_core.output_parsers import StrOutputParser
from prompts import WORKER_PROMPT, SUPERVISOR_PROMPT


async def run_worker_agent(llm, code: str) -> str:
    """Runs a worker agent to review the given code."""
    chain = WORKER_PROMPT | llm | StrOutputParser()
    review = await chain.ainvoke({"code": code})
    return review


async def run_supervisor_agent(llm, code: str, worker_reviews: list[str]) -> str:
    """Runs the supervisor agent to select the best review."""

    # Format the reviews for the supervisor prompt
    formatted_reviews = ""
    for i, review in enumerate(worker_reviews):
        formatted_reviews += f"--- Review {i+1} ---\n{review}\n\n"

    chain = SUPERVISOR_PROMPT | llm | StrOutputParser()
    decision = await chain.ainvoke({
        "code": code,
        "reviews": formatted_reviews
    })
    return decision
