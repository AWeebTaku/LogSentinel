import numpy as np

from logsentinel.parsing.content import content, mask
from logsentinel.parsing.parsers import drain_map, regex_map

BGL_BAD = "KERNDTLB 1117838570 2005.06.03 R02-M1 2005-06-03-15.42.50.36 R02-M1 RAS KERNEL FATAL data TLB error interrupt"
BGL_OK = "- 1117838570 2005.06.03 R02-M1 2005-06-03-15.42.50.36 R02-M1 RAS KERNEL INFO data TLB error interrupt"


def test_content_never_contains_label_token():
    assert content(BGL_BAD, "bgl") == "data TLB error interrupt"
    assert content(BGL_BAD, "bgl") == content(BGL_OK, "bgl")  # anomalous and normal lines are indistinguishable by header
    tb = "KERNEL 1131523501 2005.11.09 aadmin1 Nov  9 00:05:01 src@aadmin1 in.tftpd[14620]: tftp: bad"
    assert content(tb, "thunderbird") == "in.tftpd[14620]: tftp: bad"  # padded day handled


def test_hdfs_content_and_mask():
    line = "081109 203518 143 INFO dfs.DataNode$DataXceiver: Receiving block blk_-16089 src: /10.250.19.102:54106"
    assert mask(content(line, "hdfs")) == "dfs.DataNode$DataXceiver: Receiving block <*> src: /<*>"
    assert mask("job_200811092030_0001 took 45ms") == "job_<*>_<*> took <*>ms"


def _vocab():
    v = ["conn from <*> ok", "conn from <*> failed", "disk <*> full", "fresh event only in test"]
    return v, np.array([50, 10, 5, 0])


def test_regex_map_sends_unseen_to_unk():
    v, freq = _vocab()
    M, names = regex_map(v, freq)
    assert names[0] == "<UNK>" and M.shape == (4, 4)
    assert M[3].nonzero()[1].tolist() == [0]           # never seen in train -> UNK column
    assert M[0].nonzero()[1].tolist() != [0]


def test_drain_map_merges_similar_and_flags_novel():
    v, freq = _vocab()
    M, names = drain_map(v, freq)
    cols = [M[i].nonzero()[1][0] for i in range(4)]
    assert cols[0] == cols[1] != 0                     # same template family
    assert cols[2] not in (0, cols[0])
    assert names[0] == "<UNK>"
