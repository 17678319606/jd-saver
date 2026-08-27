"""
Prometheus 指标收集器 - MCP Server 监控
"""
import time
from typing import Dict, Any
from threading import Lock


class MetricsCollector:
    """Prometheus 指标收集器"""

    def __init__(self):
        self._counters: Dict[str, int] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, list] = {}
        self._lock = Lock()
        self._start_time = time.time()

    def increment(self, name: str, value: int = 1):
        """增加计数器"""
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + value

    def set_gauge(self, name: str, value: float):
        """设置仪表值"""
        with self._lock:
            self._gauges[name] = value

    def observe(self, name: str, value: float):
        """记录直方图值"""
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = []
            self._histograms[name].append(value)
            # 只保留最近 1000 个值
            if len(self._histograms[name]) > 1000:
                self._histograms[name] = self._histograms[name][-1000:]

    def get_prometheus_text(self) -> str:
        """生成 Prometheus 格式的指标文本"""
        lines = []
        lines.append(f"# HELP jd_saver_started_at Server start time in epoch")
        lines.append(f"# TYPE jd_saver_started_at gauge")
        lines.append(f"jd_saver_started_at {int(self._start_time)}")

        # Counters
        lines.append("")
        lines.append("# HELP jd_saver_api_calls_total Total number of API calls")
        lines.append("# TYPE jd_saver_api_calls_total counter")
        for name, value in self._counters.items():
            lines.append(f"jd_saver_api_calls_total{{name=\"{name}\"}} {value}")

        # Gauges
        lines.append("")
        lines.append("# HELP jd_saver_cache_hits Total cache hits")
        lines.append("# TYPE jd_saver_cache_hits gauge")
        lines.append(f"jd_saver_cache_hits {self._gauges.get('cache_hits', 0)}")

        lines.append("")
        lines.append("# HELP jd_saver_cache_misses Total cache misses")
        lines.append("# TYPE jd_saver_cache_misses gauge")
        lines.append(f"jd_saver_cache_misses {self._gauges.get('cache_misses', 0)}")

        lines.append("")
        lines.append("# HELP jd_saver_alerts_active Active price alerts count")
        lines.append("# TYPE jd_saver_alerts_active gauge")
        lines.append(f"jd_saver_alerts_active {self._gauges.get('alerts_active', 0)}")

        lines.append("")
        lines.append("# HELP jd_saver_alerts_triggered Total price alerts triggered")
        lines.append("# TYPE jd_saver_alerts_triggered gauge")
        lines.append(f"jd_saver_alerts_triggered {self._gauges.get('alerts_triggered', 0)}")

        # Histograms (simple percentile approximation)
        if "api_latency" in self._histograms:
            values = sorted(self._histograms["api_latency"])
            n = len(values)
            if n > 0:
                lines.append("")
                lines.append("# HELP jd_saver_api_latency_seconds API call latency")
                lines.append("# TYPE jd_saver_api_latency_seconds histogram")
                lines.append(f"jd_saver_api_latency_seconds_count {n}")
                lines.append(f"jd_saver_api_latency_seconds_sum {sum(values):.6f}")
                lines.append(f"jd_saver_api_latency_seconds_bucket{{le=\"0.1\"}} {sum(1 for v in values if v <= 0.1)}")
                lines.append(f"jd_saver_api_latency_seconds_bucket{{le=\"0.5\"}} {sum(1 for v in values if v <= 0.5)}")
                lines.append(f"jd_saver_api_latency_seconds_bucket{{le=\"1.0\"}} {sum(1 for v in values if v <= 1.0)}")
                lines.append(f"jd_saver_api_latency_seconds_bucket{{le=\"+Inf\"}} {n}")

        return "\n".join(lines) + "\n"


# 全局指标实例
metrics = MetricsCollector()
