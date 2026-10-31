"""Fargate entry point. The orchestrator owns heartbeat and pipeline error handling."""

import argparse
import asyncio
import logging


async def run(job_id: str, mode: str) -> int:
    from bob.config import get_settings
    from bob.core.backends import get_runner, get_store
    from bob.core.models import JobStatus
    from bob.orchestrator import Orchestrator

    if get_settings().env != "aws":
        raise RuntimeError("the Fargate worker requires BOB_ENV=aws")
    runner = get_runner()
    try:
        await Orchestrator(runner=runner).run_job(job_id, mode)
        job = await get_store().get_job(job_id)
        return 1 if job.status == JobStatus.error else 0
    finally:
        await runner.release(job_id)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Run one Bob job on Fargate")
    parser.add_argument("job_id")
    parser.add_argument("mode", choices=("create", "resync"))
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.job_id, args.mode)))


if __name__ == "__main__":
    main()
