import os

import pytest

from logsentinel.experiments.harness import (
    RunConfig,
    autoscale_decision,
    pct_table,
    proc_cpu_seconds,
    saturation,
    series_per_second,
    stage_latencies,
)


def rec(send, broker_ms, recv, scored, score_dur, alert, kind="incremental", alerted=True):
    return {"kind": kind, "alerted": alerted, "t_trigger_send": send, "t_trigger_broker_ms": broker_ms,
            "t_trigger_recv": recv, "t_scored": scored, "score_dur_ns": score_dur, "t_alert": alert}


def test_stage_latencies_decompose_and_sum_to_total():
    ms = 1_000_000
    t0 = 1_000_000_000_000                                    # ns
    r = rec(send=t0, broker_ms=(t0 + 6 * ms) // ms, recv=t0 + 20 * ms, scored=t0 + 31 * ms,
            score_dur=8 * ms, alert=t0 + 32 * ms)
    st = stage_latencies([r])
    assert st["producer_to_broker"] == [6.0] and st["broker_to_consumer"] == [14.0]
    assert st["scoring"] == [8.0] and st["engine_update"] == [3.0] and st["alert_emit"] == [1.0]
    assert st["total"] == [32.0]
    assert sum(st[s][0] for s in ("producer_to_broker", "broker_to_consumer", "engine_update", "scoring",
                                  "alert_emit")) == pytest.approx(st["total"][0])


