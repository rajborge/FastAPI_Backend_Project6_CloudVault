"""Run exactly one scheduler, independent of API process count."""

import signal
import threading

from sqlalchemy import text

from app.db.database import engine
from app.schedular.cleanup_schedular import start_schedular, stop_schedular


def main():
    stopped = threading.Event()
    for name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(name, lambda *_: stopped.set())
    with engine.connect() as connection:
        if not connection.execute(
            text("SELECT pg_try_advisory_lock(791421019)")
        ).scalar():
            raise RuntimeError("Another CloudVault scheduler is already running.")
        connection.commit()
        start_schedular()
        try:
            while not stopped.wait(30):
                # Lose the scheduler if the connection owning the lock dies.
                connection.execute(text("SELECT 1"))
                connection.commit()
        finally:
            stop_schedular()


if __name__ == "__main__":
    main()
