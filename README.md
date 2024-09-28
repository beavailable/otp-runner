# otp-runner
This KRunner plugin allows you to generate Time-based One-Time Passwords (TOTP) directly from your KDE Plasma desktop. It's a simple way to access your OTPs for two-factor authentication (2FA).

OTP secrets are stored in KWallet under the default wallet which is "kdewallet" in a folder named "OTP Keys".

Although it's a python plugin, it won't be running until you use it and will automatically exit after two minutes of inactivity, so don't worry about the memory usage.

# Screenshots
![img](https://github.com/beavailable/otp-runner/blob/main/screenshot.gif)

# Requirements
```bash
# for Debian
sudo apt install python3-gi
# for Fedora
sudo dnf install python3-gobject
```
If you're not using Klipper, then you should also install one of the following packages:
```bash
# for wayland
wl-clipboard
# for x11
xclip
```

# Installation
```bash
./install.sh
```
After the installation, you'll get a KRunner plugin and an `otp` command for you to use in terminal.

# Uninstallation
```bash
./uninstall.sh
```

# Acknowledgments
This project makes use of code and resources from the following sources:
- **Code**:
    - [mintotp](https://github.com/susam/mintotp) by Susam Pal. Licensed under the MIT License.
- **Icon**:
    - [tabler-icons](https://github.com/tabler/tabler-icons) by Paweł Kuna. Licensed under the MIT License.
