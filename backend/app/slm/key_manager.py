"""
Adaptive Rate-Aware API Key Manager for ZTA.

Production-grade key rotation with:
- Proactive load distribution across all keys
- Per-key usage tracking with sliding window
- Smart routing to key with most remaining capacity
- Backpressure handling when approaching limits
- Automatic recovery after cooldown periods

Thread-safe implementation for concurrent request handling.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_REQUESTS_PER_MINUTE = 50  # Conservative default for NVIDIA free tier
DEFAULT_COOLDOWN_SECONDS = 60
DEFAULT_WINDOW_SECONDS = 60
SAFETY_MARGIN_PERCENT = 0.15  # Reserve 15% capacity as buffer


@dataclass
class KeyState:
    """Tracks the state of a single API key."""

    index: int
    request_timestamps: deque = field(default_factory=lambda: deque(maxlen=1000))
    cooldown_until: float = 0.0
    consecutive_errors: int = 0
    total_requests: int = 0
    total_rate_limits: int = 0

    def is_available(self, now: float) -> bool:
        """Check if key is available (not in cooldown)."""
        return now >= self.cooldown_until

    def get_requests_in_window(self, now: float, window_seconds: int) -> int:
        """Count requests made within the sliding window."""
        cutoff = now - window_seconds
        # Clean old timestamps and count recent ones
        while self.request_timestamps and self.request_timestamps[0] < cutoff:
            self.request_timestamps.popleft()
        return len(self.request_timestamps)

    def record_request(self, now: float) -> None:
        """Record that a request was made with this key."""
        self.request_timestamps.append(now)
        self.total_requests += 1
        self.consecutive_errors = 0  # Reset on successful use

    def mark_rate_limited(self, now: float, cooldown_seconds: int) -> None:
        """Mark this key as rate-limited."""
        self.cooldown_until = now + cooldown_seconds
        self.consecutive_errors += 1
        self.total_rate_limits += 1


class AdaptiveKeyManager:
    """
    Production-grade API key manager with adaptive load balancing.

    Features:
    - Distributes requests across all keys proactively
    - Tracks usage per key with sliding window
    - Routes to key with most remaining capacity
    - Handles rate limits gracefully with cooldown
    - Provides comprehensive monitoring data
    """

    def __init__(
        self,
        api_keys: list[str],
        requests_per_minute: int = DEFAULT_REQUESTS_PER_MINUTE,
        cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
    ) -> None:
        if not api_keys:
            raise ValueError("At least one API key is required")

        self._keys = api_keys
        self._requests_per_minute = requests_per_minute
        self._cooldown_seconds = cooldown_seconds
        self._window_seconds = window_seconds
        self._effective_limit = int(requests_per_minute * (1 - SAFETY_MARGIN_PERCENT))

        # Initialize state for each key
        self._key_states: list[KeyState] = [
            KeyState(index=i) for i in range(len(api_keys))
        ]
        self._lock = threading.Lock()
        self._round_robin_index = 0  # For tie-breaking

        logger.info(
            f"AdaptiveKeyManager initialized: {len(api_keys)} keys, "
            f"{requests_per_minute} req/min limit (effective: {self._effective_limit})"
        )

    @property
    def total_keys(self) -> int:
        """Return total number of configured API keys."""
        return len(self._keys)

    def get_best_key(self) -> tuple[str, int]:
        """
        Get the best available API key based on remaining capacity.

        Returns:
            Tuple of (api_key, key_index)

        Raises:
            RuntimeError: If all keys are exhausted or rate-limited
        """
        with self._lock:
            now = time.time()
            return self._select_best_key(now)

    def _select_best_key(self, now: float) -> tuple[str, int]:
        """Select the key with most remaining capacity (must hold lock)."""
        best_key_idx: int | None = None
        best_capacity = -1
        all_in_cooldown = True
        min_cooldown_remaining = float("inf")
        min_cooldown_idx = 0

        for state in self._key_states:
            if state.is_available(now):
                all_in_cooldown = False
                capacity = self._get_remaining_capacity(state, now)

                if capacity > best_capacity:
                    best_capacity = capacity
                    best_key_idx = state.index
                elif capacity == best_capacity and capacity > 0:
                    # Tie-breaker: use round-robin among equal capacity keys
                    if self._is_next_in_rotation(state.index):
                        best_key_idx = state.index
            else:
                # Track shortest cooldown for error message
                remaining = state.cooldown_until - now
                if remaining < min_cooldown_remaining:
                    min_cooldown_remaining = remaining
                    min_cooldown_idx = state.index

        if all_in_cooldown:
            raise RuntimeError(
                f"All {len(self._keys)} API keys are rate-limited. "
                f"Shortest wait: {int(min_cooldown_remaining)}s (key {min_cooldown_idx + 1})"
            )

        if best_key_idx is None or best_capacity <= 0:
            # All available keys are at capacity - find one approaching limit
            # but still technically available
            for state in self._key_states:
                if state.is_available(now):
                    best_key_idx = state.index
                    logger.warning(
                        f"All keys near capacity, using key {best_key_idx + 1} "
                        f"(capacity: {self._get_remaining_capacity(state, now)})"
                    )
                    break

        if best_key_idx is None:
            raise RuntimeError("No API keys available")

        # Update round-robin index for next tie-break
        self._round_robin_index = (best_key_idx + 1) % len(self._keys)

        return self._keys[best_key_idx], best_key_idx

    def _get_remaining_capacity(self, state: KeyState, now: float) -> int:
        """Calculate remaining request capacity for a key."""
        used = state.get_requests_in_window(now, self._window_seconds)
        remaining = self._effective_limit - used
        return max(0, remaining)

    def _is_next_in_rotation(self, index: int) -> bool:
        """Check if this index is next in round-robin rotation."""
        return index == self._round_robin_index

    def record_request(self, key_index: int) -> None:
        """Record that a request was made with the specified key."""
        with self._lock:
            now = time.time()
            self._key_states[key_index].record_request(now)

    def mark_rate_limited(
        self, key_index: int, cooldown_seconds: int | None = None
    ) -> None:
        """
        Mark a key as rate-limited.

        Args:
            key_index: Index of the key that hit rate limit
            cooldown_seconds: Optional override for cooldown period
        """
        cooldown = cooldown_seconds if cooldown_seconds is not None else self._cooldown_seconds

        with self._lock:
            now = time.time()
            state = self._key_states[key_index]
            state.mark_rate_limited(now, cooldown)

            logger.warning(
                f"API key {key_index + 1}/{len(self._keys)} hit rate limit "
                f"(total: {state.total_rate_limits}), cooldown for {cooldown}s"
            )

    def _get_total_capacity_unlocked(self, now: float) -> dict[str, int]:
        """Get aggregate capacity (caller must hold lock)."""
        available_keys = 0
        total_remaining = 0
        total_used = 0

        for state in self._key_states:
            if state.is_available(now):
                available_keys += 1
                remaining = self._get_remaining_capacity(state, now)
                used = state.get_requests_in_window(now, self._window_seconds)
                total_remaining += remaining
                total_used += used

        return {
            "available_keys": available_keys,
            "total_keys": len(self._keys),
            "total_remaining_capacity": total_remaining,
            "total_used_in_window": total_used,
            "effective_limit_per_key": self._effective_limit,
            "max_capacity": self._effective_limit * len(self._keys),
        }

    def get_total_capacity(self) -> dict[str, int]:
        """Get aggregate capacity across all keys."""
        with self._lock:
            now = time.time()
            return self._get_total_capacity_unlocked(now)

    def get_status(self) -> dict[str, Any]:
        """Get comprehensive status of all keys for monitoring."""
        with self._lock:
            now = time.time()
            keys_status = []

            for state in self._key_states:
                used = state.get_requests_in_window(now, self._window_seconds)
                remaining = self._get_remaining_capacity(state, now)
                is_available = state.is_available(now)

                key_info: dict[str, Any] = {
                    "index": state.index + 1,
                    "available": is_available,
                    "requests_in_window": used,
                    "remaining_capacity": remaining,
                    "capacity_percent": round(
                        (remaining / self._effective_limit) * 100, 1
                    ) if self._effective_limit > 0 else 0,
                    "total_requests": state.total_requests,
                    "total_rate_limits": state.total_rate_limits,
                    "consecutive_errors": state.consecutive_errors,
                }

                if not is_available:
                    key_info["cooldown_remaining_seconds"] = int(
                        state.cooldown_until - now
                    )

                keys_status.append(key_info)

            # Sort by remaining capacity (highest first) for easy reading
            keys_status.sort(key=lambda k: k["remaining_capacity"], reverse=True)

            return {
                "strategy": "adaptive_rate_aware",
                "total_keys": len(self._keys),
                "requests_per_minute_limit": self._requests_per_minute,
                "effective_limit_per_key": self._effective_limit,
                "window_seconds": self._window_seconds,
                "cooldown_seconds": self._cooldown_seconds,
                "keys": keys_status,
                "aggregate": self._get_total_capacity_unlocked(now),
            }

    # Legacy compatibility methods
    def get_current_key(self) -> str:
        """Legacy method - returns best available key."""
        key, _ = self.get_best_key()
        return key


# Alias for backward compatibility
APIKeyManager = AdaptiveKeyManager

# Global key manager instance (lazily initialized)
_key_manager: AdaptiveKeyManager | None = None
_key_manager_lock = threading.Lock()


def get_key_manager(
    api_keys: list[str] | None = None,
    requests_per_minute: int = DEFAULT_REQUESTS_PER_MINUTE,
) -> AdaptiveKeyManager | None:
    """
    Get or create the global API key manager.

    Args:
        api_keys: List of API keys. Required on first call.
        requests_per_minute: Rate limit per key per minute.

    Returns:
        AdaptiveKeyManager instance, or None if no keys configured.
    """
    global _key_manager

    if _key_manager is not None:
        return _key_manager

    with _key_manager_lock:
        if _key_manager is not None:
            return _key_manager

        if not api_keys:
            return None

        _key_manager = AdaptiveKeyManager(
            api_keys=api_keys,
            requests_per_minute=requests_per_minute,
        )
        return _key_manager


def reset_key_manager() -> None:
    """Reset the global key manager (for testing purposes)."""
    global _key_manager
    with _key_manager_lock:
        _key_manager = None
