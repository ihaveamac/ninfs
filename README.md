# ninfs
ninfs (formerly fuse-3ds) is a FUSE program to extract data from Nintendo game consoles. It works by presenting a virtual filesystem with the contents of your games, NAND, or SD card contents, and you can browse and copy out just the files that you need.

Windows, macOS, and Linux are supported.

<p align="center"><img src="https://github.com/ihaveamac/ninfs/raw/2.0/resources/cia-mount-mac.png" width="1032"></p>

## Supported types
* Nintendo 3DS
  * CTR Cart Image (".3ds", ".cci")
  * CDN contents ("cetk", "tmd", and contents)
  * CTR Importable Archive (".cia")
  * Executable Filesystem (".exefs", "exefs.bin")
  * Nintendo 3DS NAND backup ("nand.bin")
  * NCCH (".cxi", ".cfa", ".ncch", ".app")
  * Read-only Filesystem (".romfs", "romfs.bin")
  * SD Card Contents ("Nintendo 3DS" from SD)
  * Installed SD Title Contents ("\*.tmd" and "\*.app" files)
  * 3DSX Homebrew (".3dsx")
* Nintendo DS / DSi
  * Nintendo DSi NAND backup ("nand\_dsi.bin")
  * Nintendo DS ROM image (".nds", ".srl")
* iQue Player
  * iQue Player NAND backup (read-only) ("nand.bin")
* Nintendo Switch
  * Nintendo Switch NAND backup ("rawnand.bin")

## Example uses
* Mount a NAND backup and browse CTRNAND, TWLNAND, and others, and write back to them without having to extract and decrypt them first.
* Browse decrypted SD card contents. Dump installed games and saves, or copy contents between two system's SD contents.
* Extract a game's files out of a CIA, CCI (".3ds"), NCCH, RomFS, raw CDN contents, just by mounting them and browsing its files. Or use the virtual decrypted file and start playing the game in [Citra](https://citra-emu.org) right away.

