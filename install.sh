#!/bin/bash
set -euo pipefail

mkdir -p ~/.local/bin
cp otp.py ~/.local/bin/otp

mkdir -p ~/.local/share/icons
cp otp.svg ~/.local/share/icons/

mkdir -p ~/.local/share/krunner/dbusplugins
cp plasma-runner-otp.desktop ~/.local/share/krunner/dbusplugins/

mkdir -p ~/.local/share/dbus-1/services
{
    echo '[D-BUS Service]'
    echo 'Name=com.github.otp'
    echo "Exec=$HOME/.local/bin/otp"
} >~/.local/share/dbus-1/services/com.github.otp.service

pgrep -x krunner >/dev/null && kquitapp6 krunner || true
