#!/bin/sh
# Start Chromium with DevTools on loopback only, wait until it answers, then run the command.
set -eu

# A restarted container leaves the previous Chromium's profile lock behind.
rm -f /data/chrome/SingletonLock /data/chrome/SingletonSocket /data/chrome/SingletonCookie

flags="--remote-debugging-address=127.0.0.1 --remote-debugging-port=9222 --user-data-dir=/data/chrome
  --no-first-run --no-default-browser-check --disable-dev-shm-usage --lang=nl-NL --window-size=1280,900
  --no-sandbox"
if [ "${CHROME_HEADLESS:-0}" = "1" ]; then
  # shellcheck disable=SC2086
  chromium --headless=new $flags about:blank >/tmp/chromium.log 2>&1 &
else
  # A virtual display keeps a normal, headed browser; some shops reject headless Chrome outright.
  # shellcheck disable=SC2086
  xvfb-run --auto-servernum --server-args="-screen 0 1280x900x24" chromium $flags about:blank \
    >/tmp/chromium.log 2>&1 &
fi

for _ in $(seq 1 100); do
  curl -fsS http://127.0.0.1:9222/json/version >/dev/null 2>&1 && exec "$@"
  sleep 0.2
done
echo "Chromium did not start:" >&2
cat /tmp/chromium.log >&2
exit 1
