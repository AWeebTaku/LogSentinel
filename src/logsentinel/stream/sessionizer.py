"""Online session state: one Counter of feature columns per key (no raw lines kept).

HDFS blocks live for hours (median ~2 h between first and last line, measured on HDFS_v1), so any
idle timeout short enough to be useful would fragment >80% of sessions. Sessions are therefore never
closed by time; the engine re-scores them as lines arrive, runs an event-time AGE check once a session
is `age_s` log-seconds old (catches sessions that stay incomplete), and flushes on end-of-stream.
# ponytail: no eviction, state grows with open sessions (~0.6 KB each). Add LRU/log-time eviction for
# production streams that never end. The due-queue assumes sessions start in roughly log-time order.
"""
from collections import Counter, deque


class Sess:
    __slots__ = (
        "alert_kind",
        "alert_score",
        "alerted",
        "counts",
        "evidence_s",
        "first_log",
        "last_broker_ms",
        "last_log",
        "last_recv",
        "last_send",
        "n",
        "n_at_alert",
        "score_dur_ns",
        "snap",
        "t_alert",
        "t_scored",
        "t_trigger_broker_ms",
        "t_trigger_recv",
        "t_trigger_send",
    )

    def __init__(self, first_log: int = 0):
        self.counts: Counter = Counter()
        self.snap: Counter = Counter()      # lines with log-time offset <= age_s (the age-check snapshot)
        self.n = 0
        self.first_log = self.last_log = first_log
        self.alerted = False
        self.alert_kind = self.alert_score = self.n_at_alert = self.evidence_s = None
        self.last_broker_ms = 0
        self.t_trigger_send = self.t_trigger_recv = self.t_trigger_broker_ms = None
        self.t_scored = self.score_dur_ns = self.t_alert = None


class Sessionizer:
    def __init__(self, line_col, age_s: int | None = None):
        self.line_col = line_col
        self.age_s = age_s
        self.open: dict[str, Sess] = {}
        self.due: deque[tuple[int, str]] = deque()   # (first_log + age_s, key), oldest first

    def add(self, key: str, line: str, t_send_ns: int, now_ns: int, log_t: int = 0, broker_ms: int = 0) -> Sess:
        s = self.open.get(key)
        if s is None:
            s = self.open[key] = Sess(log_t)
            if self.age_s is not None:
                self.due.append((log_t + self.age_s, key))
        col = self.line_col(line)
        s.counts[col] += 1
        if self.age_s is not None and log_t - s.first_log <= self.age_s:
            s.snap[col] += 1
        s.n += 1
        s.last_recv, s.last_send, s.last_log, s.last_broker_ms = now_ns, t_send_ns, log_t, broker_ms
        return s

    def pop_due(self, watermark: float) -> list[tuple[str, Sess]]:
        """Sessions whose age deadline has passed in event time (watermark = newest log time seen)."""
        out = []
        while self.due and self.due[0][0] < watermark:
            _, key = self.due.popleft()
            out.append((key, self.open[key]))
        return out
