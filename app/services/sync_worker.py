from __future__ import annotations

import asyncio
from contextlib import suppress

from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.models import Batch, BatchItem, BatchStatus, Serial
from app.services.settings import get_all_settings, is_tally_enabled
from app.services.tally import sync_batch


WORKER_STATE_KEY = "setu_retry_worker_task"


def retry_pending_batches(limit: int = 10) -> int:
    with SessionLocal() as db:
        if not is_tally_enabled(db):
            return 0
        batches = db.scalars(
            select(Batch)
            .where(Batch.status == BatchStatus.PENDING_SYNC.value)
            .order_by(Batch.last_retry_at.is_not(None), Batch.last_retry_at, Batch.created_at)
            .limit(limit)
            .options(selectinload(Batch.items).selectinload(BatchItem.serial).selectinload(Serial.product))
        ).all()
        for batch in batches:
            sync_batch(db, batch)
        return len(batches)


async def retry_worker_loop() -> None:
    while True:
        interval = 180
        with SessionLocal() as db:
            settings = get_all_settings(db)
            try:
                interval = max(30, int(settings.get("retry_interval_seconds", "180")))
            except ValueError:
                interval = 180
        await asyncio.sleep(interval)
        await asyncio.to_thread(retry_pending_batches)


def start_retry_worker(app: FastAPI) -> None:
    if getattr(app.state, WORKER_STATE_KEY, None):
        return
    setattr(app.state, WORKER_STATE_KEY, asyncio.create_task(retry_worker_loop()))


async def stop_retry_worker(app: FastAPI) -> None:
    task = getattr(app.state, WORKER_STATE_KEY, None)
    if not task:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    setattr(app.state, WORKER_STATE_KEY, None)
