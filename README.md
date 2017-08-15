# fuse-3ds
FUSE Filesystem Python scripts for Nintendo 3DS files

Why Python? Because I can. And I can't be bothered to learn something else. Also these scripts are probably not very good but they work for me.

Requires Python 3.5+, [fusepy](https://github.com/terencehonles/fusepy), and [pycryptodomex](https://github.com/Legrandin/pycryptodome).

## mount_nand.py
Mounts NAND images. Currently read-only and only does CTR partitions (no TWL yet). Can read essentials backup by GodMode9, else OTP/NAND CID must be provided in arguments.
