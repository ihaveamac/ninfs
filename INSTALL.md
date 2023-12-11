# Installation

## Windows

The installer includes ninfs and WinFsp. This is the easiest way to use the application.

The standalone release can be downloaded as **ninfs-(version)-win32.zip** below the notes. Extract and run `ninfsw.exe` (or `ninfs.exe` to have a console attached).

ninfs can also be used as a Python module below.

## macOS

macOS users need [macFUSE](https://osxfuse.github.io) or [fuse-t](https://www.fuse-t.org).

The standalone release can be downloaded as **ninfs-(version)-macos.dmg** below the notes. Open the disk image, optionally copy to the Applications folder, and run ninfs.

ninfs can also be used as a Python module below.

## Linux

Install as a pip module like below. To use the gui, make sure tkinter is installed. This is `python3-tk` on Debian/Ubuntu and `python3-tkinter` on Fedora.

Arch Linux: (AUR git package still needs updates, please wait...)

## BSD/etc.

No idea. It might work! I would like to make sure ninfs works on these systems too, so feel free to file issues or make PRs for compatibility with BSD or other systems that support libfuse.

fusepy should support FreeBSD and OpenBSD. For anything else you should consider adding support to [refuse](https://github.com/pleiszenburg/refuse).

# Python module installation

Python 3.6.1 or later is required. [ninfs on PyPI](https://pypi.org/project/ninfs/)

* Windows: `py -3 -mpip install --user ninfs`
  * Note that Python installed from the Microsoft Store does not work due to sandboxing restrictions.
* macOS and Linux: `python3 -mpip install --user ninfs`

To install a specific version, add `==(version)` to the end (e.g. `pip install --user ninfs==2.0a11`)

------

# A little something extra...

If my tools have helped you in some way then please consider supporting me on [Patreon](https://patreon.com/ihaveahax), [PayPal](https://paypal.me/ihaveamac), or [Ko-Fi](https://ko-fi.com/ihaveahax).