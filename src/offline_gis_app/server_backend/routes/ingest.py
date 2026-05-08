"""Legacy compatibility module for ingest route imports."""

import sys
from server_gateway.api.routes import ingest as _target

sys.modules[__name__] = _target
