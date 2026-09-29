import shlex
import subprocess
import sys
import time

import pytest

from logsentinel.experiments.e6 import TreeMonitor, analyse_alerts, descendants, parse_iso
from logsentinel.experiments.e6_report import fmt, md, stat


def alert(key, kind, send_ns, ts_ms):
    return {"id": key, "kind": kind, "t_trigger_send_ns": send_ns, "_ts_ms": ts_ms}


def test_analyse_alerts_latency_labels_and_false_alarms():
    t = 5_000_000_000_000
    alerts = [alert("a", "incremental", t, t // 1_000_000 + 40), alert("b", "incremental", t, t // 1_000_000 + 80),
              alert("c", "deadline", t, t // 1_000_000 + 999),                   # deadline latency is not reported
              alert("d", "deadline_eos", t, t // 1_000_000 + 5),                 # end-of-stream flush is not a live alert
              alert("a", "deadline", t, t // 1_000_000 + 10)]                    # same session alerted twice counts once
    labels = {"a": 1, "b": 0, "c": 1, "d": 1}
    r = analyse_alerts(alerts, labels, {"a", "b", "c", "d", "e"})
    assert r["alerts"] == 4 and r["incremental"] == 2 and r["deadline"] == 2
    assert r["alerted_sessions"] == 3 and r["true_anomalies_alerted"] == 2 and r["false_alarms"] == 1
    assert r["incremental_latency_ms"]["n"] == 2 and r["incremental_latency_ms"]["p50"] == pytest.approx(60.0)
    assert analyse_alerts([], labels, set())["incremental_latency_ms"]["p50"] is None


def test_parse_iso_handles_spark_timestamps():
    assert parse_iso("2026-09-28T17:33:48.500Z") - parse_iso("2026-09-28T17:33:48.000Z") == pytest.approx(0.5)
    assert parse_iso("1970-01-01T00:00:10Z") == 10.0


def test_descendants_and_tree_monitor_follow_child_processes():
    p = subprocess.Popen(["sh", "-c", f"{shlex.quote(sys.executable)} -c 'import time; x=[0]*3_000_000; time.sleep(2)' & wait"])
    try:
        time.sleep(0.6)
        assert len(descendants(p.pid)) >= 2                       # the shell and the python it started
        mon = TreeMonitor(p.pid)
        mon.start()
        p.wait(timeout=10)
        cpu, rss_mb = mon.close()
        assert rss_mb > 10 and cpu >= 0.0                           # the child's memory is counted, not just the shell's
    finally:
        p.kill()


def test_report_helpers():
    assert stat([1.0, 3.0, None, 2.0]) == (2.0, 1.0, 3.0, 3) and stat([None]) is None
    assert fmt((1234.5, 1000.0, 2000.0, 3)) == "1,234 [1,000-2,000]" or fmt((1234.5, 1000.0, 2000.0, 3)).startswith("1,23")
    assert md(["a", "b"], [[1, 2]]).splitlines()[-1] == "| 1 | 2 |"


def test_tree_monitor_counts_cpu_since_monitoring_began_not_since_process_start():
    """Regression: cumulative CPU included start-up (Spark's JVM), so Spark looked like 3 cores on 2 pinned cores."""
    burn = "import time\nt=time.time()\nwhile time.time()-t<1.2: pass\ntime.sleep(3)"     # busy 1.2 s, then idle
    p = subprocess.Popen([sys.executable, "-c", burn])
    try:
        time.sleep(1.6)                                    # the busy start-up is over before monitoring starts
        mon = TreeMonitor(p.pid)
        mon.start()
        time.sleep(1.2)
        cpu, _ = mon.close()
        assert cpu < 0.5                                   # only the idle stretch is counted (would be about 1.2 s before the fix)
    finally:
        p.kill()
