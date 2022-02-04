This is still being worked on (as of February 3, 2022).

# Windows

## Standalone build
This expects Python 3.8 32-bit to be installed.

Install the dependencies:
```batch
py -3.8-32 -m pip install --user --upgrade cx-Freeze==6.10 -r requirements.txt
```

Build the exe:
```batch
scripts\make-exe-win.bat
```

Build the standalone zip:
```batch
scripts\make-zip-win.bat
```

Build the NSIS installer (by default this depends on it being installed to `C:\Program Files (x86)\NSIS`):
```
scripts\make-inst-win.bat
```

## Wheel and source dist build
* `py -3 setup.py bdist_wheel` - build multi-platform py3 wheel
* `py -3 setup.py sdist` - build source distribution

# macOS
This needs Python built with universal2 to produce a build with a working GUI. A universal2 build will be made.

Set up a venv, activate it, and install the requirements:
```sh
python3.10 -m venv venv310
source venv310/bin/activate
pip install --upgrade pyinstaller certifi -r requirements.txt
```

Build the icns:
```sh
./scripts/make-icons.sh
```

Build the app:
```sh
pyinstaller standalone.spec
```

## Distributing for release
Mostly for my reference, but in case you want to try and reproduce a build. If you are not signing and notarizing the app (which requires giving Apple $99 for a yearly developer program membership), you can just build the dmg and ignore the rest.

## DMG only
```sh
./scripts/make-dmg-mac.sh
```

## Sign and notarize
Most of this was taken from this gist: https://gist.github.com/txoof/0636835d3cc65245c6288b2374799c43

Sign the app:
```sh
codesign \
    --force \
    --deep \
    --options runtime \
    --entitlements ./resources/mac-entitlements.plist \
    --sign "<signature-id>" \
    --timestamp \
    ./dist/ninfs.app
```

`--timestamp` is not necessarily required (and could probably be removed for test builds), but it is if you are notarizing the app.

Build the dmg:
```sh
./scripts/make-dmg-mac.sh
```

Upload for notarization:
```sh
xcrun altool --notarize-app --primary-bundle-id "net.ihaveahax.ninfs" --username "<email-address>" --password "@keychain:Developer-altool" --file ./dist/ninfs-<version>-macos.dmg
```

Wait for an email back about a successful notarization, or check the status:
```sh
xcrun altool --notarization-history 0 -u "<email-address>" -p "@keychain:Developer-altool"
```

Staple the ticket to the dmg:
```sh
xcrun stapler staple ./dist/ninfs-<version>-macos.dmg
```

todo:
* Use pyinstaller for Windows in the same spec file (trying to do this with nsis might suck)

## Wheel and source dist build
* `python3 setup.py bdist_wheel` - build multi-platform py3 wheel
* `python3 setup.py sdist` - build source distribution
