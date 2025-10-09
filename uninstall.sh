#!/usr/bin/bash
set -euo pipefail

rm ~/.local/bin/otp
rm ~/.local/share/icons/otp.svg
rm ~/.local/share/krunner/dbusplugins/plasma-runner-otp.desktop
rm ~/.local/share/dbus-1/services/com.github.otp.service

pgrep -x krunner >/dev/null && kquitapp6 krunner || true
