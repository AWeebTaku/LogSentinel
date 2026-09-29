import time

from confluent_kafka.admin import AdminClient, NewTopic

from .wire import TOPIC_ALERTS, TOPIC_METRICS, TOPIC_RAW


def ensure_topics(bootstrap: str, partitions: int = 6, recreate: bool = True) -> None:
    """(Re)create logs-raw (LogAppendTime => broker append timestamps) and alerts-critical."""
    ac = AdminClient({"bootstrap.servers": bootstrap})
    names = [TOPIC_RAW, TOPIC_ALERTS, TOPIC_METRICS]
    existing = set(ac.list_topics(timeout=10).topics)
    if recreate:
        gone = [n for n in names if n in existing]
        if gone:
            for f in ac.delete_topics(gone, operation_timeout=30).values():
                f.result()
        while set(gone) & set(ac.list_topics(timeout=10).topics):  # wait until deletion is visible
            time.sleep(0.2)
    elif set(names) <= existing:
        return
    new = [NewTopic(TOPIC_RAW, partitions, 1, config={"message.timestamp.type": "LogAppendTime",
                                                      "retention.ms": "7200000"}),
           NewTopic(TOPIC_ALERTS, 3, 1, config={"retention.ms": "86400000"}),
           NewTopic(TOPIC_METRICS, 1, 1, config={"retention.ms": "3600000"})]
    for f in ac.create_topics(new, operation_timeout=30).values():
        f.result()
