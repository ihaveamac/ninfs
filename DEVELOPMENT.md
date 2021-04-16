This is a work in progress, please do not hesitate to contact me if there are any questions.

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
    `info` usually should show a quoted, comma-separated list of common file names and/or file extensions, but it can show other important files if necessary.
1. Add any appropriate aliases. This could include different file extensions (e.g. `mount_3ds` is an alias for `mount_cci` since both are extensions of the same file type) or consoles (e.g. `mount_nandhac` and `mount_nandswitch`).
1. Add it to the appropriate category, or create one if needed.

Now ninfs will be able to show it in the default output (e.g. `python3 -m ninfs`), it can be used as a mount type (`python3 -m ninfs romfs`), it will generate aliases when installed (e.g. `mount_romfs`), and will be included in a build produced by cx_Freeze.

It will also show up in the GUI, however it won't work properly until a setup wizard module is created for it.

### Creating a GUI wizard
Designing a wizard module is a bit more complicated. A template for this might also be provided later. For now, copy one that works the closest to what the mount module needs.

#### Adding the wizard module
1. Edit `ninfs/gui/setupwizard/__init__.py` and add an import for the setup class.
1. Edit `ninfs/gui/wizardcontainer.py` and add the mount name + setup class to `wizard_bases`. (The setup class is already imported from the above with a wildcard import.)
