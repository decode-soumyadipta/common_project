"""Legacy compatibility module for profile route imports."""

import sys
from server_vm.server_backend.routes import profile as _target

sys.modules[__name__] = _target
