from __future__ import annotations

import argparse
import os

from backend.app import create_app
from backend.config import load_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Ka-band RF Designer desktop backend.")
    parser.add_argument("--crawl-only", action="store_true", help="Run the component pipeline and exit.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    arguments = parser.parse_args()

    if arguments.crawl_only:
        from scripts.pipeline import run
        run(load_config().pipeline)
        return 0

    os.environ["RF_DESIGN_DESKTOP"] = "1"
    create_app().run(host=arguments.host, port=arguments.port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__": raise SystemExit(main())
