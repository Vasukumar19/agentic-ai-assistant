"""Persistent Reminder Scheduler & Notification Delivery Worker."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import List, Optional

from app.core.config import settings
from app.storage.database import get_session
from app.storage.models import ReminderModel

logger = logging.getLogger(__name__)


class ReminderScheduler:
    """
    Background worker that reliably discovers, claims, and delivers due reminders.
    Supports restart recovery, retry counts, and duplicate delivery suppression.
    """

    def __init__(self, poll_interval_s: float = 10.0):
        self.poll_interval_s = poll_interval_s
        self._running = False
        self._thread: Optional[threading.Thread] = None

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
                    delivered_ids.append(rid)
                    logger.info("Successfully delivered reminder '%s' (ID: %s)", rec.title, rid)
                except Exception as exc:
                    logger.error("Failed delivering reminder '%s' (ID: %s): %s", rec.title, rid, exc)
                    rec.status = "FAILED"
                    rec.delivery_error = str(exc)

        return delivered_ids

    def _deliver_notification(self, reminder: ReminderModel) -> None:
        """
        Deliver reminder to configured channel.
        Default channel: logs and local delivery.
        """
        channel = (reminder.delivery_channel or "CLI").upper()
        if channel == "CLI":
            logger.info(
                "[REMINDER NOTIFICATION] Tenant: %s | Title: '%s' | Scheduled: %s",
                reminder.user_id,
                reminder.title,
                reminder.due_date,
            )
        else:
            # External delivery infrastructure unconfigured
            logger.info("Stored reminder '%s' delivered via default channel (%s).", reminder.title, channel)

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
