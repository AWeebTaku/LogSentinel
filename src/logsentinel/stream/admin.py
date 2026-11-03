import time

from confluent_kafka.admin import AdminClient, NewTopic

from .wire import TOPIC_ALERTS, TOPIC_METRICS, TOPIC_RAW


def ensure_topics(bootstrap: str, partitions: int = 6, recreate: bool = True) -> None:
    """(Re)create logs-raw (LogAppendTime => broker append timestamps) fresh for this run; ensure
    alerts-critical and logsentinel-metrics exist but never delete them.

    alerts-critical/logsentinel-metrics are long-lived: logsentinel.alerts.sink keeps one consumer
    subscribed to them for the whole app lifetime, across many runs. Deleting and recreating a topic
    out from under a live subscription silently stalls that consumer (the broker hands out a new
    TopicId but librdkafka does not notice the old one is gone), so only logs-raw -- which is per-run
    replay traffic nothing else depends on between runs -- gets the delete+recreate treatment.
    """
    ac = AdminClient({"bootstrap.servers": bootstrap})
    existing = set(ac.list_topics(timeout=10).topics)
    if recreate and TOPIC_RAW in existing:
        ac.delete_topics([TOPIC_RAW], operation_timeout=30)[TOPIC_RAW].result()
        while TOPIC_RAW in set(ac.list_topics(timeout=10).topics):  # wait until deletion is visible
            time.sleep(0.2)
        existing.discard(TOPIC_RAW)
    new = []
    if TOPIC_RAW not in existing:
        new.append(NewTopic(TOPIC_RAW, partitions, 1, config={"message.timestamp.type": "LogAppendTime",
                                                                "retention.ms": "7200000"}))
    if TOPIC_ALERTS not in existing:
        new.append(NewTopic(TOPIC_ALERTS, 3, 1, config={"retention.ms": "86400000"}))
    if TOPIC_METRICS not in existing:
        new.append(NewTopic(TOPIC_METRICS, 1, 1, config={"retention.ms": "3600000"}))
    if new:
        for f in ac.create_topics(new, operation_timeout=30).values():
            f.result()
