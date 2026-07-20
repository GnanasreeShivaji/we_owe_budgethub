"""Long-running stdlib worker for automatic scheduled reminder delivery."""

import logging
import os
import time

from app import create_app
from app.reminders.routes import dispatch_due_reminders


def main():
    interval = max(15, int(os.environ.get("REMINDER_WORKER_INTERVAL", "60")))
    app = create_app()
    logging.basicConfig(level=logging.INFO)
    logging.info("Reminder worker started; checking every %s seconds", interval)
    while True:
        with app.app_context():
            count = dispatch_due_reminders()
            if count:
                logging.info("Processed %s due reminders", count)
        time.sleep(interval)


if __name__ == "__main__":
    main()
