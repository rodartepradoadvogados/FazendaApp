#!/bin/bash
cd "$(dirname "$0")"
for p in $(pgrep -x node); do tr '\0' ' ' < /proc/$p/cmdline | grep -q "stub-api" && kill $p; done
sleep 1; (nohup node stub-api.mjs > stub.log 2>&1 &); sleep 2
node capturar.mjs
