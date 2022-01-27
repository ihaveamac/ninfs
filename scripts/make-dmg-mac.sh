#!/bin/sh
NV=$(python3 -c 'import ninfs.__init__ as i; print(i.__version__)')
DMGDIR=build/dmg/ninfs-$NV
rm -rf "$DMGDIR"

set -e -u

mkdir -p "$DMGDIR"

cp -rpc dist/ninfs.app "$DMGDIR/ninfs.app"
ln -s /Applications "$DMGDIR/Applications"
cp resources/MacGettingStarted.pdf "$DMGDIR/Getting Started.pdf"

hdiutil create -format UDZO -srcfolder "$DMGDIR" -fs HFS+ "dist/ninfs-$NV-macos.dmg" -ov
