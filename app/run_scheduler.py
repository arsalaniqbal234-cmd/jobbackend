import signal
import threading

from app.observability import setup_monitoring
from app.scheduler import scheduler, start_scheduler

if __name__ == "__main__":
    setup_monitoring()
    stopped = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    start_scheduler()
    try:
        stopped.wait()
    finally:
        scheduler.shutdown(wait=True)
