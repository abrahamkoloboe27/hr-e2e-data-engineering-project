from __future__ import annotations

import argparse
import logging

from config.settings import GenerationSettings, load_mongo_settings
from db.mongo import get_database
from generators.hr_pipeline import HRDataPipeline
from utils.logging_utils import configure_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic HR ecosystem data into MongoDB Atlas")
    parser.add_argument("--employees", type=int, default=500, help="Number of employees to generate")
    parser.add_argument("--batch-size", type=int, default=5000, help="Batch size for generation and insertion")
    parser.add_argument("--seed", type=int, default=42, help="Seed for reproducibility")
    parser.add_argument("--retry-count", type=int, default=3, help="Insert retry attempts")
    parser.add_argument("--payroll-months", type=int, default=6, help="Payroll months generated per employee")
    parser.add_argument("--resume", action="store_true", help="Resume generation by skipping populated collections")
    parser.add_argument("--drop-existing", action="store_true", help="Drop target collections before generation")
    return parser.parse_args()


def main() -> int:
    configure_logging()
    args = parse_args()

    if args.employees <= 0:
        raise ValueError("--employees must be > 0")
    if args.batch_size <= 0:
        raise ValueError("--batch-size must be > 0")

    settings = GenerationSettings(
        employees=args.employees,
        batch_size=args.batch_size,
        seed=args.seed,
        retry_count=args.retry_count,
        payroll_months=args.payroll_months,
        resume=args.resume,
        drop_existing=args.drop_existing,
    )

    db = get_database(load_mongo_settings())
    logging.info("Connected to MongoDB")
    pipeline = HRDataPipeline(db=db, settings=settings)
    pipeline.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
