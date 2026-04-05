"""Run offline evals against persisted RespondAI sessions."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.evals.runner import EvalRunner


async def _run(limit: int, session_ids: list[str]) -> None:
    runner = EvalRunner()
    summary = await runner.run(limit=limit, session_ids=session_ids or None)

    print("Eval run completed")
    print(f"- eval_run_id: {summary.eval_run_id}")
    print(f"- target_session_count: {summary.target_session_count}")
    print(f"- evaluated_session_count: {summary.evaluated_session_count}")
    print(f"- average_score: {summary.average_score}")

    if summary.session_scores:
        print("- top_sessions:")
        for item in sorted(summary.session_scores, key=lambda row: row.overall_score, reverse=True)[:5]:
            print(f"  - {item.session_id}: score={item.overall_score} passed={item.passed}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RespondAI offline evals")
    parser.add_argument("--limit", type=int, default=50, help="Max sessions to evaluate when --session-id is not set")
    parser.add_argument(
        "--session-id",
        action="append",
        dest="session_ids",
        default=[],
        help="Specific session id to evaluate (can be repeated)",
    )
    args = parser.parse_args()

    asyncio.run(_run(limit=max(1, args.limit), session_ids=args.session_ids))


if __name__ == "__main__":
    main()
