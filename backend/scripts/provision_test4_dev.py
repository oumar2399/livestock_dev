#!/usr/bin/env python3
"""Retired entry point. Importing this module never provisions or deletes data."""


def main():
    raise SystemExit(
        "Direct provisioning in livestock_dev is retired. Use "
        "backend/scripts/test4_bench.py prepare --database-url <bench-url> "
        "--transport-id 102 --api-url <backend-url>. "
        "The database must be named livestock_bench; collisions are refused."
    )


if __name__ == "__main__":
    main()
