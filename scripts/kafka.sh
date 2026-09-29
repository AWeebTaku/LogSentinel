#!/usr/bin/env bash
# User-space single-node Kafka (KRaft, no ZooKeeper) for machines without Docker access.
#   scripts/kafka.sh setup   # download + verify JDK 17 and Kafka into ~/.local/share/logsentinel (once)
#   scripts/kafka.sh start | stop | status | reset
# For a Docker setup see docker-compose.yml (not tested on the dev machine).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
T="${LOGSENTINEL_TOOLS:-$HOME/.local/share/logsentinel}"   # must not contain spaces (Kafka scripts break)
JDK_URL="https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.20.1%2B1/OpenJDK17U-jdk_x64_linux_hotspot_17.0.20.1_1.tar.gz"
JDK_SHA256="3808d1d15e3ec6bd5b84057fb5d84c33d8a1536a258146bcea2e603fc726e08e"
KAFKA_VER="3.9.1"
KAFKA_URL="https://archive.apache.org/dist/kafka/$KAFKA_VER/kafka_2.13-$KAFKA_VER.tgz"
KAFKA_SHA512="1EA204BA73411737A275429CA976D440F007FF0957B90B19BE41DC5A4BAE52617267769BE9F0B5791714D0B3C4C760605BD426FAEA39EDD90763585523FA2CFE"
export JAVA_HOME="$T/jdk"
KDIR="$T/kafka"
DATA="$T/kafka-data"
CONF="$T/server.properties"
PIDF="$T/kafka.pid"

fetch() { # url dest algo expected
  local tmp="$2.part"
  curl -fL --retry 5 --retry-delay 3 -o "$tmp" "$1"
  local got; got="$("$3"sum "$tmp" | cut -d' ' -f1 | tr a-f A-F)"
  [ "$got" = "$(echo "$4" | tr a-f A-F)" ] || { echo "checksum mismatch for $1" >&2; rm -f "$tmp"; exit 1; }
  mv "$tmp" "$2"
}

case "${1:-}" in
setup)
  mkdir -p "$T"
  if [ ! -x "$JAVA_HOME/bin/java" ]; then
    fetch "$JDK_URL" "$T/jdk.tgz" sha256 "$JDK_SHA256"
    mkdir -p "$JAVA_HOME" && tar -xzf "$T/jdk.tgz" -C "$JAVA_HOME" --strip-components=1 && rm "$T/jdk.tgz"
  fi
  if [ ! -x "$KDIR/bin/kafka-server-start.sh" ]; then
    fetch "$KAFKA_URL" "$T/kafka.tgz" sha512 "$KAFKA_SHA512"
    mkdir -p "$KDIR" && tar -xzf "$T/kafka.tgz" -C "$KDIR" --strip-components=1 && rm "$T/kafka.tgz"
  fi
  "$JAVA_HOME/bin/java" -version 2>&1 | head -1
  echo "kafka $KAFKA_VER ready in $KDIR" ;;
start)
  [ -x "$KDIR/bin/kafka-server-start.sh" ] || { echo "run: scripts/kafka.sh setup" >&2; exit 1; }
  if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then echo "already running"; exit 0; fi
  cat > "$CONF" <<EOF
process.roles=broker,controller
node.id=1
controller.quorum.voters=1@127.0.0.1:9093
listeners=PLAINTEXT://127.0.0.1:9092,CONTROLLER://127.0.0.1:9093
advertised.listeners=PLAINTEXT://127.0.0.1:9092
controller.listener.names=CONTROLLER
inter.broker.listener.name=PLAINTEXT
listener.security.protocol.map=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
log.dirs=$DATA
num.partitions=6
offsets.topic.replication.factor=1
transaction.state.log.replication.factor=1
transaction.state.log.min.isr=1
group.initial.rebalance.delay.ms=0
num.network.threads=3
num.io.threads=4
log.retention.hours=2
log.segment.bytes=268435456
EOF
  if [ ! -f "$DATA/meta.properties" ]; then
    mkdir -p "$DATA"
    "$KDIR/bin/kafka-storage.sh" format -t "$("$KDIR/bin/kafka-storage.sh" random-uuid)" -c "$CONF" >/dev/null
  fi
  # GC and safepoint logs (wall-clock stamped) so latency stalls can be matched to JVM pauses: $T/kafka-logs/
  mkdir -p "$T/kafka-logs"
  GC_LOG_ENABLED=true LOG_DIR="$T/kafka-logs" \
    KAFKA_OPTS="-Xlog:safepoint*:file=$T/kafka-logs/safepoint.log:time,tags:filecount=3,filesize=50M" \
    KAFKA_HEAP_OPTS="-Xms512m -Xmx1g" nohup "$KDIR/bin/kafka-server-start.sh" "$CONF" > "$T/kafka.log" 2>&1 &
  echo $! > "$PIDF"
  for _ in $(seq 60); do
    if grep -q "Kafka Server started" "$T/kafka.log" 2>/dev/null; then echo "kafka up (pid $(cat "$PIDF"))"; exit 0; fi
    sleep 1
  done
  echo "kafka did not start; see $T/kafka.log" >&2; exit 1 ;;
stop)
  if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
    kill "$(cat "$PIDF")"; while kill -0 "$(cat "$PIDF")" 2>/dev/null; do sleep 1; done; echo stopped
  else echo "not running"; fi
  rm -f "$PIDF" ;;
status)
  if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then echo "running (pid $(cat "$PIDF"))"; else echo "stopped"; fi ;;
reset)
  "$0" stop; rm -rf "$DATA"; echo "data wiped" ;;
*) echo "usage: $0 setup|start|stop|status|reset" >&2; exit 2 ;;
esac
