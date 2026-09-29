import random

from logsentinel.data.sessions import Session

NORMAL = [
    "081109 203518 143 INFO dfs.DataNode$DataXceiver: Receiving block blk_{b} src: /10.0.0.{a}:5{a} dest: /10.0.0.2:50010",
    "081109 203519 143 INFO dfs.FSNamesystem: BLOCK* NameSystem.allocateBlock: /user/root/f{a}. blk_{b}",
    "081109 203520 35 INFO dfs.DataNode$PacketResponder: PacketResponder {a} for block blk_{b} terminating",
    "081109 203521 35 INFO dfs.DataNode$PacketResponder: Received block blk_{b} of size 67108864 from /10.0.0.{a}",
    "081109 203522 35 INFO dfs.FSNamesystem: BLOCK* NameSystem.addStoredBlock: blockMap updated: 10.0.0.{a}:50010 is added to blk_{b} size 67108864",
]
ANOMALY = "081109 203523 35 ERROR dfs.DataNode$DataXceiver: writeBlock blk_{b} received exception java.io.IOException: Connection reset by 10.0.0.{a}"


def make_sessions(n_train=300, n_val=100, n_test=100, anom_frac=0.3, seed=0, lines=12, n_short=0) -> list[Session]:
    rnd = random.Random(seed)
    out = []

    def one(i, split, anomalous):
        b = 1000 + i
        a = rnd.randint(1, 9)
        ls = [NORMAL[j % len(NORMAL)].format(a=a, b=b) for j in range(lines)]
        if anomalous:
            ls[-2:] = [ANOMALY.format(a=a, b=b)] * 2
        return Session(f"blk_{b}", int(anomalous), float(i), ls, split)

    i = 0
    for split, n in (("train", n_train), ("val", n_val), ("test", n_test)):
        for _ in range(n):
            out.append(one(i, split, split != "train" and rnd.random() < anom_frac))
            i += 1
    # short anomalies: write started but never completed (2 lines, then silence), val and test only
    for split, n in (("val", n_short), ("test", n_short)):
        for _ in range(n):
            b, a = 1000 + i, rnd.randint(1, 9)
            out.append(Session(f"blk_{b}", 1, float(i), [NORMAL[j].format(a=a, b=b) for j in range(2)], split))
            i += 1
    return out
