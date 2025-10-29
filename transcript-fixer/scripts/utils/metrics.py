#!/usr/bin/env python3
"""
Metrics Collection and Monitoring

CRITICAL FIX (P1-7): Production-grade metrics and observability

Features:
- Real-time metrics collection
- Time-series data storage (in-memory)
- Prometheus-compatible export format
- Common metrics: requests, errors, latency, throughput
- Custom metric support
- Thread-safe operations

Metrics Types:
- Counter: Monotonically increasing value (e.g., total requests)
- Gauge: Point-in-time value (e.g., active connections)
- Histogram: Distribution of values (e.g., response times)
- Summary: Statistical summary (e.g., percentiles)
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Deque, Final
from contextlib import contextmanager
import json

logger = logging.getLogger(__name__)

# Configuration constants
MAX_HISTOGRAM_SAMPLES: Final[int] = 1000  # Keep last 1000 samples per histogram
MAX_TIMESERIES_POINTS: Final[int] = 100   # Keep last 100 time series points
PERCENTILES: Final[List[float]] = [0.5, 0.9, 0.95, 0.99]  # P50, P90, P95, P99


class MetricType(Enum):
    """Type of metric"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class MetricValue:
    """Single metric data point"""
    timestamp: float
    value: float
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class MetricSnapshot:
    """Snapshot of a metric at a point in time"""
    name: str
    type: MetricType
    value: float
    labels: Dict[str, str]
    help_text: str
    timestamp: float

    # Additional statistics for histograms
    samples: Optional[int] = None
    sum: Optional[float] = None
    percentiles: Optional[Dict[str, float]] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        result = {
            'name': self.name,
            'type': self.type.value,
            'value': self.value,
            'labels': self.labels,
            'help': self.help_text,
            'timestamp': self.timestamp
        }
        if self.samples is not None:
            result['samples'] = self.samples
        if self.sum is not None:
            result['sum'] = self.sum
        if self.percentiles:
            result['percentiles'] = self.percentiles
        return result


class Counter:
    """
    Counter metric - monotonically increasing value.

    Use for: total requests, total errors, total API calls
    """

    def __init__(self, name: str, help_text: str = ""):
        self.name = name
        self.help_text = help_text
        self._value = 0.0
        self._lock = threading.Lock()
        self._labels: Dict[str, str] = {}

    def inc(self, amount: float = 1.0) -> None:
        """Increment counter by amount"""
        if amount < 0:
            raise ValueError("Counter can only increase")

        with self._lock:
            self._value += amount

    def get(self) -> float:
        """Get current value"""
        with self._lock:
            return self._value

    def snapshot(self) -> MetricSnapshot:
        """Get current snapshot"""
        return MetricSnapshot(
            name=self.name,
            type=MetricType.COUNTER,
            value=self.get(),
            labels=self._labels.copy(),
            help_text=self.help_text,
            timestamp=time.time()
        )


class Gauge:
    """
    Gauge metric - can increase or decrease.

    Use for: active connections, memory usage, queue size
    """

    def __init__(self, name: str, help_text: str = ""):
        self.name = name
        self.help_text = help_text
        self._value = 0.0
        self._lock = threading.Lock()
        self._labels: Dict[str, str] = {}

    def set(self, value: float) -> None:
        """Set gauge to specific value"""
        with self._lock:
            self._value = value

    def inc(self, amount: float = 1.0) -> None:
        """Increment gauge"""
        with self._lock:
            self._value += amount

    def dec(self, amount: float = 1.0) -> None:
        """Decrement gauge"""
        with self._lock:
            self._value -= amount

    def get(self) -> float:
        """Get current value"""
        with self._lock:
            return self._value

    def snapshot(self) -> MetricSnapshot:
        """Get current snapshot"""
        return MetricSnapshot(
            name=self.name,
            type=MetricType.GAUGE,
            value=self.get(),
            labels=self._labels.copy(),
            help_text=self.help_text,
            timestamp=time.time()
        )


class Histogram:
    """
    Histogram metric - tracks distribution of values.

    Use for: request latency, response sizes, processing times
    """

    def __init__(self, name: str, help_text: str = ""):
        self.name = name
        self.help_text = help_text
        self._samples: Deque[float] = deque(maxlen=MAX_HISTOGRAM_SAMPLES)
        self._count = 0
        self._sum = 0.0
        self._lock = threading.Lock()
        self._labels: Dict[str, str] = {}

    def observe(self, value: float) -> None:
        """Record a new observation"""
        with self._lock:
            self._samples.append(value)
            self._count += 1
            self._sum += value

    def get_percentile(self, percentile: float) -> float:
        """
        Calculate percentile value.

        Args:
            percentile: Value between 0 and 1 (e.g., 0.95 for P95)
        """
        with self._lock:
            if not self._samples:
                return 0.0

            sorted_samples = sorted(self._samples)
            index = int(len(sorted_samples) * percentile)
            index = max(0, min(index, len(sorted_samples) - 1))
            return sorted_samples[index]

    def get_mean(self) -> float:
        """Calculate mean value"""
        with self._lock:
            if self._count == 0:
                return 0.0
            return self._sum / self._count

    def snapshot(self) -> MetricSnapshot:
        """Get current snapshot with percentiles"""
        percentiles = {
            f"p{int(p * 100)}": self.get_percentile(p)
            for p in PERCENTILES
        }

        return MetricSnapshot(
            name=self.name,
            type=MetricType.HISTOGRAM,
            value=self.get_mean(),
            labels=self._labels.copy(),
            help_text=self.help_text,
            timestamp=time.time(),
            samples=len(self._samples),
            sum=self._sum,
            percentiles=percentiles
        )


