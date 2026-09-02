#!/usr/bin/env bash
set -euo pipefail
root="build/deb-root"
rm -rf "$root"
mkdir -p "$root/DEBIAN" "$root/opt/ace-studio" "$root/usr/share/applications" "$root/usr/share/pixmaps" "$root/usr/bin"
cp -R build/linux/. "$root/opt/ace-studio/"
cp packaging/linux/control "$root/DEBIAN/control"
cp packaging/linux/ace-studio.desktop "$root/usr/share/applications/ace-studio.desktop"
cp src/assets/icon.png "$root/usr/share/pixmaps/ace-studio.png"
ln -s /opt/ace-studio/ace_studio "$root/usr/bin/ace-studio"
dpkg-deb --build "$root" build/ace-studio_0.1.5_amd64.deb
