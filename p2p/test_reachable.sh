#!/bin/bash
peer="$1"
ip="${peer%:*}"
port="${peer##*:}"
if timeout 5 bash -c "echo > /dev/tcp/$ip/$port" 2>/dev/null; then
  echo "$peer  REACHABLE"
else
  echo "$peer  unreachable"
fi
