"""Scheduler wrapper for the AI Intelligence Dashboard.

Wraps ``APScheduler`` ``BlockingScheduler`` with an ``IntervalTrigger``
so the pipeline runs automatically on a configurable interval.  Timeouts
are handled by removing the timed-out job and re-adding it at the normal
interval.
"""

from __future__ import annotations

import logging
import sys
import threading

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.job import Job
from apscheduler.schedulers.blocking import BlockingScheduler

from backend.config.config_loader import AppConfig

logger = logging.getLogger(__name__)


class PipelineScheduler:
    """Wraps a blocking APScheduler that runs the pipeline periodically.

    Parameters
    ----------
    config:
        Fully validated application configuration.
    pipeline_runner:
        A callable ``run(dry_run=False)`` that executes the pipeline.
    """

    def __init__(
        self,
        config: AppConfig,
        pipeline_runner: object,
    ) -> None:
        self._config = config
        self._pipeline_runner = pipeline_runner
        self._scheduler: BlockingScheduler | None = None
        self._job: Job | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the scheduler and block forever.

        The pipeline runs immediately on start, then repeats at the
        configured interval.  The scheduler catches job errors and
        timeouts, logs them, and re-adds the job at the normal interval.
        """
        interval = self._config.run_interval_minutes

        executors = {"default": ThreadPoolExecutor(1)}
        self._scheduler = BlockingScheduler(executors=executors)

        # Run once immediately, then on interval.
        self._schedule_run(delay_seconds=0)
        self._job = self._scheduler.add_job(
            self._wrapped_run,
            trigger="interval",
            minutes=interval,
            id="pipeline",
            replace_existing=True,
            name=f"pipeline-every-{interval}m",
        )

        self._scheduler.add_listener(
            self._on_job_event,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR,
        )

        logger.info(
            "Scheduler started — interval=%d minute(s)", interval
        )

        try:
            self._scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped via interrupt.")

    def stop(self) -> None:
        """Shut down the scheduler gracefully."""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler shut down.")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _schedule_run(self, delay_seconds: int = 0) -> None:
        """Schedule a single pipeline run, optionally delayed."""
        if self._scheduler is None:
            return
        self._scheduler.add_job(
            self._wrapped_run,
            trigger="date",
            run_date=None,  # "now"
            id="pipeline-now",
            replace_existing=True,
        )

    def _wrapped_run(self) -> None:
        """Execute the pipeline, catching and logging all errors."""
        with self._lock:
            try:
                logger.info("Scheduled pipeline run starting...")
                getattr(self._pipeline_runner, "run")(dry_run=False)
                logger.info("Scheduled pipeline run completed.")
            except Exception as exc:
                logger.error(
                    "Scheduled pipeline run failed: %s", exc, exc_info=True
                )

    def _on_job_event(self, event) -> None:
        """Handle job execution and error events."""
        if event.exception:
            logger.error(
                "Job %r raised an exception: %s",
                event.job_id,
                event.exception,
            )

        # If the job was removed due to timeout or error, re-add it.
        if event.job_id == "pipeline" and event.code != 0:
            with self._lock:
                self._job = self._scheduler.add_job(
                    self._wrapped_run,
                    trigger="interval",
                    minutes=self._config.run_interval_minutes,
                    id="pipeline",
                    replace_existing=True,
                    name=f"pipeline-every-{self._config.run_interval_minutes}m",
                )
                logger.info("Re-added pipeline job after event.")
