# fuse-3ds
FUSE Filesystem Python scripts for Nintendo 3DS files

ARM9 bootROM required. Checked in order of:
* `boot9.bin` (full) in current working directory
* `boot9_prot.bin` (protected) in current working directory
* `~/.3ds/boot9.bin` (full)
* `~/.3ds/boot9_prot.bin` (protected)

Requires Python 3.5+, [fork of fusepy](https://github.com/billziss-gh/fusepy), and [pycryptodomex](https://github.com/Legrandin/pycryptodome).

Install fusepy with `pip install git+https://github.com/billziss-gh/fusepy.git`.

* macOS: [Fuse for macOS](https://osxfuse.github.io)
* Windows: [WinFsp](http://www.secfs.net/winfsp/) - Windows does not work properly so filesystems are read-only.
* Linux: Most distributions should have fuse included. Use your package manager.

## mount_nand.py
Mounts NAND images, creating a virtual filesystem of decrypted partitions. Can read essentials backup by GodMode9, else OTP file/NAND CID must be provided in arguments.

```
usage: mount_nand.py [-h] [--otp OTP] [--cid CID] [--dev] [--ro] [--fg] [--do]
                     [-o OPTIONS]
                     nand mount_point

Mount Nintendo 3DS NAND images.

positional arguments:
  nand         NAND image
  mount_point  mount point

optional arguments:
  -h, --help   show this help message and exit
  --otp OTP    path to otp (enc/dec); not needed if NAND image has essentials
               backup from GodMode9
  --cid CID    NAND CID; not needed if NAND image has essentials backup from
               GodMode9
  --dev        use dev keys
  --ro         mount read-only
  --fg, -f     run in foreground
  --do         debug output (python logging module)
  -o OPTIONS   mount options
```

### Current files
```
mount_point
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
├── twlmbr.bin
├── twln.img
└── twlp.img
```

## mount_sd.py
Mounts SD contents under `/Nintendo 3DS`, creating a virtual filesystem with decrypted contents. `movable.sed` required.

Still needs testing, keep backups.

```
usage: mount_sd.py [-h] --movable MOVABLESED [--ro] [--dev] [--fg] [--do]
                   [-o OPTIONS]
                   sd_dir mount_point

Mount Nintendo 3DS SD card contents. (WRITE SUPPORT NYI)

positional arguments:
  sd_dir                path to folder with SD contents (on SD: /Nintendo 3DS)
  mount_point           mount point

optional arguments:
  -h, --help            show this help message and exit
  --movable MOVABLESED  path to movable.sed
  --ro                  mount read-only
  --dev                 use dev keys
  --fg                  run in foreground
  --do                  debug output (python logging module)
  -o OPTIONS            mount options
```

# License/Credits
`mount_nand.py`, `mount_sd.py` are under the MIT license.

Special thanks to @Stary2001 for help with NAND crypto (especially TWL), and @d0k3 for SD crypto.
