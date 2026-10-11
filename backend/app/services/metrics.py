from collections import defaultdict, deque

import numpy as np

STAGES = ("stt_ms", "translate_ms", "tts_ms", "total_ms")


class Metrics:
    """Rolling latency samples per stage with percentile summaries."""

    def __init__(self, window: int = 1000) -> None:
        self._samples: dict[str, deque[int]] = defaultdict(lambda: deque(maxlen=window))
        self.utterances = 0
        self.errors = 0

    def record(self, stage: str, ms: int) -> None:
        self._samples[stage].append(ms)

    def snapshot(self) -> dict[str, object]:
        latency: dict[str, dict[str, float]] = {}
        for stage in STAGES:
            data = self._samples.get(stage)
            if not data:
                continue
            p50, p95, p99 = np.percentile(np.array(data), [50, 95, 99])
            latency[stage] = {
                "count": float(len(data)),
                "p50": float(p50),
                "p95": float(p95),
                "p99": float(p99),
            }
        return {"utterances": self.utterances, "errors": self.errors, "latency": latency}
