"""Topic names and the on-wire event format.

logs-raw value: {"i": seq, "t": producer send time (ns, wall clock), "l": raw log line}; key = session key.
Ground-truth labels never go on the wire; the benchmark joins them afterwards by session key.
"""
import re

TOPIC_RAW = "logs-raw"
TOPIC_ALERTS = "alerts-critical"
TOPIC_METRICS = "logsentinel-metrics"   # 1 message/s/worker: throughput, lag, latency, watermark

_BLK = re.compile(r"blk_-?\d+")


def hdfs_key(line: str) -> str | None:
    """Session key = first block id in the line (multi-block lines are routed by their first block)."""
    m = _BLK.search(line)
    return m.group(0) if m else None


def hdfs_log_time(line: str) -> int:
    """Seconds on a monotonic scale from the 'YYMMDD HHMMSS' line prefix (HDFS_v1 spans 3 days of one month)."""
    y, m, d = int(line[0:2]), int(line[2:4]), int(line[4:6])
    return (d + 31 * m + 372 * y) * 86400 + int(line[7:9]) * 3600 + int(line[9:11]) * 60 + int(line[11:13])


def format_hdfs_time(t: int) -> str:
    """Inverse of hdfs_log_time: the 13-character 'YYMMDD HHMMSS' prefix for a time on that scale.
    Only valid for dates whose day/month are >= 1 on the scale (true for HDFS_v1, Nov 2008)."""
    days, sec = divmod(int(t), 86400)
    y, rem = divmod(days, 372)
    m, d = divmod(rem, 31)
    return f"{y:02d}{m:02d}{d:02d} {sec // 3600:02d}{sec % 3600 // 60:02d}{sec % 60:02d}"
