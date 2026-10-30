#!/bin/bash
BRIDGE="${TD_BRIDGE_DIR:-./td-bridge}"
# usage: send_command.sh <local_cmd_py> -- writes cmd.py, waits, prints result
cp "$1" "$BRIDGE/cmd.py"
rm -f "$BRIDGE/cmd_result.txt"
sleep 1
cp "$1" "$BRIDGE/cmd.py"
for i in 1 2 3 4 5 6 7 8; do
  sleep 1
  if [ -f "$BRIDGE/cmd_result.txt" ]; then break; fi
done
cat "$BRIDGE/cmd_result.txt" 2>/dev/null || echo NO_RESULT_YET
