# fuse-3ds
fuse-3ds is the best and most efficient way to extract data for the Nintendo 3DS. It works by presenting a virtual filesystem with the contents of your games, NAND, or SD card contents, and you can browse and copy out just the files that you need.

## Example uses
* Mount a NAND backup and browse CTRNAND, TWLNAND, and others, and write back to them without having to extract and decrypt them first.
* Browse decrypted SD card contents. Dump installed games and saves, or copy contents between two system's SD contents.
* Extract a game's files out of a CIA, CCI (".3ds"), NCCH, RomFS, raw CDN contents, just by mounting them and browsing its files. Or use the virtual decrypted file start playing the game in [Citra](https://citra-emu.org) right away.

## Setup
The ARM9 bootROM is required. You can dump it using boot9strap, which can be set up by [3DS Hacks Guide](https://3ds.hacks.guide). It is checked in order of:
* `BOOT9_PATH` environment variable (if set)
* `boot9.bin` (full) in current working directory
* `boot9_prot.bin` (protected) in current working directory
* `~/.3ds/boot9.bin` (full)
* `~/.3ds/boot9_prot.bin` (protected)
* `~/3ds/boot9.bin` (full)
* `~/3ds/boot9_prot.bin` (protected)

"`~`" means the user's home directory. "`~/3ds`" would mean `/Users/username/3ds` on macOS and `C:\Users\username\3ds` on Windows.

CCI, CDN, CIA, and NCCH mounting will need [SeedDB](https://github.com/ihaveamac/3DS-rom-tools/wiki/SeedDB-list) for mounting NCCH containers.  
SeedDB is checked in order of:
* `SEEDDB_PATH` environment variable (if set)
* `seeddb.bin` in current working directory
* `~/.3ds/seeddb.bin`
* `~/3ds/seeddb.bin`

It can also be provided with the `--seeddb` argument.

Python 3.6.1+, pycryptodomex, and fusepy are required. appJar is required for the GUI.
* Python 3.5.2+ is supported right now, but support will be removed after Ubuntu 18.04 is released.

### Windows
A GUI is available for use. If you download the exe from the [latest release](https://github.com/ihaveamac/fuse-3ds/releases) and run it, a window will appear allowing you to choose mount options easily.

Python does not have to be installed, but [WinFsp](http://www.secfs.net/winfsp/download/) is still required.

<p align="center"><img src="https://github.com/ihaveamac/fuse-3ds/raw/master/resources/mainwindow.png"></p>

#### Install with existing Python
* Install the latest version of [Python 3](https://www.python.org/downloads/). The x86-64 version is preferred on 64-bit Windows.
* Install the latest version of [WinFsp](http://www.secfs.net/winfsp/download/).
* Install fuse-3ds with `py -3 -m pip install --upgrade https://github.com/ihaveamac/fuse-3ds/archive/master.zip https://github.com/billziss-gh/fusepy/archive/windows.zip`.
  * At the moment, the [main fusepy repository](https://github.com/fusepy/fusepy) does not have full Windows support. This extra requirement will be removed once it is added and a new release is made.

### macOS
* Install the latest version of Python 3. The recommended way is [Homebrew](https://brew.sh). You can also use an installer from [python.org](https://www.python.org/downloads/) or a tool like [pyenv](https://github.com/pyenv/pyenv).
* Install the latest version of [FUSE for macOS](https://github.com/osxfuse/osxfuse/releases/latest).
* Install fuse-3ds with `python3 -m pip install --upgrade https://github.com/ihaveamac/fuse-3ds/archive/master.zip`.

### Linux
* Most modern distributions should have Python 3.5.2 or later pre-installed, or included in its repositories. If not, you can use an extra repository (e.g. [deadsnakes's PPA](https://launchpad.net/%7Edeadsnakes/+archive/ubuntu/ppa) for Ubuntu), build from source, or use a tool like [pyenv](https://github.com/pyenv/pyenv).
* Most distributions should have fuse enabled/installed by default. Use your package manager if it isn't.
* Install fuse-3ds with `python3 -m pip install --upgrade --user https://github.com/ihaveamac/fuse-3ds/archive/master.zip`.
  * `--user` is not needed if you are using a virtual environment.

## Usage
### Graphical user interface
A GUI can be used by specifying the type to be `gui` (e.g. Windows: `py -3 -mfuse3ds gui`, \*nix: `python3 -mfuse3ds gui`).

### Command line
The main way to run a mount script after installing is using "`mount_<type>`" (e.g. `mount_cci game.3ds mountpoint`).

If it doesn't work, the other way is to use `<python-cmd> -mfuse3ds <type>` (e.g. Windows: `py -3 -mfuse3ds cci game.3ds mountpoint`, \*nix: `python3 -mfuse3ds cci game.3ds mountpoint`).

Windows users can use a drive letter like `F:` as a mountpoint, or use `*` and a drive letter will be automatically chosen.

### Examples
* Mount a 3DS game card dump:  
  `mount_cci game.3ds mountpoint`
* Mount contents downloaded from CDN:  
  `mount_cdn cdn_directory mountpoint`
* Mount CDN contents with a specific decrypted titlekey:  
  `mount_cdn --dec-key 3E3E6769742E696F2F76416A65423C3C cdn_directory mountpoint`
* Mount a CIA:  
  `mount_cia game.cia mountpoint`
* Mount an ExeFS:  
  `mount_exefs exefs.bin mountpoint`
* Mount a NAND backup with `essential.exefs` embedded:    
  `mount_nand nand.bin mountpoint`
* Mount a NAND backup with OTP and CID files:  
  `mount_nand --otp otp.bin --cid nandcid.bin nand.bin mountpoint`
* Mount a NAND backup with OTP file and a CID hexstring:  
  `mount_nand --otp otp.bin --cid 7468616E6B7334636865636B696E6721 nand.bin mountpoint`
* Mount an NCCH container (.app, .cxi, .cfa, .ncch):  
  `mount_ncch content.cxi mountpoint`
* Mount a RomFS:  
  `mount_romfs romfs.bin mountpoint`
* Mount a `Nintendo 3DS` directory from an SD card:  
  `mount_sd --movable movable.sed "/path/to/Nintendo 3DS" mountpoint`
* Mount a 3DSX homebrew application:  
  `mount_threedsx boot.3dsx mountpoint`
* Mount an entire `title` directory (like one from a NAND backup, or in an SD card mount):  
  `mount_titledir title mountpoint`

## Useful tools
* wwylele's [3ds-save-tool](https://github.com/wwylele/3ds-save-tool) can be used to extract game saves and extra data (DISA and DIFF, respectively).
* [OSFMount](https://www.osforensics.com/tools/mount-disk-images.html) for Windows can mount FAT12/FAT16 partitions in NAND backups.

## Mount scripts

### mount_cci
Mounts CTR Cart Image (CCI, ".3ds") files, creating a virtual filesystem of separate partitions.

```
usage: mount_cci [-h] [-f] [-d] [-o OPTIONS] [--dev] [--seeddb SEEDDB]
                 cci mount_point

Mount Nintendo 3DS CTR Cart Image files.

positional arguments:
  cci              CCI file
  mount_point      mount point

optional arguments:
  -h, --help       show this help message and exit
  -f, --fg         run in foreground
  -d               debug output (fuse/winfsp log)
  -o OPTIONS       mount options
  --dev            use dev keys
  --seeddb SEEDDB  path to seeddb.bin
```

#### Current files
```
mount_point
├── content0.game/        (contains contents from mount_ncch)
├── content1.manual/      (contains contents from mount_ncch)
├── content2.dlp/         (contains contents from mount_ncch)
├── content6.update_o3ds/ (contains contents from mount_ncch)
├── content7.update_n3ds/ (contains contents from mount_ncch)
├── cardinfo.bin
├── content0.game.ncch
├── content1.manual.ncch
├── content2.dlp.ncch
├── content6.update_o3ds.ncch
├── content7.update_n3ds.ncch
├── devinfo.bin
└── ncsd.bin
```

### mount_cdn
Mounts raw CDN contents, creating a virtual filesystem of decrypted contents (if encrypted).

```
usage: mount_cdn [-h] [-f] [-d] [-o OPTIONS] [--dev] [--seeddb SEEDDB]
                 [--dec-key DEC_KEY]
                 cdn_dir mount_point

Mount Nintendo 3DS CDN contents.

positional arguments:
  cdn_dir            directory with CDN contents
  mount_point        mount point

optional arguments:
  -h, --help         show this help message and exit
  -f, --fg           run in foreground
  -d                 debug output (fuse/winfsp log)
  -o OPTIONS         mount options
  --dev              use dev keys
  --seeddb SEEDDB    path to seeddb.bin
  --dec-key DEC_KEY  decrypted titlekey
```

#### Current files
```
mount_point
├── <id>.<index>/     (contains contents from mount_ncch)
├── <id>.<index>.ncch (.nds for twl titles)
├── ticket.bin        (only if a ticket is available)
├── tmd.bin
└── tmdchunks.bin
```

### mount_cia
Mounts CTR Importable Archive (CIA) files, creating a virtual filesystem of decrypted contents (if encrypted) + Ticket,
Title Metadata, and Meta region (if exists).

DLC with missing contents is currently not supported.

```
usage: mount_cia [-h] [-f] [-d] [-o OPTIONS] [--dev] [--seeddb SEEDDB]
                 cia mount_point

Mount Nintendo 3DS CTR Importable Archive files.

positional arguments:
  cia              CIA file
  mount_point      mount point

optional arguments:
  -h, --help       show this help message and exit
  -f, --fg         run in foreground
  -d               debug output (fuse/winfsp log)
  -o OPTIONS       mount options
  --dev            use dev keys
  --seeddb SEEDDB  path to seeddb.bin
```

#### Current files
```
mount_point
├── <id>.<index>/     (contains contents from mount_ncch)
├── <id>.<index>.ncch (.nds for twl titles)
├── cert.bin
├── header.bin
├── icon.bin          (only if meta region exists)
├── meta.bin          (only if meta region exists)
├── ticket.bin
├── tmd.bin
└── tmdchunks.bin
```

### mount_exefs
Mounts Executable Filesystem (ExeFS) files, creating a virtual filesystem of the ExeFS contents.

```
usage: mount_exefs [-h] [-f] [-d] [-o OPTIONS] [--decompress-code]
                   exefs mount_point

Mount Nintendo 3DS Executable Filesystem (ExeFS) files.

positional arguments:
  exefs              ExeFS file
  mount_point        mount point

optional arguments:
  -h, --help         show this help message and exit
  -f, --fg           run in foreground
  -d                 debug output (fuse/winfsp log)
  -o OPTIONS         mount options
  --decompress-code  decompress the .code section
```

### mount_nand
Mounts NAND images, creating a virtual filesystem of decrypted partitions. Can read essentials backup by GodMode9, else
OTP file/NAND CID must be provided in arguments.

```
usage: mount_nand [-h] [-f] [-d] [-o OPTIONS] [-r] [--dev] [--otp OTP]
                  [--cid CID]
                  nand mount_point

Mount Nintendo 3DS NAND images.

positional arguments:
  nand         NAND image
  mount_point  mount point

optional arguments:
  -h, --help   show this help message and exit
  -f, --fg     run in foreground
  -d           debug output (fuse/winfsp log)
  -o OPTIONS   mount options
  -r, --ro     mount read-only
  --dev        use dev keys
  --otp OTP    path to otp (enc/dec); not needed if NAND image has essentials
               backup from GodMode9
  --cid CID    NAND CID; not needed if NAND image has essentials backup from
               GodMode9
```

#### Current files
```
mount_point
├── essential/        (only if essential.exefs was embedded)
├── agbsave.bin
├── bonus.img         (only if GM9 bonus drive is detected)
├── ctrnand_fat.img
├── ctrnand_full.img
├── essential.exefs   (only if essential.exefs was embedded)
├── firm0.bin
├── firm1.bin         (up to 8 firm partitions may be displayed)
├── nand.bin
├── nand_hdr.bin
├── nand_minsize.bin
├── sector0x96.bin    (only if keysector is detected)
├── twl_full.img
├── twlmbr.bin
├── twln.img
└── twlp.img
```

### mount_ncch
Mounts NCCH containers, creating a virtual filesystem of decrypted sections.

```
usage: mount_ncch [-h] [-f] [-d] [-o OPTIONS] [--dev] [--seeddb SEEDDB]
                  ncch mount_point

Mount Nintendo 3DS NCCH containers.

positional arguments:
  ncch             NCCH file
  mount_point      mount point

optional arguments:
  -h, --help       show this help message and exit
  -f, --fg         run in foreground
  -d               debug output (fuse/winfsp log)
  -o OPTIONS       mount options
  --dev            use dev keys
  --seeddb SEEDDB  path to seeddb.bin
```

#### Current files
```
mount_point
├── exefs/           (contains contents from mount_exefs)
├── romfs/           (contains contents from mount_romfs)
├── decrypted.cxi    (shows as decrypted.cfa if the content is not executable)
├── exefs.bin
├── extheader.bin
├── logo.bin         (only if the logo is in a separate region, for 5.0+ games)
├── ncch.bin
├── plain.bin
└── romfs.bin
```

### mount_romfs
Mounts Read-only Filesystem (RomFS) files, creating a virtual filesystem of the RomFS contents. Accepts ones with and
without an IVFC header (original HANS format).

```
usage: mount_romfs [-h] [-f] [-d] [-o OPTIONS] romfs mount_point

Mount Nintendo 3DS Read-only Filesystem (RomFS) files.

positional arguments:
  romfs        RomFS file
  mount_point  mount point

optional arguments:
  -h, --help   show this help message and exit
  -f, --fg     run in foreground
  -d           debug output (fuse/winfsp log)
  -o OPTIONS   mount options
```

### mount_sd
Mounts SD contents under `/Nintendo 3DS`, creating a virtual filesystem with decrypted contents. movable.sed required.

```
usage: mount_sd [-h] [-f] [-d] [-o OPTIONS] [-r] [--dev] --movable MOVABLESED
                sd_dir mount_point

Mount Nintendo 3DS SD card contents.

positional arguments:
  sd_dir                path to folder with SD contents (on SD: /Nintendo 3DS)
  mount_point           mount point

optional arguments:
  -h, --help            show this help message and exit
  -f, --fg              run in foreground
  -d                    debug output (fuse/winfsp log)
  -o OPTIONS            mount options
  -r, --ro              mount read-only
  --dev                 use dev keys
  --movable MOVABLESED  path to movable.sed
```

### mount_threedsx
Mounts 3DSX Homebrew files, creating a virtual filesystem with the 3DSX's RomFS and SMDH.

```
usage: mount_threedsx [-h] [-f] [-d] [-o OPTIONS] threedsx mount_point

Mount 3DSX Homebrew files.

positional arguments:
  threedsx     3DSX file
  mount_point  mount point

optional arguments:
  -h, --help   show this help message and exit
  -f, --fg     run in foreground
  -d           debug output (fuse/winfsp log)
  -o OPTIONS   mount options
```

### mount_titledir
Mounts a "title" directory, creating a virtual system of all the installed titles inside it.

```
usage: mount_titledir [-h] [-f] [-d] [-o OPTIONS] [--dev] [--seeddb SEEDDB]
                      [--mount-all] [--decompress-code]
                      title_dir mount_point

Mount Nintendo 3DS NCCH files from installed NAND/SD titles.

positional arguments:
  title_dir          title directory
  mount_point        mount point

optional arguments:
  -h, --help         show this help message and exit
  -f, --fg           run in foreground
  -d                 debug output (fuse/winfsp log)
  -o OPTIONS         mount options
  --dev              use dev keys
  --seeddb SEEDDB    path to seeddb.bin
  --mount-all        mount all contents, not just the first
  --decompress-code  decompress code of all mounted titles (can be slow with
                     lots of titles!)
```

# License/Credits
`fuse3ds` is under the MIT license.

Special thanks to @Stary2001 for help with NAND crypto (especially TWL), and @d0k3 for SD crypto.
