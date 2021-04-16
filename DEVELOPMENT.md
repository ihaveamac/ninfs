This is a work in progress, please do not hesitate to contact me if there are any questions.

## Before you continue...
The focus of ninfs is to allow easy extraction of data from file types relevant to Nintendo consoles that would be useful mounting as a virtual filesystem.

### Goals
- File types that are standard on Nintendo consoles
- File types that are standard across games used on Nintendo consoles (e.g. darc)
- Standard/generic file types that are used often on Nintendo consoles (e.g. FAT32)

### Non-goals
- File types for other devices (e.g. Xbox or PlayStation), though ninfs can be used as a base for a separate project
- Creation of files (e.g. game or save file containers, NAND images)
- File types that would not be useful viewing as a filesystem (e.g. N64 ROMs due to the lack of a standard filesystem)

## Adding a new type
Each mount type is stored in `ninfs/mount/{type_name}.py`. "`type_name`" is a name such as `cia`, `nandctr` or `sd`.

### Creating the module
There might be templates here later. For now, the best place would be to copy another module.

### Adding the module
The central module that describes all the mount types is in `ninfs/mountinfo.py`.
1. Add an entry to the `types` dict. Example:
    ```python
    'romfs': {
        'name': 'Read-only Filesystem',
        'info': '".romfs", "romfs.bin"'
    },
    ```
   The key name must match the mount type. `name` should include the type's full name, including the console if necessary to distinguish it. `info` usually should show a quoted, comma-separated list of common file names and/or file extensions, but it can show other important files if necessary.
1. Add any appropriate aliases. This could include different file extensions (e.g. `mount_3ds` is an alias for `mount_cci` since both are extensions of the same file type) or consoles (e.g. `mount_nandhac` and `mount_nandswitch`).
1. Add it to the appropriate category, or create one if needed.

Now ninfs will be able to show it in the default output (`python3 -m ninfs`), it can be used as a mount type (`python3 -m ninfs romfs`), it will generate aliases when installed (e.g. `mount_romfs`), and will be included in a build produced by cx_Freeze.

It will also show up in the GUI, however it won't work properly until a setup wizard module is created for it.

### Creating a GUI wizard
Designing a wizard module is a bit more complicated. A template for this might also be provided later. For now, copy one that works the closest to what the mount module needs.

#### Adding the wizard module
1. Edit `ninfs/gui/setupwizard/__init__.py` and add an import for the setup class.
1. Edit `ninfs/gui/wizardcontainer.py` and add the mount name + setup class to `wizard_bases`. (The setup class is already imported from the above with a wildcard import.)
