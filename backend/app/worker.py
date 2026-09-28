"""独立 worker 入口：回收过期 lease 并 claim 执行。

用法:
  cd backend && python -m app.worker
"""
from __future__ import annotations

import asyncio
import logging
import signal

from app.database import async_session, init_db
from app.services.task_queue import MAX_PARALLEL, dispatch_queue
from app.services.task_service import recover_expired_leases, worker_id

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker")

_stop = False


def _handle_stop(*_args):
    global _stop
    _stop = True


async def worker_loop(poll_seconds: float = 1.0) -> None:
    wid = worker_id()
    log.info("worker started id=%s max_parallel=%s", wid, MAX_PARALLEL)
    while not _stop:
        async with async_session() as db:
            n = await recover_expired_leases(db)
            if n:
                log.info("recovered %s expired leases", n)
            await db.commit()
        await dispatch_queue()
        await asyncio.sleep(poll_seconds)
    log.info("worker stopped")


def main():
    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)
    asyncio.run(_bootstrap())


async def _bootstrap():
    await init_db()
    await worker_loop()


if __name__ == "__main__":
    main()
