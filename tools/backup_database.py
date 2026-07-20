"""Create a consistent SQLite backup without stopping the application."""
import argparse
import sqlite3
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="instance/we_owe.db")
    parser.add_argument("--destination", default=None)
    args = parser.parse_args()
    source = Path(args.source).resolve()
    destination = Path(args.destination).resolve() if args.destination else source.parent / "backups" / f"we_owe-{datetime.now():%Y%m%d-%H%M%S}.db"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as original, sqlite3.connect(destination) as backup:
        original.backup(backup)
    print(destination)


if __name__ == "__main__":
    main()
