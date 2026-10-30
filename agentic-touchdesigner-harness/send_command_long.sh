#!/bin/bash
BRIDGE="${TD_BRIDGE_DIR:-./td-bridge}"
# usage: send_command_long.sh <local_cmd.py> <max_wait_s>
cp "$1" "$BRIDGE/cmd.py"
sleep 1
cp "$1" "$BRIDGE/cmd.py"
start=$(date +%s)
while true; do
  if [ -f "$BRIDGE/cmd_result.txt" ]; then
    age=$(( $(date +%s) - $(stat -c %Y "$BRIDGE/cmd_result.txt") ))
    if [ $age -lt 5 ]; then cat "$BRIDGE/cmd_result.txt"; exit 0; fi
  fi
  now=$(date +%s); elapsed=$(( now - start ))
  if [ $elapsed -gt $2 ]; then echo "TIMEOUT_WAITING_RESULT after ${elapsed}s"; exit 0; fi
  sleep 2
done
