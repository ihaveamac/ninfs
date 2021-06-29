# This file is a part of ninfs.
#
# Copyright (c) 2017-2021 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

from .base import WizardBase

from .cci import CCISetup
from .cdn import CDNSetup
from .cia import CIASetup
from .exefs import ExeFSSetup
from .nandctr import CTRNandImageSetup
from .nandhac import HACNandImageSetup
from .nandtwl import TWLNandImageSetup
from .nandbb import BBNandImageSetup
from .ncch import NCCHSetup
from .romfs import RomFSSetup
from .sd import SDFilesystemSetup
from .sdtitle import SDTitleSetup
from .srl import SRLSetup
from .threedsx import ThreeDSXSetup
