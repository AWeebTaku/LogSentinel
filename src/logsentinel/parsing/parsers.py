"""Parser arms for E2. All three map a session's line-level events to a fixed set of feature columns.

raw   : hash of the message content (no masking) into fixed buckets. Unseen events are invisible.
regex : masked message (numbers/ids/IPs -> <*>) is the event id. Unseen masked strings -> <UNK> column.
drain : Drain3 templates learned on the TRAIN vocabulary only; unmatched messages -> <UNK> column.

The heavy per-line pass happens once (features/counts.py). Here we only build column maps, so
comparing parsers costs a sparse matrix product, not another pass over 20M lines.
"""
import numpy as np
import scipy.sparse as sp
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig


def _column_map(mapping: np.ndarray, n_cols: int) -> sp.csr_matrix:
    """mapping[i] = target column of source column i (-1 -> UNK, placed at column 0)."""
    cols = mapping + 1
    n = len(mapping)
    return sp.csr_matrix((np.ones(n, dtype=np.float32), (np.arange(n), cols)), shape=(n, n_cols + 1))


def regex_map(vocab: list[str], train_freq: np.ndarray, max_events: int = 5000) -> tuple[sp.csr_matrix, list[str]]:
    """Keep the max_events most frequent masked strings seen in train; everything else -> UNK."""
    seen = np.flatnonzero(train_freq > 0)
    keep = seen[np.argsort(-train_freq[seen], kind="stable")][:max_events]
    mapping = np.full(len(vocab), -1, dtype=np.int64)
    mapping[keep] = np.arange(len(keep))
    return _column_map(mapping, len(keep)), ["<UNK>"] + [vocab[i] for i in keep]


def drain_map(
    vocab: list[str], train_freq: np.ndarray, sim_th: float = 0.4, depth: int = 4
) -> tuple[sp.csr_matrix, list[str]]:
    """Fit Drain on train masked strings (most frequent first), then match every vocab entry."""
    cfg = TemplateMinerConfig()
    cfg.drain_sim_th, cfg.drain_depth, cfg.profiling_enabled = sim_th, depth, False
    tm = TemplateMiner(persistence_handler=None, config=cfg)
    seen = np.flatnonzero(train_freq > 0)
    for i in seen[np.argsort(-train_freq[seen], kind="stable")]:
        tm.add_log_message(vocab[i])
    ids: dict[int, int] = {}
    templates = ["<UNK>"]
    mapping = np.full(len(vocab), -1, dtype=np.int64)
    for i, text in enumerate(vocab):
        c = tm.match(text, full_search_strategy="fallback")
        if c is not None:
            if c.cluster_id not in ids:
                ids[c.cluster_id] = len(ids)
                templates.append(c.get_template())
            mapping[i] = ids[c.cluster_id]
    return _column_map(mapping, len(ids)), templates


class ParserRuntime:
    """Serve-time parser: masked message -> feature column (0 = <UNK>). regex and drain only.

    The feature space is defined by TRAIN strings alone (what a deployed system can know): anything
    else, including messages Drain clusters into templates it never saw, lands in <UNK>. Rebuilt
    deterministically from its constructor args on unpickle (TemplateMiner itself is not picklable).
    """

    def __init__(self, kind: str, train_strings: list[str], train_freq, max_events: int = 5000,
                 sim_th: float = 0.4, depth: int = 4):
        if kind not in ("regex", "drain"):
            raise ValueError("serving supports regex and drain (raw is an offline ablation only)")
        self.args = (kind, list(train_strings), np.asarray(train_freq), max_events, sim_th, depth)
        self.kind = kind
        self._cache: dict[str, int] = {}
        seen = np.flatnonzero(self.args[2] > 0)
        order = seen[np.argsort(-self.args[2][seen], kind="stable")]
        if kind == "regex":
            _, names = regex_map(self.args[1], self.args[2], max_events)
            self._cols = {n: i for i, n in enumerate(names) if i}
            self.n_cols = len(names)
            self._tm = None
        else:
            cfg = TemplateMinerConfig()
            cfg.drain_sim_th, cfg.drain_depth, cfg.profiling_enabled = sim_th, depth, False
            self._tm = TemplateMiner(persistence_handler=None, config=cfg)
            for i in order:
                self._tm.add_log_message(self.args[1][i])
            self._cols: dict[int, int] = {}       # drain cluster id -> column (assigned on train strings only)
            for i in order:
                c = self._tm.match(self.args[1][i], full_search_strategy="fallback")
                if c is not None and c.cluster_id not in self._cols:
                    self._cols[c.cluster_id] = len(self._cols) + 1
            self.n_cols = len(self._cols) + 1

    def __reduce__(self):
        return (ParserRuntime, self.args)

    def column(self, masked: str) -> int:
        col = self._cache.get(masked)
        if col is None:
            if self.kind == "regex":
                col = self._cols.get(masked, 0)
            else:
                c = self._tm.match(masked, full_search_strategy="fallback")
                col = self._cols.get(c.cluster_id, 0) if c is not None else 0
            if len(self._cache) < 500_000:   # bound memory under adversarial/high-cardinality input
                self._cache[masked] = col
        return col
