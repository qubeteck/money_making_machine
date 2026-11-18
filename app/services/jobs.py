from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from enum import Enum
from typing import TypeVar, Optional, Dict, Any

from app.db import session_scope
from app.models import JobRun

logger = logging.getLogger(__name__)

T = TypeVar("T")


class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobExecutionError(Exception):
    """Raised when every attempt of a retried job failed."""

    def __init__(self, attempts: int, last_error: BaseException) -> None:
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(
            f"{type(last_error).__name__}: {last_error} (after {attempts} attempt(s))"
        )


class JobQueueItem:
    """Represents a job queued for execution."""
    
    def __init__(self, job_name: str, factory: Callable[[], Awaitable[T]],
                 max_retries: int = 2, priority: int = 0):
        self.job_name = job_name
        self.factory = factory
        self.max_retries = max_retries
        self.priority = priority
        self.attempts = 0
        self.created_at = time.monotonic()
        self.scheduled_for = time.monotonic()
        self.status = JobStatus.PENDING
        self.last_error = None
        self.result = None
        self.retry_after = 0


class CircuitBreaker:
    """Circuit breaker to prevent repeated failures from flooding the system."""
    
    def __init__(self, failure_threshold: int = 3, timeout_seconds: int = 300):
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning("Circuit breaker OPENED for job after %d failures", self.failure_count)
    
    def record_success(self):
        self.failure_count = 0
        self.state = "CLOSED"
    
    def can_execute(self) -> bool:
        if self.state == "CLOSED":
            return True
        
        if self.state == "OPEN":
            if time.monotonic() - self.last_failure_time > self.timeout_seconds:
                self.state = "HALF_OPEN"
                logger.info("Circuit breaker HALF_OPEN, allowing test execution")
                return True
            return False
        
        return True  # HALF_OPEN
    
    def get_status(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "last_failure_time": self.last_failure_time,
            "timeout_seconds": self.timeout_seconds,
            "can_execute": self.can_execute()
        }


class JobManager:
    """Enhanced job manager with isolation, queuing, and circuit breaker protection."""
    
    def __init__(self):
        self.active_jobs: Dict[str, Dict] = {}
        self.job_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.job_history: Dict[str, list] = {}
        self._shutdown = False
        self._queue_processor_task: Optional[asyncio.Task] = None
    
    def register_job(self, job_name: str, factory: Callable[[], Awaitable[T]], 
                    max_retries: int = 2, priority: int = 0) -> None:
        """Register a job for execution."""
        job = JobQueueItem(job_name, factory, max_retries, priority)
        asyncio.create_task(self.job_queue.put((priority, job)))
    
    def get_circuit_breaker(self, job_name: str) -> CircuitBreaker:
        """Get or create circuit breaker for a job."""
        if job_name not in self.circuit_breakers:
            self.circuit_breakers[job_name] = CircuitBreaker()
        return self.circuit_breakers[job_name]
    
    async def process_queue(self):
        """Background task that processes the job queue."""
        while not self._shutdown:
            try:
                # Wait for next job with timeout
                priority, job = await asyncio.wait_for(
                    self.job_queue.get(), timeout=5.0
                )
                
                # Check if similar job is already running
                if self._is_job_running(job.job_name):
                    logger.info("Skipping %s - similar job already running", job.job_name)
                    job.status = JobStatus.CANCELLED
                    self.job_queue.task_done()
                    continue
                
                # Check circuit breaker
                circuit_breaker = self.get_circuit_breaker(job.job_name)
                if not circuit_breaker.can_execute():
                    logger.warning("Circuit breaker preventing execution of %s", job.job_name)
                    job.status = JobStatus.CANCELLED
                    self.job_queue.task_done()
                    continue
                
                # Execute the job
                await self._execute_job(job)
                
            except asyncio.TimeoutError:
                continue
            except Exception as exc:
                logger.error("Queue processor error: %s", exc)
    
    def _is_job_running(self, job_name: str) -> bool:
        """Check if a similar job is currently running."""
        # Check for active jobs with similar names
        for job_id, job_info in self.active_jobs.items():
            if job_info["job_name"].startswith(job_name.split('_')[0]):
                if time.monotonic() - job_info["start_time"] < 300:  # 5 minutes
                    return True
        return False
    
    async def _execute_job(self, job: JobQueueItem):
        """Execute a single job with enhanced error handling."""
        job_id = f"{job.job_name}_{int(time.time())}"
        self.active_jobs[job_id] = {
            "job_name": job.job_name,
            "start_time": time.monotonic(),
            "attempts": 0,
            "circuit_breaker": self.get_circuit_breaker(job.job_name)
        }
        
        try:
            job.status = JobStatus.RUNNING
            job.attempts += 1
            self.active_jobs[job_id]["attempts"] = job.attempts
            
            # Execute with retries
            result, attempts_used = await run_with_retries(
                job.factory,
                attempts=max(1, job.max_retries + 1),
                backoff_seconds=3.0,
            )
            
            # Success
            job.result = result
            job.status = JobStatus.COMPLETED
            circuit_breaker = self.get_circuit_breaker(job.job_name)
            circuit_breaker.record_success()
            
            logger.info("%s completed successfully after %d attempt(s)", job.job_name, attempts_used)
            
        except JobExecutionError as exc:
            # All retries failed
            job.last_error = exc
            job.status = JobStatus.FAILED
            circuit_breaker = self.get_circuit_breaker(job.job_name)
            circuit_breaker.record_failure()
            
            logger.error("%s failed after %d attempts: %s", job.job_name, exc.attempts, exc)
            
        except Exception as exc:
            # Unexpected error
            job.last_error = exc
            job.status = JobStatus.FAILED
            circuit_breaker = self.get_circuit_breaker(job.job_name)
            circuit_breaker.record_failure()
            
            logger.error("Unexpected error in %s: %s", job.job_name, exc, exc_info=True)
            
        finally:
            # Clean up
            del self.active_jobs[job_id]
            self.job_queue.task_done()
    
    def get_job_status(self, job_name: str) -> Dict[str, Any]:
        """Get status of all jobs with the given name."""
        status = {
            "job_name": job_name,
            "is_running": self._is_job_running(job_name),
            "active_instances": len([j for j in self.active_jobs.values() 
                                   if j["job_name"].startswith(job_name.split('_')[0])]),
            "circuit_breaker": self.get_circuit_breaker(job_name).get_status(),
            "queue_size": self.job_queue.qsize() if hasattr(self.job_queue, 'qsize') else 0
        }
        return status
    
    def get_all_jobs_status(self) -> Dict[str, Any]:
        """Get status of all jobs."""
        return {
            "active_jobs": len(self.active_jobs),
            "circuit_breakers": {name: cb.get_status() for name, cb in self.circuit_breakers.items()},
            "queue_size": self.job_queue.qsize() if hasattr(self.job_queue, 'qsize') else 0
        }
    
    async def shutdown(self):
        """Shutdown the job manager gracefully."""
        self._shutdown = True
        if self._queue_processor_task:
            self._queue_processor_task.cancel()
            try:
                await self._queue_processor_task
            except asyncio.CancelledError:
                pass


