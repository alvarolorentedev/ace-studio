#!/usr/bin/env bash
set -euo pipefail
root="build/deb-root"
rm -rf "$root"
mkdir -p "$root/DEBIAN" "$root/opt/ace-studio" "$root/usr/share/applications" "$root/usr/bin"
cp -R build/linux/. "$root/opt/ace-studio/"
cp packaging/linux/control "$root/DEBIAN/control"
cp packaging/linux/ace-studio.desktop "$root/usr/share/applications/ace-studio.desktop"
ln -s /opt/ace-studio/ace_studio "$root/usr/bin/ace-studio"
dpkg-deb --build "$root" build/ace-studio_0.1.0_amd64.deb
