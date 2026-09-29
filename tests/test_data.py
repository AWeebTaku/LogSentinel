from logsentinel.data.bgl import iter_window_sessions
from logsentinel.data.hdfs import iter_hdfs_sessions
from logsentinel.data.sessions import Session, read_sessions, write_sessions
from logsentinel.data.split import split_sessions


def test_hdfs_groups_by_block_and_uses_block_labels(tmp_path):
    log = tmp_path / "HDFS.log"
    log.write_text(
        "081109 203518 1 INFO x: Receiving block blk_1 src\n"
        "081109 203519 1 INFO x: Receiving block blk_2 src\n"
        "081109 203520 1 INFO x: replicate blk_1 to blk_2\n"   # touches two blocks
        "081109 203521 1 INFO x: Verification for blk_1\n"
        "081109 203522 1 INFO x: unlabeled blk_9\n"            # not in label file -> dropped
    )
    lab = tmp_path / "anomaly_label.csv"
    lab.write_text("BlockId,Label\nblk_1,Normal\nblk_2,Anomaly\n")
    s = {x.id: x for x in iter_hdfs_sessions(log, lab)}
    assert set(s) == {"blk_1", "blk_2"}
    assert len(s["blk_1"].lines) == 3 and len(s["blk_2"].lines) == 2
    assert (s["blk_1"].label, s["blk_2"].label) == (0, 1)
    assert s["blk_1"].ts < s["blk_2"].ts  # ordered by first appearance


def test_bgl_windows_label_if_any_line_anomalous(tmp_path):
    log = tmp_path / "BGL.log"
    log.write_text(
        "- 100 d n t n RAS KERNEL INFO ok\n"
        "KERNDTLB 200 d n t n RAS KERNEL FATAL bad\n"   # same 1h window as above
        "- 3700 d n t n RAS KERNEL INFO ok\n"           # next window, normal
        "garbage line\n"
    )
    w = list(iter_window_sessions(log, window_seconds=3600))
    assert [x.label for x in w] == [1, 0]
    assert [len(x.lines) for x in w] == [2, 1]


def test_split_is_chronological_and_train_is_normal_only():
    ss = [Session(str(i), int(i in (1, 8)), float(i), ["l"]) for i in range(10)]
    out = split_sessions(ss, train=0.6, val=0.1)
    by = {x.id: x.split for x in out}
    assert "1" not in by                      # anomaly inside train slice is dropped
    assert by["0"] == "train" and by["5"] == "train"
    assert by["6"] == "val"
    assert by["7"] == by["8"] == by["9"] == "test"
    assert all(x.label == 0 for x in out if x.split == "train")


def test_roundtrip(tmp_path):
    p = tmp_path / "s.jsonl.gz"
    write_sessions([Session("a", 1, 2.0, ["x", "y"], "test"), Session("b", 0, 3.0, ["z"], "train")], p)
    assert [s.id for s in read_sessions(p, "test")] == ["a"]
    assert len(list(read_sessions(p))) == 2


def test_random_split_is_seeded_and_keeps_anomalies_in_eval():
    def mk():
        return [Session(str(i), int(i % 10 == 0), float(i), ["l"]) for i in range(200)]

    a = split_sessions(mk(), mode="random", seed=1)
    b = split_sessions(mk(), mode="random", seed=1)
    assert [(x.id, x.split) for x in a] == [(x.id, x.split) for x in b]
    assert all(x.label == 0 for x in a if x.split == "train")
    assert any(x.label for x in a if x.split == "test")
    assert [x.ts for x in a] == sorted(x.ts for x in a)