def test_stage_latencies_skip_eos_unalerted_and_clamp_ms_rounding():
    ms = 1_000_000
    t0 = 5_000_000_000_000
    ok = rec(t0, (t0 // ms) - 1, t0 + ms, t0 + 2 * ms, ms // 2, t0 + 2 * ms)       # broker stamp rounded before send
    assert stage_latencies([ok])["producer_to_broker"] == [0.0]                     # clamped, not negative
    bad = [rec(t0, 1, t0, t0, 0, t0, kind="deadline_eos"), rec(t0, 1, t0, t0, 0, t0, alerted=False),
           {**ok, "t_trigger_broker_ms": None}]
    assert all(v == [] for v in stage_latencies(bad).values())


def test_pct_table_handles_empty():
    t = pct_table({"a": [1.0, 2.0, 3.0, 4.0, 100.0], "b": []})
    assert t["a"]["n"] == 5 and t["a"]["p50"] == 3.0 and t["a"]["p99"] > 90
    assert t["b"] == {"n": 0, "p50": None, "p95": None, "p99": None}


CFG = {"lag_threshold": 1000, "hold_s": 2.0, "max_workers": 3, "cooldown_s": 10.0}


def test_autoscale_needs_sustained_lag_and_respects_cooldown_and_cap():
    s: dict = {}
    assert autoscale_decision(s, 5000, 100.0, 1, CFG) is False           # just crossed the threshold
    assert autoscale_decision(s, 5000, 101.0, 1, CFG) is False           # held 1 s of 2
    assert autoscale_decision(s, 5000, 102.1, 1, CFG) is True            # held long enough: scale out
    assert autoscale_decision(s, 5000, 103.0, 2, CFG) is False           # cooldown
    assert autoscale_decision(s, 5000, 113.0, 2, CFG) is True            # cooldown over, still lagging
    assert autoscale_decision(s, 5000, 130.0, 3, CFG) is False           # at max_workers
    s2: dict = {}
    autoscale_decision(s2, 5000, 0.0, 1, CFG)
    assert autoscale_decision(s2, 10, 1.0, 1, CFG) is False              # lag cleared: timer resets
    assert autoscale_decision(s2, 5000, 1.5, 1, CFG) is False
    assert autoscale_decision(s2, 5000, 2.9, 1, CFG) is False            # only 1.4 s since it re-crossed


def test_saturation_stops_at_the_first_rate_that_fails():
    rows = [{"offered": 1000, "achieved": 1000, "drain_s": 0.1, "p99_ms": 50},
            {"offered": 2000, "achieved": 1990, "drain_s": 0.3, "p99_ms": 90},
            {"offered": 4000, "achieved": 3500, "drain_s": 6.0, "p99_ms": 900},       # falls behind
            {"offered": 8000, "achieved": 8000, "drain_s": 0.2, "p99_ms": 60}]        # a lucky run above the failure
    assert saturation(rows) == 2000                                        # not inflated by the 8000 outlier
    assert saturation(rows[2:3]) is None
    assert saturation([{**rows[1], "p99_ms": 800}]) is None                # keeping up on rate but too slow
    assert saturation([{"offered": 10, "achieved": 10, "drain_s": 0.0, "p99_ms": None}]) == 10


def test_series_sums_workers_per_second():
    rows = [{"ts_ns": 10 * 10**9 + 1, "lag": 5, "rate_eps": 100.0, "open_sessions": 3, "alerts": 1},
            {"ts_ns": 10 * 10**9 + 9, "lag": 7, "rate_eps": 50.0, "open_sessions": 4, "alerts": 2},
            {"ts_ns": 11 * 10**9, "lag": None, "rate_eps": None}]
    s = series_per_second(rows)
    assert s[0] == {"t": 10, "lag": 12, "rate_eps": 150.0, "open_sessions": 7, "workers": 2, "alerts": 3}
    assert s[1]["lag"] == 0 and s[1]["workers"] == 1


def test_proc_cpu_seconds_reads_this_process():
    a = proc_cpu_seconds(os.getpid())
    sum(i * i for i in range(2_000_000))
    assert proc_cpu_seconds(os.getpid()) > a


def test_run_config_plan_to_segments():
    paced = RunConfig(plan=[[10.0, 1500.0], [2.0, 15000.0]])
    assert paced.segment_events() == [(15000, 1500.0), (30000, 15000.0)] and paced.total_events() == 45000
    burst = RunConfig(plan=[[0, None]], events=123)
    assert burst.segment_events() == [(123, None)] and burst.total_events() == 123


def test_ready_requires_stable_full_assignment(tmp_path):
    """Regression: a stale ready file made the harness produce while the consumer group was still rebalancing;
    a partition then moved mid-run and ~200k messages were consumed twice."""
    import os
    import time

    from logsentinel.stream.ready import is_ready
    now = time.time()

    def write(w, n, age_s):
        f = tmp_path / f"ready-{w}"
        f.write_text(str(n))
        os.utime(f, (now - age_s, now - age_s))

    assert is_ready(tmp_path, 2, 6, settle_s=3) is False              # no files yet
    write(0, 6, 10)                                                    # w0 was told "6" when it was alone (stale)
    assert is_ready(tmp_path, 2, 6, settle_s=3) is False              # w1 has not reported at all
    write(1, 3, 10)
    assert is_ready(tmp_path, 2, 6, settle_s=3) is False              # 6 + 3 != 6: assignment still moving
    write(0, 3, 10)
    assert is_ready(tmp_path, 2, 6, settle_s=3) is True               # 3 + 3 == 6 and settled for 10 s
    write(1, 3, 1)                                                     # rewritten a second ago: a rebalance just ran
    assert is_ready(tmp_path, 2, 6, settle_s=3) is False
    assert is_ready(tmp_path, 2, 6, settle_s=3, now=now + 5) is True  # ...and settled again 5 s later
    (tmp_path / "ready-1").write_text("")                              # caught mid-write
    assert is_ready(tmp_path, 2, 6, settle_s=0) is False


def test_proc_stat_parsing_and_core_util():
    from logsentinel.experiments.sysmon import core_util, parse_proc_stat
    a = parse_proc_stat("cpu  1 1 1 1 1 1 1 1\ncpu0 100 0 50 800 50 0 0 0\ncpu1 10 0 10 970 10 0 0 0\nintr 5\n")
    b = parse_proc_stat("cpu  1 1 1 1 1 1 1 1\ncpu0 200 0 100 850 50 0 0 0\ncpu1 10 0 10 1070 10 0 0 0\n")
    assert set(a) == {0, 1} and a[0] == (150, 1000)                 # busy = user+nice+system+irq+softirq+steal
    assert core_util(a, b) == [pytest.approx(0.75), pytest.approx(0.0)]   # core0: 150 busy of 200; core1 idle


def test_gc_and_safepoint_log_parsing():
    from logsentinel.experiments.gclog import parse_pauses
    text = (
        "[2026-09-28T21:30:13.123+0000][info][gc] GC(12) Pause Young (Normal) (G1 Evacuation Pause) 25M->10M(64M) 3.456ms\n"
        "[2026-09-28T21:30:14.000+0000][info][gc] GC(13) Concurrent Mark Cycle\n"
        '[2026-09-28T21:30:15.500+0000][info][safepoint] Safepoint "G1CollectForAllocation", Time since last: 1 ns, '
        "Reaching safepoint: 100 ns, Cleanup: 5 ns, At safepoint: 4000000 ns, Total: 4000105 ns\n"
        "garbage line\n"
        "[2026-09-28T21:30:16.000+0000][info][gc] GC(14) Pause Full (System.gc()) 100M->20M(128M) 812.500ms\n"
    )
    p = parse_pauses(text)
    assert [(x["kind"], round(x["ms"], 1)) for x in p] == [("gc:Young", 3.5), ("safepoint:G1CollectForAllocation", 4.0),
                                                            ("gc:Full", 812.5)]
    assert p[2]["t"] - p[0]["t"] == pytest.approx(2.877)


def test_proc_uptime_is_small_for_this_process_and_grows():
    import time

    from logsentinel.experiments.harness import COLD_BROKER_S, proc_uptime_seconds
    a = proc_uptime_seconds(os.getpid())
    assert 0 <= a < 3600                                  # the test process just started
    time.sleep(0.05)
    assert proc_uptime_seconds(os.getpid()) > a
    assert COLD_BROKER_S > 0


def test_steady_state_statistics_skip_cold_incomplete_and_excluded_runs(tmp_path, monkeypatch):
    import json

    import logsentinel.experiments.perf_report as pr
    monkeypatch.setattr(pr, "OUT", tmp_path)
    (tmp_path / "exclusions.json").write_text(json.dumps({"e5d/load25.rep7": "set aside by hand"}))

    def run(cell="load25", rep=0, exp="e5d", **kw):
        return {"experiment": exp, "cell": cell, "rep": rep, "complete": True, "cold_start": False, **kw}

    runs = [run(rep=0), run(rep=1, cold_start=True), run(rep=2, complete=False), run(rep=7), run(rep=3, exp="e5")]
    assert [r["rep"] for r in pr.good(runs)] == [0, 3]     # warm + complete + not excluded (rep 7 is in exclusions.json)
