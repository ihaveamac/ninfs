# fuse-3ds
fuse-3ds enables you to read and write files for the Nintendo 3DS without extracting or separate decryption.

Since it acts like a virtual filesystem, you can browse it with a file manager (e.g. Windows/File Explorer and Finder) and use any tools to read from it. Certain ones like NAND and SD can also be written back to. All encryption is transparently handled by fuse-3ds.

## Example uses
* Mount a NAND backup and browse CTRNAND, TWLNAND, and others, and write back to them without having to extract and decrypt them first.
* Browse decrypted SD card contents. Dump installed games and saves, or copy contents between two system's SD contents.
* Extract a game's files out of a CIA, CCI (".3ds"), NCCH, RomFS, raw CDN contents, just by mounting them and browsing its files. Or use the virtual decrypted file start playing the game in [Citra](https://citra-emu.org) right away.

## Setup
The ARM9 bootROM is required. You can dump it using boot9strap, which can be set up by [3DS Hacks Guide](https://3ds.hacks.guide). It is checked in order of:
* `boot9.bin` (full) in current working directory
* `boot9_prot.bin` (protected) in current working directory
* `~/.3ds/boot9.bin` (full)
* `~/.3ds/boot9_prot.bin` (protected)

CCI, CDN, CIA, and NCCH mounting will need [SeedDB](https://github.com/ihaveamac/3DS-rom-tools/wiki/SeedDB-list) for mounting NCCH containers. SeedDB is checked at `seeddb.bin` in current working directory, or `~/.3ds/seeddb.bin`. It can also be provided with the `--seeddb` argument.

Python 3.5.2+ and fusepy are required.

### Windows
* Install the latest version of [Python 3](https://www.python.org/downloads/). Make sure you use the x86-64 version on 64-bit Windows.
* Install the latest version of [WinFsp](http://www.secfs.net/winfsp/download/).
* Install fuse-3ds with `py -3 -m pip install --upgrade https://github.com/ihaveamac/fuse-3ds/archive/master.zip https://github.com/billziss-gh/fusepy/archive/windows.zip`.

### macOS
* Install the latest version of Python 3. The recommended way is [Homebrew](https://brew.sh). You can also use an installer from [python.org](https://www.python.org/downloads/) or a tool like [pyenv](https://github.com/pyenv/pyenv).
* Install the latest version of [FUSE for macOS](https://github.com/osxfuse/osxfuse/releases/latest).
* Install fuse-3ds with `python3 -m pip install --upgrade https://github.com/ihaveamac/fuse-3ds/archive/master.zip`.

### Linux
* Most modern distributions should have Python 3.5 or later pre-installed, or included in its repositories. If not, you can use an extra repository (e.g. [deadsnakes's PPA](https://launchpad.net/%7Edeadsnakes/+archive/ubuntu/ppa) for Ubuntu), build from source, or use a tool like [pyenv](https://github.com/pyenv/pyenv).
* Most distributions should have fuse enabled/installed by default. Use your package manager if it isn't.
* Install fuse-3ds with `python3 -m pip install --upgrade --user https://github.com/ihaveamac/fuse-3ds/archive/master.zip`.
  * `--user` is not needed if you are using a virtual environment.

## Usage
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

## Useful tools
* wwylele's [3ds-save-tool](https://github.com/wwylele/3ds-save-tool) can be used to extract game saves and extra data (DISA and DIFF, respectively).
* [OSFMount](https://www.osforensics.com/tools/mount-disk-images.html) for Windows can mount FAT12/FAT16 partitions in NAND backups.

## Mount scripts

### mount_cci
Mounts CTR Cart Image (CCI, ".3ds") files, creating a virtual filesystem of separate partitions.

```
usage: mount_cci [-h] [--fg] [--do] [-o OPTIONS] [--dev] [--seeddb SEEDDB]
                 cci mount_point

Mount Nintendo 3DS CTR Cart Image files.

positional arguments:
  cci              CCI file
  mount_point      mount point

optional arguments:
  -h, --help       show this help message and exit
  --fg, -f         run in foreground
  --do             debug output (python logging module)
  -o OPTIONS       mount options
  --dev            use dev keys
  --seeddb SEEDDB  path to seeddb.bin

```

#### Current files
```
mount_point
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
usage: mount_cdn [-h] [--fg] [--do] [-o OPTIONS] [--dec-key DEC_KEY] [--dev]
                 [--seeddb SEEDDB]
                 cdn_dir mount_point

Mount Nintendo 3DS CDN contents.

positional arguments:
  cdn_dir            directory with CDN contents
  mount_point        mount point

optional arguments:
  -h, --help         show this help message and exit
  --fg, -f           run in foreground
  --do               debug output (python logging module)
  -o OPTIONS         mount options
  --dec-key DEC_KEY  decrypted titlekey
  --dev              use dev keys
  --seeddb SEEDDB    path to seeddb.bin

```

### mount_cia
Mounts CTR Importable Archive (CIA) files, creating a virtual filesystem of decrypted contents (if encrypted) + Ticket, Title Metadata, and Meta region (if exists).

DLC with missing contents is currently not supported.

```
usage: mount_cia [-h] [--fg] [--do] [-o OPTIONS] [--dev] [--seeddb SEEDDB]
                 cia mount_point

Mount Nintendo 3DS CTR Importable Archive files.

positional arguments:
  cia              CIA file
  mount_point      mount point

optional arguments:
  -h, --help       show this help message and exit
  --fg, -f         run in foreground
  --do             debug output (python logging module)
  -o OPTIONS       mount options
  --dev            use dev keys
  --seeddb SEEDDB  path to seeddb.bin

```

#### Current files
```
mount_point
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
usage: mount_exefs [-h] [--fg] [--do] [-o OPTIONS] [--decompress-code]
                   exefs mount_point

Mount Nintendo 3DS Executable Filesystem (ExeFS) files.

positional arguments:
  exefs              ExeFS file
  mount_point        mount_point

optional arguments:
  -h, --help         show this help message and exit
  --fg, -f           run in foreground
  --do               debug output (python logging module)
  -o OPTIONS         mount options
  --decompress-code  decompress the .code section
```

### mount_nand
Mounts NAND images, creating a virtual filesystem of decrypted partitions. Can read essentials backup by GodMode9, else OTP file/NAND CID must be provided in arguments.

```
usage: mount_nand [-h] [--fg] [--do] [-o OPTIONS] [-r] [--otp OTP] [--cid CID]
                  [--dev]
                  nand mount_point

Mount Nintendo 3DS NAND images.

positional arguments:
  nand         NAND image
  mount_point  mount point

optional arguments:
  -h, --help   show this help message and exit
  --fg, -f     run in foreground
  --do         debug output (python logging module)
  -o OPTIONS   mount options
  -r, --ro     mount read-only
  --otp OTP    path to otp (enc/dec); not needed if NAND image has essentials
               backup from GodMode9
  --cid CID    NAND CID; not needed if NAND image has essentials backup from
               GodMode9
  --dev        use dev keys
```

#### Current files
```
mount_point
├── _nandinfo.txt
├── agbsave.bin
├── bonus.img         (only if GM9 bonus drive is detected)
├── ctrnand_fat.img
├── ctrnand_full.img
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
usage: mount_ncch [-h] [--fg] [--do] [-o OPTIONS] [--dev] [--seeddb SEEDDB]
                  ncch mount_point

Mount Nintendo 3DS NCCH containers.

positional arguments:
  ncch             NCCH file
  mount_point      mount point

optional arguments:
  -h, --help       show this help message and exit
  --fg, -f         run in foreground
  --do             debug output (python logging module)
  -o OPTIONS       mount options
  --dev            use dev keys
  --seeddb SEEDDB  path to seeddb.bin
```

### mount_romfs
Mounts Read-only Filesystem (RomFS) files, creating a virtual filesystem of the RomFS contents. Accepts ones with and without an IVFC header (original HANS format).

```
usage: mount_romfs [-h] [--fg] [--do] [-o OPTIONS] romfs mount_point

Mount Nintendo 3DS Read-only Filesystem (RomFS) files.

positional arguments:
  romfs        RomFS file
  mount_point  mount point

optional arguments:
  -h, --help   show this help message and exit
  --fg, -f     run in foreground
  --do         debug output (python logging module)
  -o OPTIONS   mount options
```

### mount_sd
Mounts SD contents under `/Nintendo 3DS`, creating a virtual filesystem with decrypted contents. `movable.sed` required.

```
usage: mount_sd [-h] [--fg] [--do] [-o OPTIONS] [-r] --movable MOVABLESED
                [--dev]
                sd_dir mount_point

Mount Nintendo 3DS SD card contents.

positional arguments:
  sd_dir                path to folder with SD contents (on SD: /Nintendo 3DS)
  mount_point           mount point

optional arguments:
  -h, --help            show this help message and exit
  --fg, -f              run in foreground
  --do                  debug output (python logging module)
  -o OPTIONS            mount options
  -r, --ro              mount read-only
  --movable MOVABLESED  path to movable.sed
  --dev                 use dev keys
```

# License/Credits
`pyctr`, `common`, `mount_cci`, `mount_cdn`, `mount_cia`, `mount_nand`, `mount_ncch`, `mount_romfs`, `mount_sd` are under the MIT license.

Special thanks to @Stary2001 for help with NAND crypto (especially TWL), and @d0k3 for SD crypto.
