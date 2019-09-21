#!/bin/sh

# exit on errors
set -e

# build wheels for 3.6 to 3.7
python3.6 setup.py bdist_wheel
python3.7 setup.py bdist_wheel
