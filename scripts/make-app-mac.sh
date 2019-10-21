#!/bin/sh

# exit on errors
set -e

# make icons
./scripts/make-icons.sh

# build application
python3.7 -m PyInstaller pyi-app.spec
