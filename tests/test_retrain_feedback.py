import numpy as np

from logsentinel.models.retrain_feedback import false_positive_session_keys, retrain
from logsentinel.store import db


def test_retrain_folds_confirmed_false_positives_into_training(tiny_cf, tmp_path):
    # a handful of real, normal (label 0) val/test sessions, same as a model wrongly flagging them
    normal_val_test = [tiny_cf.ids[i] for i in range(len(tiny_cf.ids))
                       if tiny_cf.labels[i] == 0 and tiny_cf.splits[i] != "train"][:12]
    assert len(normal_val_test) == 12

    with db.connect(tmp_path / "db") as con:
        for sid in normal_val_test:
            db.insert_alerts(con, [{"id": sid, "score": 0.9, "kind": "incremental", "run": "r", "model": "m",
                                    "t_trigger_send_ns": 1}])
            a = db.list_alerts(con, run="r", after_id=0, limit=500)[-1]
            db.set_alert_status(con, a["id"], "false_positive", "tester")

        keys = false_positive_session_keys(con)
        assert keys == set(normal_val_test)

        # below the minimum: no bundle
        assert retrain(con, tiny_cf, "hdfs", "regex", "pca", "tuned_val", 0, min_false_positives=99,
                       out=tmp_path / "unused") is None

        m = retrain(con, tiny_cf, "hdfs", "regex", "pca", "tuned_val", 0, min_false_positives=5,
                   out=tmp_path / "bundle")
        assert m is not None and m["status"] == "registered"          # never auto-activated
        assert m["metrics"]["false_positives_folded_in"] == 12
        assert m["meta"]["n_train"] == len(np.flatnonzero(tiny_cf.splits == "train")) + 12
