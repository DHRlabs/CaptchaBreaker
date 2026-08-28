"""Command-line interface for CaptchaBreaker.

Usage examples:
    captchabreaker serve                # run the HTTP server
    captchabreaker solve img captcha.png
    captchabreaker solve math captcha.png
    captchabreaker recaptcha SITEKEY https://example.com
    captchabreaker status
"""

from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="captchabreaker",
                                     description="Solve CAPTCHAs for browser agents.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("serve", help="run the local HTTP API server")
    sub.add_parser("status", help="show solver configuration and enabled backends")

    p_solve = sub.add_parser("solve", help="solve an image/math captcha locally")
    p_solve.add_argument("kind", choices=["image", "text", "math"], help="captcha kind")
    p_solve.add_argument("image", help="file path, base64 string, or data: URL")

    p_net = sub.add_parser("recaptcha", help="solve a server-side captcha via provider")
    p_net.add_argument("sitekey")
    p_net.add_argument("page_url")

    args = parser.parse_args(argv)

    if args.cmd == "serve":
        from captchabreaker.server import main as serve
        serve()
        return 0

    if args.cmd == "status":
        from captchabreaker.config import get_provider_config
        for k, v in get_provider_config().items():
            print(f"  {k}: {v}")
        return 0

    if args.cmd == "solve":
        from captchabreaker.client import solve_image, solve_math
        if args.kind == "math":
            answer, ok = solve_math(args.image)
        else:
            answer, ok = solve_image(args.image)
        print(answer if ok else f"FAILED: {answer}")
        return 0 if ok else 1

    if args.cmd == "recaptcha":
        from captchabreaker.client import solve_network
        resp = solve_network("recaptcha_v2", args.sitekey, args.page_url)
        print(resp.solution if resp.success else f"FAILED: {resp.raw}")
        return 0 if resp.success else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
