#!/bin/sh

# check for imagemagick
#if ! convert > /dev/null 2>&1; then
if ! command -v convert &> /dev/null; then
  echo "convert not found, please install ImageMagick"
  exit 1
fi

if [ "$(uname -s)" = Darwin ]; then
    mkdir build 2> /dev/null
    rm -r build/ninfs.iconset 2> /dev/null
    mkdir build/ninfs.iconset

    cp ninfs/gui/data/16x16.png build/ninfs.iconset/icon_16x16.png
    cp ninfs/gui/data/32x32.png build/ninfs.iconset/icon_16x16@2x.png
    cp ninfs/gui/data/32x32.png build/ninfs.iconset/icon_32x32.png
    cp ninfs/gui/data/64x64.png build/ninfs.iconset/icon_32x32@2x.png
    cp ninfs/gui/data/128x128.png build/ninfs.iconset/icon_128x128.png
    cp ninfs/gui/data/1024x1024.png build/ninfs.iconset/icon_512x512@2x.png

    convert ninfs/gui/data/1024x1024.png -resize 256x256 build/256x256_gen.png
    convert ninfs/gui/data/1024x1024.png -resize 512x512 build/512x512_gen.png
    cp build/256x256_gen.png build/ninfs.iconset/icon_128x128@2x.png
    cp build/256x256_gen.png build/ninfs.iconset/icon_256x256.png
    cp build/512x512_gen.png build/ninfs.iconset/icon_256x256@2x.png
    cp build/512x512_gen.png build/ninfs.iconset/icon_512x512.png

    iconutil --convert icns --output build/AppIcon.icns build/ninfs.iconset
fi

cd ninfs/gui/data
convert 1024x1024.png 128x128.png 64x64.png 32x32.png 16x16.png \
          \( -clone 2 -resize 48x48 \) \
          \( -clone 0 -resize 256x256 \) \
          -delete 0 windows.ico