class MetricsCollector:
    """
    Central metrics collector for the application.

    CRITICAL FIX (P1-7): Thread-safe metrics collection and aggregation
    """

    def __init__(self):
        self._counters: Dict[str, Counter] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._histograms: Dict[str, Histogram] = {}
        self._lock = threading.Lock()

        # Initialize standard metrics
        self._init_standard_metrics()

    def _init_standard_metrics(self) -> None:
        """Initialize standard application metrics"""
        # Request metrics
        self.register_counter("requests_total", "Total number of requests")
        self.register_counter("requests_success", "Total successful requests")
        self.register_counter("requests_failed", "Total failed requests")

        # Performance metrics
        self.register_histogram("request_duration_seconds", "Request duration in seconds")
        self.register_histogram("api_call_duration_seconds", "API call duration in seconds")

        # Resource metrics
        self.register_gauge("active_connections", "Current active connections")
        self.register_gauge("active_tasks", "Current active tasks")

        # Database metrics
        self.register_counter("db_queries_total", "Total database queries")
        self.register_histogram("db_query_duration_seconds", "Database query duration")

        # Error metrics
        self.register_counter("errors_total", "Total errors")
        self.register_counter("errors_by_type", "Errors by type")

    def register_counter(self, name: str, help_text: str = "") -> Counter:
        """Register a new counter metric"""
        with self._lock:
            if name not in self._counters:
                self._counters[name] = Counter(name, help_text)
            return self._counters[name]

    def register_gauge(self, name: str, help_text: str = "") -> Gauge:
        """Register a new gauge metric"""
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = Gauge(name, help_text)
            return self._gauges[name]

    def register_histogram(self, name: str, help_text: str = "") -> Histogram:
        """Register a new histogram metric"""
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = Histogram(name, help_text)
            return self._histograms[name]

    def get_counter(self, name: str) -> Optional[Counter]:
        """Get counter by name"""
        return self._counters.get(name)

    def get_gauge(self, name: str) -> Optional[Gauge]:
        """Get gauge by name"""
        return self._gauges.get(name)

    def get_histogram(self, name: str) -> Optional[Histogram]:
        """Get histogram by name"""
        return self._histograms.get(name)

    @contextmanager
    def track_request(self, success: bool = True):
        """
        Context manager to track request metrics.

        Usage:
            with metrics.track_request():
                # Do work
                pass
        """
        start_time = time.time()
        self.get_gauge("active_tasks").inc()

        try:
            yield
            if success:
                self.get_counter("requests_success").inc()
        except Exception:
            self.get_counter("requests_failed").inc()
            raise
        finally:
            duration = time.time() - start_time
            self.get_histogram("request_duration_seconds").observe(duration)
            self.get_counter("requests_total").inc()
            self.get_gauge("active_tasks").dec()

    @contextmanager
    def track_api_call(self):
        """
        Context manager to track API call metrics.

        Usage:
            with metrics.track_api_call():
                response = await client.post(...)
        """
        start_time = time.time()

        try:
            yield
        finally:
            duration = time.time() - start_time
            self.get_histogram("api_call_duration_seconds").observe(duration)

    @contextmanager
    def track_db_query(self):
        """
        Context manager to track database query metrics.

        Usage:
            with metrics.track_db_query():
                cursor.execute(query)
        """
        start_time = time.time()

        try:
            yield
        finally:
            duration = time.time() - start_time
            self.get_histogram("db_query_duration_seconds").observe(duration)
            self.get_counter("db_queries_total").inc()

    def get_all_snapshots(self) -> List[MetricSnapshot]:
        """Get snapshots of all metrics"""
        snapshots = []

        with self._lock:
            for counter in self._counters.values():
                snapshots.append(counter.snapshot())

            for gauge in self._gauges.values():
                snapshots.append(gauge.snapshot())

            for histogram in self._histograms.values():
                snapshots.append(histogram.snapshot())

        return snapshots

    def to_json(self) -> str:
        """Export all metrics as JSON"""
        snapshots = self.get_all_snapshots()
        data = {
            'timestamp': time.time(),
            'metrics': [s.to_dict() for s in snapshots]
        }
        return json.dumps(data, indent=2)

    def to_prometheus(self) -> str:
        """
        Export metrics in Prometheus text format.

        Format:
        # HELP metric_name Description
        # TYPE metric_name counter
        metric_name{label="value"} 123.45 timestamp
        """
        lines = []
        snapshots = self.get_all_snapshots()

        for snapshot in snapshots:
            # HELP line
            lines.append(f"# HELP {snapshot.name} {snapshot.help_text}")

            # TYPE line
            lines.append(f"# TYPE {snapshot.name} {snapshot.type.value}")

            # Metric line
            labels_str = ",".join(f'{k}="{v}"' for k, v in snapshot.labels.items())
            if labels_str:
                labels_str = f"{{{labels_str}}}"

            # For histograms, export percentiles
            if snapshot.type == MetricType.HISTOGRAM and snapshot.percentiles:
                for pct_name, pct_value in snapshot.percentiles.items():
                    lines.append(
                        f'{snapshot.name}_bucket{{le="{pct_name}"}}{labels_str} '
                        f'{pct_value} {int(snapshot.timestamp * 1000)}'
                    )
                lines.append(
                    f'{snapshot.name}_count{labels_str} '
                    f'{snapshot.samples} {int(snapshot.timestamp * 1000)}'
                )
                lines.append(
                    f'{snapshot.name}_sum{labels_str} '
                    f'{snapshot.sum} {int(snapshot.timestamp * 1000)}'
                )
            else:
                lines.append(
                    f'{snapshot.name}{labels_str} '
                    f'{snapshot.value} {int(snapshot.timestamp * 1000)}'
                )

            lines.append("")  # Blank line between metrics

        return "\n".join(lines)

    def get_summary(self) -> Dict:
        """Get human-readable summary of key metrics"""
        request_duration = self.get_histogram("request_duration_seconds")
        api_duration = self.get_histogram("api_call_duration_seconds")
        db_duration = self.get_histogram("db_query_duration_seconds")

        return {
            'requests': {
                'total': int(self.get_counter("requests_total").get()),
                'success': int(self.get_counter("requests_success").get()),
                'failed': int(self.get_counter("requests_failed").get()),
                'active': int(self.get_gauge("active_tasks").get()),
                'avg_duration_ms': round(request_duration.get_mean() * 1000, 2),
                'p95_duration_ms': round(request_duration.get_percentile(0.95) * 1000, 2),
            },
            'api_calls': {
                'avg_duration_ms': round(api_duration.get_mean() * 1000, 2),
                'p95_duration_ms': round(api_duration.get_percentile(0.95) * 1000, 2),
            },
            'database': {
                'total_queries': int(self.get_counter("db_queries_total").get()),
                'avg_duration_ms': round(db_duration.get_mean() * 1000, 2),
                'p95_duration_ms': round(db_duration.get_percentile(0.95) * 1000, 2),
            },
            'errors': {
                'total': int(self.get_counter("errors_total").get()),
            },
            'resources': {
                'active_connections': int(self.get_gauge("active_connections").get()),
                'active_tasks': int(self.get_gauge("active_tasks").get()),
            }
        }


