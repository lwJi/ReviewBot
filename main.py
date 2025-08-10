# main.py
import os
import argparse
import asyncio
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from agents import run_worker_agent, run_supervisor_agent


async def review_file(llms, filepath: str):
    """
    Reads a single file and runs the full review process on it.
    """
    print("\n" + "="*80)
    print(f"📄 Reviewing file: {filepath}")
    print("="*80)

    # 1. Read the code from the specified file
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            code_to_review = f.read()
    except Exception as e:
        print(f"Error reading file {filepath}: {e}")
        return

    # 2. Run worker agents in parallel
    print("🔬 Analyzing code with 2 worker agents...")
    worker_tasks = [
        run_worker_agent(llms['worker1'], code_to_review),
        run_worker_agent(llms['worker2'], code_to_review)
    ]
    worker_reviews = await asyncio.gather(*worker_tasks)

    # 3. Run the supervisor agent
    print("🧐 Supervisor is now evaluating the reviews...")
    final_decision = await run_supervisor_agent(llms['supervisor'], code_to_review, worker_reviews)

    # 4. Print the final result for the file
    print("\n" + "-"*50)
    print(f"🎉 Final Decision for {os.path.basename(filepath)} 🎉")
    print("-"*50 + "\n")
    print(final_decision)


async def main(directory: str, extensions: list[str]):
    """
    Main function to discover files and orchestrate the code review process.
    """
    print("🤖 Initializing AI Code Reviewer for Directory...")

    # Load environment variables
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not found. Please set it in your .env file.")
        return

    # Define the LLMs for the agents
    llms = {
        'worker1': ChatOpenAI(model="gpt-3.5-turbo", temperature=0.7),
        'worker2': ChatOpenAI(model="gpt-4o", temperature=0.2),
        'supervisor': ChatOpenAI(model="gpt-4o", temperature=0.1)
    }

    # Find all files with the specified extensions
    files_to_review = []
    for root, _, files in os.walk(directory):
        for file in files:
            if any(file.endswith(ext) for ext in extensions):
                files_to_review.append(os.path.join(root, file))

    if not files_to_review:
        print(f"No files with extensions {extensions} found in '{directory}'.")
        return

    print(f"Found {len(files_to_review)} files to review: {files_to_review}")

    # Review each file sequentially
    for filepath in files_to_review:
        await review_file(llms, filepath)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AI Multi-Agent Code Review Tool for Directories")
    parser.add_argument("directory", type=str,
                        help="The path to the source directory to review.")
    parser.add_argument(
        "--extensions",
        nargs='+',
        default=['.cpp', '.hpp', '.h'],
        help="A list of file extensions to review (e.g., .cpp .hpp .h)"
    )
    args = parser.parse_args()

    asyncio.run(main(args.directory, args.extensions))
