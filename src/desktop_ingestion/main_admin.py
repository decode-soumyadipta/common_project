"""Admin desktop entrypoint.

For Step 1, admin mode maps to the existing server-capable desktop runtime.
"""

from desktop_client.client_backend.desktop.apps.server_app import main


if __name__ == "__main__":
    raise SystemExit(main())
