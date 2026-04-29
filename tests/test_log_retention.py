# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Tests for log retention and GDPR compliance."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock

from app.services.log_retention import LogRetentionPolicy, get_retention_policy


def test_retention_policy_initialization():
    """LogRetentionPolicy initializes with correct retention days."""
    policy = LogRetentionPolicy(retention_days=7)
    assert policy.retention_days == 7
    assert policy.cleanup_interval_hours == 24


def test_retention_cutoff_calculation():
    """Retention policy calculates correct cutoff datetime."""
    policy = LogRetentionPolicy(retention_days=7)
    cutoff = policy.get_retention_cutoff()
    
    # Cutoff should be approximately 7 days in the past
    expected_cutoff = datetime.utcnow() - timedelta(days=7)
    delta = abs((cutoff - expected_cutoff).total_seconds())
    
    assert delta < 2, "Cutoff calculation is off by more than 2 seconds"


def test_custom_retention_days():
    """LogRetentionPolicy supports custom retention periods."""
    policy = LogRetentionPolicy(retention_days=14)
    cutoff = policy.get_retention_cutoff()
    
    # Cutoff should be approximately 14 days in the past
    expected_cutoff = datetime.utcnow() - timedelta(days=14)
    delta = abs((cutoff - expected_cutoff).total_seconds())
    
    assert delta < 2


@pytest.mark.asyncio
async def test_cleanup_old_logs():
    """cleanup_old_logs deletes jobs older than retention period."""
    policy = LogRetentionPolicy(retention_days=7)
    
    # Mock job_store
    mock_store = AsyncMock()
    mock_store.delete_jobs_before = AsyncMock(return_value=42)
    
    deleted = await policy.cleanup_old_logs(mock_store)
    
    assert deleted == 42
    mock_store.delete_jobs_before.assert_called_once()
    
    # Verify the cutoff passed was approximately 7 days ago
    call_args = mock_store.delete_jobs_before.call_args
    cutoff_arg = call_args[0][0]
    expected = datetime.utcnow() - timedelta(days=7)
    delta = abs((cutoff_arg - expected).total_seconds())
    assert delta < 2


def test_global_retention_policy():
    """get_retention_policy returns global singleton."""
    policy1 = get_retention_policy()
    policy2 = get_retention_policy()
    
    assert policy1 is policy2
    assert policy1.retention_days == 7


@pytest.mark.asyncio
async def test_cleanup_task_lifecycle():
    """Cleanup task can be started and stopped."""
    policy = LogRetentionPolicy(retention_days=7, cleanup_interval_hours=1)
    mock_store = AsyncMock()
    mock_store.delete_jobs_before = AsyncMock(return_value=0)
    
    # Start cleanup task (should not block)
    await policy.start_cleanup_task(mock_store)
    assert policy.cleanup_task is not None
    
    # Stop cleanup task
    await policy.stop_cleanup_task()
    assert policy.cleanup_task.done() or policy.cleanup_task.cancelled()
