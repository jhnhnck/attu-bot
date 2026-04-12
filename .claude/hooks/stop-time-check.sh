#!/usr/bin/env bash
# warn if it's past 12:30 AM ET
HOUR_MIN=$(TZ=America/New_York date +%H%M)
if (( 10#$HOUR_MIN >= 30 && 10#$HOUR_MIN < 600 )); then
  echo "heads up: it's past 12:30 AM ET - good stopping point if you're wrapping up" >&2
  exit 2
fi
