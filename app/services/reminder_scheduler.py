"""Persistent Reminder Scheduler & Notification Delivery Worker."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Callable, Dict, List, Optional

from app.core.config import settings
from app.storage.database import get_session
from app.storage.models import ReminderModel

logger = logging.getLogger(__name__)


class ReminderScheduler:
    """
    Background worker that reliably discovers, claims, and delivers due reminders.
    Supports restart recovery, bounded retry counts, truthful delivery status,
    and duplicate delivery suppression.
    """

    def __init__(self, poll_interval_s: float = 10.0, max_retries: int = 3):
        self.poll_interval_s = poll_interval_s
        self.max_retries = max_retries
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._custom_adapters: Dict[str, Callable[[ReminderModel], None]] = {}

    def register_channel_adapter(self, channel: str, adapter: Callable[[ReminderModel], None]) -> None:
        """Register a delivery handler for a specific notification channel."""
        self._custom_adapters[channel.upper()] = adapter

    def recover_stale_delivering_reminders(self, timeout_seconds: int = 300) -> int:
        """
        Recover reminders left in DELIVERING state due to a worker crash or restart.
        If delivery_attempts < max_retries, resets to PENDING; otherwise marks FAILED.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)
        recovered = 0
        with get_session() as session:
            stale_records = (
                session.query(ReminderModel)
                .filter(
                    ReminderModel.status == "DELIVERING",
                    (ReminderModel.last_attempt_at <= cutoff) | (ReminderModel.last_attempt_at.is_(None)),
                )
                .all()
            )
            for rec in stale_records:
                recovered += 1
                if rec.delivery_attempts < self.max_retries:
                    rec.status = "PENDING"
                    rec.delivery_error = "Recovered from interrupted delivery attempt."
                else:
                    rec.status = "FAILED"
                    rec.delivery_error = "Delivery failed: maximum attempts reached after crash recovery."
            if recovered > 0:
                logger.warning("Recovered %d stale DELIVERING reminders from previous crash.", recovered)
        return recovered

    def poll_and_deliver_due_reminders(self, current_time: Optional[datetime] = None) -> List[str]:
        """
        Scan for due pending reminders, atomically claim each job, and deliver notifications.
        Returns list of successfully delivered reminder IDs.
        """
        now = current_time or datetime.now(timezone.utc)
        delivered_ids: List[str] = []

        with get_session() as session:
            # Discover due reminders
            due_records = (
                session.query(ReminderModel)
                .filter(
                    ReminderModel.status == "PENDING",
                    ReminderModel.due_date <= now,
                )
                .all()
            )

            for rec in due_records:
                rid = rec.reminder_id
                # Atomic Claim: transition to DELIVERING
                claimed = (
                    session.query(ReminderModel)
                    .filter(
                        ReminderModel.reminder_id == rid,
                        ReminderModel.status == "PENDING",
                    )
                    .update(
                        {
                            "status": "DELIVERING",
                            "delivery_attempts": ReminderModel.delivery_attempts + 1,
                            "last_attempt_at": now,
                        },
                        synchronize_session="fetch",
                    )
                )

                if claimed == 0:
                    continue  # Raced with another worker

                # Execute delivery through channel
                try:
                    self._deliver_notification(rec)
                    rec.status = "DELIVERED"
                    rec.delivered_at = now
                    rec.delivery_error = None
                    delivered_ids.append(rid)
                    logger.info("Successfully delivered reminder '%s' (ID: %s)", rec.title, rid)
                except Exception as exc:
                    logger.error("Failed delivering reminder '%s' (ID: %s): %s", rec.title, rid, exc)
                    rec.delivery_error = str(exc)
                    if rec.delivery_attempts < self.max_retries:
                        rec.status = "PENDING"  # Requeue for retry
                    else:
                        rec.status = "FAILED"

        return delivered_ids

    def _deliver_notification(self, reminder: ReminderModel) -> None:
        """
        Deliver reminder to configured channel.
        Supported channels: CLI, LOCAL, or registered adapter.
        Unsupported channels raise NotImplementedError to fail truthfully.
        """
        channel = (reminder.delivery_channel or "CLI").upper()
        if channel in ("CLI", "LOCAL"):
            logger.info(
                "[REMINDER NOTIFICATION] Tenant: %s | Title: '%s' | Scheduled: %s",
                reminder.user_id,
                reminder.title,
                reminder.due_date,
            )
        elif channel in self._custom_adapters:
            self._custom_adapters[channel](reminder)
        else:
            raise NotImplementedError(
                f"Delivery channel '{channel}' is not supported or not configured."
            )

    def _worker_loop(self) -> None:
        """Periodic background execution loop."""
        while self._running:
            try:
                self.poll_and_deliver_due_reminders()
            except Exception as e:
                logger.error("Error in reminder scheduler worker loop: %s", e)
            time.sleep(self.poll_interval_s)

    def start(self) -> None:
        """Start background polling thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="ReminderScheduler")
        self._thread.start()
        logger.info("Started background ReminderScheduler thread.")

    def stop(self) -> None:
        """Stop background polling thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("Stopped background ReminderScheduler thread.")


# Global default scheduler singleton
reminder_scheduler = ReminderScheduler()
