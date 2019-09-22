#!/bin/sh

# get the ninfs version
NV=`python3 -c 'from ninfs import __version__; print(__version__)'`
# set build directory
BUILDDIR=build/dmg/ninfs-$NV
# remove existing dmg build directory
rm -r $BUILDDIR

# exit on errors
set -e

# make dmg build directory
mkdir -p $BUILDDIR
# create /Applications symlink
ln -s /Applications $BUILDDIR
# copy application to dmg build directory
cp -pr dist/ninfs.app $BUILDDIR
# (a line here will eventually copy other resources into the dmg)
# create final dmg
hdiutil create -ov -o dist/ninfs-$NV-macos.dmg -format UDBZ -srcfolder $BUILDDIR -fs HFS+
