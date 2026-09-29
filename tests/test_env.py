from logsentinel.common.env import capture_env


def test_capture_env_has_core_fields():
    e = capture_env()
    assert e["cpu_count"] and e["mem_gb"] > 0 and "scikit-learn" in e["packages"]
