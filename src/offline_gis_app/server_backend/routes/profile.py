"""Legacy compatibility module for profile route imports."""

import sys
from server_gateway.api.routes import profile as _target

sys.modules[__name__] = _target
