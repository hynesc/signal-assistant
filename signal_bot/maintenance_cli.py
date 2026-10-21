import argparse
from pathlib import Path

from .data_cleanup import purge_attachments, purge_message_databases


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bot maintenance utilities.")
    parser.add_argument(
        "--signal-root",
        default=str(Path(__file__).resolve().parent.parent / "signal-data"),
        help="Path to the signal-data root directory.",
    )
    parser.add_argument(
        "--purge-runtime-data",
        action="store_true",
        help="Delete attachments and purge message_send_log tables from account.db files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    signal_root = Path(args.signal_root)

    if not args.purge_runtime_data:
        return 0

    removed_attachments = purge_attachments(signal_root)
    for path in removed_attachments:
        print(f"attachment_removed {path}")

    for result in purge_message_databases(signal_root / "data"):
        if result.ok:
            print(f"db_cleared {result.path}")
        else:
            print(f"db_failed {result.path} {result.detail}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
