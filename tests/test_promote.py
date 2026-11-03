import shutil
import uuid

import pytest

from logsentinel.common.config import ROOT
from logsentinel.models.bundle import train_bundle
from logsentinel.promote import promote
from logsentinel.store import db


@pytest.fixture
def bundle_dir(tiny_cf):
    d = ROOT / "models" / f"_pytest-promote-{uuid.uuid4().hex[:8]}"
    train_bundle(tiny_cf, "hdfs", "regex", "pca").save(d)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_promote_registers_and_activates_in_the_target_db(bundle_dir, tmp_path):
    target = tmp_path / "target.db"
    m = promote(bundle_dir, target)
    assert m["status"] == "active" and m["path"] == str(bundle_dir.resolve())
    with db.connect(target) as con:
        assert db.active_model(con, "hdfs")["id"] == m["id"]


def test_promote_without_activate_leaves_it_registered(bundle_dir, tmp_path):
    target = tmp_path / "target.db"
    m = promote(bundle_dir, target, activate=False)
    assert m["status"] == "registered"
    with db.connect(target) as con:
        assert db.active_model(con, "hdfs") is None
