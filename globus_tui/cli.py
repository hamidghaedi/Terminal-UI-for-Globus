"""Command line entry point."""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .backend import config_path, load_config, make_backend


def main(argv=None) -> int:
    cfg = load_config()
    p = argparse.ArgumentParser(
        prog="globus-tui",
        description="Lightweight terminal UI for monitoring Globus transfers.",
    )
    p.add_argument("--demo", action="store_true", help="run with fake data, no login needed")
    p.add_argument("--tasks", action="store_true", help="open on the Activity (task list) screen")
    p.add_argument("-i", "--interval", type=int, default=cfg.get("interval", 30),
                   help="auto-refresh interval in seconds (default 30)")
    p.add_argument("--client-id", default=None,
                   help="Globus native-app client id (or set GLOBUS_TUI_CLIENT_ID)")
    p.add_argument("--no-flows", action="store_true", default=not cfg.get("flows", True),
                   help="do not request Flows access (skips the Flow Runs section)")
    p.add_argument("--login", action="store_true", help="(re)run the Globus login flow and exit")
    p.add_argument("--logout", action="store_true", help="revoke and delete stored tokens")
    p.add_argument("--version", action="version", version=f"globus-tui {__version__}")
    args = p.parse_args(argv)

    backend = make_backend(demo=args.demo, client_id=args.client_id, flows=not args.no_flows)

    if args.logout:
        backend.logout()
        print("Logged out; stored tokens removed.")
        return 0

    if args.login or backend.login_required():
        if args.login or sys.stdin.isatty():
            print("Globus login needed. A URL will be shown; open it, approve, and paste the code back.")
            backend.login(force=args.login)
            if args.login:
                print("Login complete. Tokens are stored under ~/.globus/app/.")
                return 0
        else:
            print("Not logged in. Run `globus-tui --login` first.", file=sys.stderr)
            return 1

    from .app import GlobusTUI

    app = GlobusTUI(backend, interval=args.interval, start="tasks" if args.tasks else "dashboard")
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
