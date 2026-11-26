"""Celery tasks for long-running route-safety analyses."""

from __future__ import annotations

import logging

from celery import shared_task

from core.services.analysis import process_analysis

logger = logging.getLogger(__name__)


@shared_task(name="core.process_analysis", bind=True, max_retries=0)
def process_analysis_task(self, analysis_id: str) -> None:
    """Execute an analysis job and persist its terminal state."""

    logger.info("analysis_task_started", extra={"analysis_id": analysis_id})
    process_analysis(analysis_id)
    logger.info("analysis_task_finished", extra={"analysis_id": analysis_id})