# Global job manager instance
_job_manager = None
_job_manager_lock = asyncio.Lock()


async def get_job_manager() -> JobManager:
    """Get or create the global job manager instance."""
    global _job_manager
    async with _job_manager_lock:
        if _job_manager is None:
            _job_manager = JobManager()
            _job_manager._queue_processor_task = asyncio.create_task(_job_manager.process_queue())
        return _job_manager


async def register_scheduled_job(job_name: str, factory: Callable[[], Awaitable[T]],
                                 max_retries: int = 2, priority: int = 0) -> None:
    """Register a job with the job manager."""
    manager = await get_job_manager()
    manager.register_job(job_name, factory, max_retries, priority)


async def get_job_status(job_name: str) -> Dict[str, Any]:
    """Get status of a specific job."""
    manager = await get_job_manager()
    return manager.get_job_status(job_name)


async def get_all_jobs_status() -> Dict[str, Any]:
    """Get status of all jobs."""
    manager = await get_job_manager()
    return manager.get_all_jobs_status()


# Keep existing functions for backward compatibility
async def run_with_retries(
    factory: Callable[[], Awaitable[T]],
    *,
    attempts: int = 1,
    backoff_seconds: float = 0.0,
) -> tuple[T, int]:
    """Run an async job factory, retrying failures with linear backoff.

    Returns the result and the number of attempts used. Raises
    :class:`JobExecutionError` when the final attempt fails so callers can
    persist the attempt count and send one failure alert.
    """
    total = max(1, int(attempts))
    delay = max(0.0, float(backoff_seconds))
    for attempt in range(1, total + 1):
        try:
            return await factory(), attempt
        except Exception as exc:
            if attempt >= total:
                raise JobExecutionError(attempt, exc) from exc
            wait = delay * attempt
            logger.warning(
                "Job attempt %s/%s failed (%s); retrying in %.1fs",
                attempt,
                total,
                exc,
                wait,
            )
            if wait > 0:
                await asyncio.sleep(wait)
    raise AssertionError("unreachable: retry loop exhausted without a result")


def record_job_run(
    job_name: str,
    started_at: datetime,
    status: str,
    message: str = "",
    duration_seconds: float = 0.0,
    attempts: int = 1,
) -> None:
    """Persist a job outcome so failures can be inspected from the dashboard/API."""
    with session_scope() as db:
        db.add(
            JobRun(
                job_name=job_name,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                status=status,
                message=(message or "")[:4000],
                duration_seconds=round(float(duration_seconds), 4),
                attempts=max(1, int(attempts)),
            )
        )
