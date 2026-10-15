#!/usr/bin/env bash
# Run one marker variant over the fixtures and record the peak RSS of the
# processes this run owns: benchmark children and the surya/llama-server
# servers they spawn. Servers start in new sessions, so ownership is an
# environment tag (inherited by every child), not a process group.
# Usage: experiments/run_marker.sh marker|marker-ocr TIMEOUT_S [--only STEM...]
set -u
cd "$(dirname "$0")/.."
variant=$1; timeout=$2; shift 2
log=experiments/$variant-bench.log
export MARKER_RUN_TAG="marker-run-$$-$RANDOM"

owned() {  # pids whose environment carries this run's tag
  grep -lsz "^MARKER_RUN_TAG=$MARKER_RUN_TAG\$" /proc/[0-9]*/environ 2>/dev/null | cut -d/ -f3
}
cleanup() { owned | grep -vx "$$" | xargs -r kill -9 2>/dev/null; }
trap cleanup EXIT
trap 'exit 130' INT TERM

if pgrep -f 'surya\.(fast_layout|ocr_error)\.server|llama-server -m .*surya' >/dev/null; then
  echo "surya/llama-server already running: this run would attach to it and not measure it. Stop it first." >&2
  exit 2
fi

peak=0
experiments/.venv-marker/bin/python experiments/parsing_benchmark.py --backend "$variant" --timeout "$timeout" "$@" > "$log" 2>&1 &
bench=$!
while kill -0 "$bench" 2>/dev/null; do
  pids=$(owned | grep -vx "$$")
  kb=0
  [ -n "$pids" ] && kb=$(ps -o rss= -p "$(echo $pids | tr ' ' ,)" | awk '{s+=$1} END {print s+0}')
  [ "$kb" -gt "$peak" ] && peak=$kb
  # A per-PDF timeout kills only the benchmark child; its llama-server survives in its own session.
  for pid in $(pgrep -f 'llama-server -m .*surya'); do
    echo "$pids" | grep -qx "$pid" || continue
    parent=$(ps -o ppid= -p "$pid" | tr -d ' ')
    echo "$pids" | grep -qx "$parent" || kill -9 "$pid"
  done
  sleep 1
done
wait "$bench"; code=$?
echo "exit=$code peak_rss_mib=$((peak/1024))" | tee -a "$log"
exit "$code"
