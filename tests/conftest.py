import pytest
from synth import make_sessions

from logsentinel.data.sessions import write_sessions
from logsentinel.features.counts import featurize


@pytest.fixture(scope="session")
def tiny_cf(tmp_path_factory):
    p = tmp_path_factory.mktemp("sess") / "hdfs.sessions.jsonl.gz"
    write_sessions(make_sessions(), p)
    return featurize(p, "hdfs")


@pytest.fixture(scope="session")
def tiny_cf_short(tmp_path_factory):
    sessions = make_sessions(n_short=25)
    p = tmp_path_factory.mktemp("sess_short") / "hdfs.sessions.jsonl.gz"
    write_sessions(sessions, p)
    return featurize(p, "hdfs"), sessions
