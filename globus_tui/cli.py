"""Command line entry point."""
from __future__ import annotations

import argparse
import os
import sys

from . import __version__
from .backend import load_config, make_backend


def _check(backend) -> int:
    """Non-interactive environment check; exit 0 when the TUI can run."""
    import platform

    ok = True

    def line(good, msg):
        nonlocal ok
        ok = ok and good
        print(("[ok]   " if good else "[FAIL] ") + msg)

    v = sys.version_info
    line(v >= (3, 9), f"python {platform.python_version()} at {sys.executable}")
    try:
        import textual, globus_sdk  # noqa: F401
        line(True, f"textual {textual.__version__}, globus-sdk {globus_sdk.__version__}")
    except Exception as exc:  # pragma: no cover
        line(False, f"imports: {exc}")
    enc = (getattr(sys.stdout, "encoding", None) or "").lower()
    print(("[ok]   " if "utf" in enc else "[warn] ") + f"stdout encoding {enc or 'unknown'}"
          + ("" if "utf" in enc else "  (ASCII glyphs will be used; set LANG=C.UTF-8 for nicer output)"))
    term = os.environ.get("TERM", "")
    print(("[ok]   " if term and term != "dumb" else "[warn] ") + f"TERM={term or 'unset'}")
    if backend.name == "demo":
        line(True, "demo backend, no login needed")
        return 0 if ok else 1
    need = backend.login_required()
    authenticated = "Existing Globus CLI session authenticated" if backend.name == "cli" else "Globus tokens present"
    line(not need, authenticated if not need else "not logged in: run `globus-tui --login` (interactive)")
    if not need:
        try:
            backend.count_tasks(("ACTIVE", "INACTIVE"))
            line(True, "Transfer API reachable as " + backend.identity())
        except Exception as exc:
            line(False, f"Transfer API call failed: {exc}")
    else:
        try:
            import requests

            r = requests.get("https://transfer.api.globus.org/v0.10/endpoint_search?filter_fulltext=tutorial&limit=1",
                             timeout=10)
            line(True, f"transfer.api.globus.org reachable (HTTP {r.status_code})")
        except Exception as exc:
            line(False, f"cannot reach transfer.api.globus.org: {exc} (login node without internet? proxy?)")
    return 0 if ok else 1


def main(argv=None) -> int:
    cfg = load_config()
    p = argparse.ArgumentParser(
        prog="globus-tui",
        description="Lightweight terminal UI for monitoring Globus transfers.",
    )
    p.add_argument("--demo", action="store_true", help="run with fake data, no login needed")
    p.add_argument("--tasks", action="store_true", help="open on the Activity (task list) screen")
    p.add_argument("--backend", choices=("auto", "cli", "sdk"), default=cfg.get("backend", "auto"),
                   help="authentication backend (auto prefers an installed Globus CLI)")
    p.add_argument("-i", "--interval", type=int, default=cfg.get("interval", 30),
                   help="auto-refresh interval in seconds (default 30)")
    p.add_argument("--client-id", default=None,
                   help="Globus native-app client id (or set GLOBUS_TUI_CLIENT_ID)")
    p.add_argument("--no-flows", action="store_true", default=not cfg.get("flows", True),
                   help="do not request Flows access (skips the Flow Runs section)")
    p.add_argument("--login", action="store_true", help="(re)run the Globus login flow and exit")
    p.add_argument("--logout", action="store_true", help="revoke and delete stored tokens")
    p.add_argument("--check", action="store_true",
                   help="non-interactive environment/login check, exit 0 if the TUI can run")
    p.add_argument("--version", action="version", version=f"globus-tui {__version__}")
    args = p.parse_args(argv)

    backend = make_backend(demo=args.demo, client_id=args.client_id, flows=not args.no_flows,
                           backend=args.backend)

    if args.check:
        try:
            return _check(backend)
        except RuntimeError as exc:
            print(f"[FAIL] {exc}\nFor CLI authentication, run `globus login` in your terminal.", file=sys.stderr)
            return 1

    if backend.name == "cli":
        try:
            if args.login:
                backend.login()
            if args.logout:
                backend.logout()
            backend.login_required()
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    if args.logout:
        backend.logout()
        print("Logged out; stored tokens removed.")
        return 0

    if args.login or (backend.name != "cli" and backend.login_required()):
        if args.login or sys.stdin.isatty():
            print("Globus login needed. A URL will be shown; open it in any browser, approve, and paste the code back.")
            backend.login(force=args.login)
            if args.login:
                print("Login complete. Tokens are stored under ~/.globus/app/ and refresh automatically.")
                return 0
        else:
            print("Not logged in. Run `globus-tui --login` in an interactive shell first.", file=sys.stderr)
            return 1

    if not os.environ.get("TERM") or os.environ.get("TERM") == "dumb":
        os.environ["TERM"] = "xterm-256color"

    from .app import GlobusTUI

    app = GlobusTUI(backend, interval=args.interval, start="tasks" if args.tasks else "dashboard")
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