## Setup
For 3DS types, The ARM9 bootROM is required. You can dump it using boot9strap, which can be set up by [3DS Hacks Guide](https://3ds.hacks.guide). To dump the bootROM, hold START+SELECT+X when you boot up your 3DS. It is checked in order of:
* `--boot9` argument (if set)
* `BOOT9_PATH` environment variable (if set)
* `%APPDATA%\3ds\boot9.bin` (Windows-specific)
* `~/Library/Application Support/3ds/boot9.bin` (macOS-specific)
* `~/.3ds/boot9.bin`
* `~/3ds/boot9.bin`

`boot9_prot.bin` can also be used in all of these locations.

"`~`" means the user's home directory. "`~/3ds`" would mean `/Users/username/3ds` on macOS and `C:\Users\username\3ds` on Windows.

CDN, CIA, and NCCH mounting may need [SeedDB](https://github.com/ihaveamac/3DS-rom-tools/wiki/SeedDB-list) for mounting NCCH containers of newer games (2015+) that use seeds.  
SeedDB is checked in order of:
* `--seeddb` argument (if set)
* `SEEDDB_PATH` environment variable (if set)
* `%APPDATA%\3ds\seeddb.bin` (Windows-specific)
* `~/Library/Application Support/3ds/seeddb.bin` (macOS-specific)
* `~/.3ds/seeddb.bin`
* `~/3ds/seeddb.bin`

Python 3.6.1 or later is required.

### Windows
Windows 8.1 or later is required.

#### Installer
An installer is provided in [releases](https://github.com/ihaveamac/ninfs/releases). It includes both ninfs and WinFsp, which is installed if required.

#### Standalone release
A standalone zip is also provided in [releases](https://github.com/ihaveamac/ninfs/releases). [WinFsp](https://winfsp.dev/rel/) must be installed separately.

#### Install with existing Python
* Install the latest version of [Python 3](https://www.python.org/downloads/). The x86-64 version is preferred on 64-bit Windows.
  * Python from the Microsoft Store can also be used. If this is used, `python3` must be used instead of `py -3`. This version has some limitations however, such as not being able to mount to directories.
* Install the latest version of [WinFsp](https://winfsp.dev/rel/).
* Install ninfs with `py -3 -m pip install --upgrade https://github.com/ihaveamac/ninfs/archive/2.0.zip`

### macOS
Versions of macOS supported by Apple are highly recommended. macOS Sierra is the oldest version that should work. [macFUSE](https://osxfuse.github.io/) is required.

No standalone build is available at the moment.

#### Install with existing Python
* Install the latest version of Python 3. The recommended way is [Homebrew](https://brew.sh). You can also use an installer from [python.org](https://www.python.org/downloads/) or a tool like [pyenv](https://github.com/pyenv/pyenv).
* Install the latest version of [macFUSE](https://github.com/osxfuse/osxfuse/releases/latest).
* Install ninfs with `python3 -m pip install --upgrade https://github.com/ihaveamac/ninfs/archive/2.0.zip`

### Linux
#### Arch Linux
(NOTE: git versions out of date while build process stabilizes)  
ninfs is available in the AUR: [normal](https://aur.archlinux.org/packages/ninfs/), [with gui](https://aur.archlinux.org/packages/ninfs-gui/), ~~[git](https://aur.archlinux.org/packages/ninfs-git/), [git with gui](https://aur.archlinux.org/packages/ninfs-gui-git/)~~

#### Other distributions
* Recent distributions (e.g. Ubuntu 18.04 and later) should have Python 3.6.1 or later pre-installed, or included in its repositories. If not, you can use an extra repository (e.g. [deadsnakes's PPA](https://launchpad.net/%7Edeadsnakes/+archive/ubuntu/ppa) for Ubuntu), [build from source](https://www.python.org/downloads/source/), or use a tool like [pyenv](https://github.com/pyenv/pyenv).
* Most distributions should have libfuse enabled/installed by default. Use your package manager if it isn't.
* Install ninfs with `python3 -m pip install --upgrade --user https://github.com/ihaveamac/ninfs/archive/2.0.zip`
  * `--user` is not needed if you are using a virtual environment.
* You can add a desktop entry with `python3 -m ninfs --install-desktop-entry`. If you want to install to a location other than the default (`$XDG_DATA_HOME`), you can add another argument with a path like `/usr/local/share`.
* To use the GUI, tkinter needs to be installed. On Debian-/Ubuntu-based systems this is `python3-tk`. On Fedora this is `python3-tkinter`.

## Usage
### Graphical user interface
A GUI can be used by specifying the type to be `gui` (e.g. Windows: `py -3 -mninfs gui`, \*nix: `python3 -mninfs gui`). The GUI controls mounting and unmounting.

### Command line
Run a mount script by using "`mount_<type>`" (e.g. `mount_cci game.3ds mountpoint`). Use `-h` to view arguments for a script.

If it doesn't work, the other way is to use `<python-cmd> -mninfs <type>` (e.g. Windows: `py -3 -mninfs cci game.3ds mountpoint`, \*nix: `python3 -mninfs cci game.3ds mountpoint`).

Windows users can use a drive letter like `F:` as a mountpoint, or use `*` and a drive letter will be automatically chosen.

Developer-unit contents are encrypted with different keys, which can be used with `--dev` with CCI, CDN, CIA, NANDCTR, NCCH, and SD.

#### Unmounting
* Windows: Press <kbd>Ctrl</kbd> + <kbd>C</kbd> in the command prompt/PowerShell window.
* macOS: Two methods:
  * Right-click on the mount and choose "Eject “_drive name_”".
  * Run from terminal: `diskutil unmount /path/to/mount`
* Linux: Run from terminal: `fusermount -u /path/to/mount`

### Examples
* 3DS game card dump:  
  `mount_cci game.3ds mountpoint`
* Contents downloaded from CDN:  
  `mount_cdn cdn_directory mountpoint`
* CDN contents with a specific decrypted titlekey:  
  `mount_cdn --dec-key 3E3E6769742E696F2F76416A65423C3C cdn_directory mountpoint`
* CIA:  
  `mount_cia game.cia mountpoint`
* ExeFS:  
  `mount_exefs exefs.bin mountpoint`
* 3DS NAND backup with `essential.exefs` embedded:    
  `mount_nandctr nand.bin mountpoint`
* 3DS NAND backup with an OTP file (Counter is automatically generated):  
  `mount_nandctr --otp otp.bin nand.bin mountpoint`
* 3DS NAND backup with OTP and CID files:  
  `mount_nandctr --otp otp.bin --cid nand_cid.bin nand.bin mountpoint`
* 3DS NAND backup with OTP file and a CID hexstring:  
  `mount_nandctr --otp otp.bin --cid 7468616E6B7334636865636B696E6721 nand.bin mountpoint`
* DSi NAND backup (Counter is automatically generated):  
  `mount_nandtwl --console-id 5345445543454D45 nand_dsi.bin mountpoint`
* DSi NAND backup with a Console ID hexstring and specified CID hexstring:  
  `mount_nandtwl --console-id 5345445543454D45 --cid 576879446F657344536945786973743F nand_dsi.bin mountpoint`
* DSi NAND backup with a Console ID file and specified CID file:  
  `mount_nandtwl --console-id ConsoleID.bin --cid CID.bin nand_dsi.bin mountpoint`
* iQue Player NAND backup:  
  `mount_nandbb nand.bin mountpoint`
* Switch NAND backup:  
  `mount_nandhac --keys prod.keys rawnand.bin mountpoint`
* Switch NAND backup in multiple parts:  
  `mount_nandhac --keys prod.keys -S rawnand.bin.00 mountpoint`
* Switch NAND encrypted partition dump:  
  `mount_nandhac --keys prod.keys --partition SYSTEM SYSTEM.bin mountpoint`
* NCCH container (.app, .cxi, .cfa, .ncch):  
  `mount_ncch content.cxi mountpoint`
* RomFS:  
  `mount_romfs romfs.bin mountpoint`
* `Nintendo 3DS` directory from an SD card:  
  `mount_sd --movable movable.sed "/path/to/Nintendo 3DS" mountpoint`
* `Nintendo 3DS` directory from an SD card with an SD key hexstring:  
  `mount_sd --sd-key 504C415900000000504F4B454D4F4E21 "/path/to/Nintendo 3DS" mountpoint`
* Nintendo DS ROM image (NDS/SRL, `mount_nds` also works):  
  `mount_srl game.nds mountpoint`
* 3DSX homebrew application:  
  `mount_threedsx boot.3dsx mountpoint`

## Useful tools
* wwylele's [3ds-save-tool](https://github.com/wwylele/3ds-save-tool) can be used to extract game saves and extra data (DISA and DIFF, respectively).
  * wwylele's [save3ds](https://github.com/wwylele/save3ds) is a tool to interact with 3DS save files and extdata. Extracting and importing works on all platforms. The FUSE part only works on macOS and Linux.
* [OSFMount](https://www.osforensics.com/tools/mount-disk-images.html) for Windows can mount FAT12/FAT16/FAT32 partitions in NAND backups.

## Related tools
* roothorick's [BUSEHAC](https://gitlab.com/roothorick/busehac) is a Linux driver for encrypted Nintendo Switch NANDs.
* Maschell's [fuse-wiiu](https://github.com/Maschell/fuse-wiiu) can be used to mount Wii U contents.
* koolkdev's [wfslib](https://github.com/koolkdev/wfslib) has wfs-fuse to mount the Wii U mlc dumps and usb devices.

# License/Credits
* `ninfs` is under the MIT license.
  * `fuse.py` is under the ISC license ([taken from `setup.py`](https://github.com/fusepy/fusepy/blob/b5f87a1855119d55c755c2c4c8b1da346365629d/setup.py)).

Special thanks to @Jhynjhiruu for adding support for iQue Player NAND backups.

Special thanks to @Stary2001 for help with NAND crypto (especially TWL), and @d0k3 for SD crypto.

OTP code is from [Stary2001/3ds_tools](https://github.com/Stary2001/3ds_tools/blob/10b74fee927f66865b97fd73b3e7392e81a3099f/three_ds/aesengine.py), and is under the MIT license.