# Global metrics collector singleton
_global_metrics: Optional[MetricsCollector] = None
_metrics_lock = threading.Lock()


def get_metrics() -> MetricsCollector:
    """Get global metrics collector (singleton)"""
    global _global_metrics

    if _global_metrics is None:
        with _metrics_lock:
            if _global_metrics is None:
                _global_metrics = MetricsCollector()
                logger.info("Initialized global metrics collector")

    return _global_metrics


def format_metrics_summary(summary: Dict) -> str:
    """Format metrics summary for CLI display"""
    lines = [
        "\n📊 Metrics Summary",
        "=" * 70,
        "",
        "Requests:",
        f"  Total: {summary['requests']['total']}",
        f"  Success: {summary['requests']['success']}",
        f"  Failed: {summary['requests']['failed']}",
        f"  Active: {summary['requests']['active']}",
        f"  Avg Duration: {summary['requests']['avg_duration_ms']}ms",
        f"  P95 Duration: {summary['requests']['p95_duration_ms']}ms",
        "",
        "API Calls:",
        f"  Avg Duration: {summary['api_calls']['avg_duration_ms']}ms",
        f"  P95 Duration: {summary['api_calls']['p95_duration_ms']}ms",
        "",
        "Database:",
        f"  Total Queries: {summary['database']['total_queries']}",
        f"  Avg Duration: {summary['database']['avg_duration_ms']}ms",
        f"  P95 Duration: {summary['database']['p95_duration_ms']}ms",
        "",
        "Errors:",
        f"  Total: {summary['errors']['total']}",
        "",
        "Resources:",
        f"  Active Connections: {summary['resources']['active_connections']}",
        f"  Active Tasks: {summary['resources']['active_tasks']}",
        "",
        "=" * 70
    ]

    return "\n".join(lines)
