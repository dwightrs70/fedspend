"""Fail a commit if the author email is not a GitHub no-reply address.

Prevents accidentally publishing a personal email address in commit history.
"""

from __future__ import annotations

import os
import subprocess
import sys

REQUIRED_SUFFIX = "@users.noreply.github.com"


def get_author_email() -> str:
    env_email = os.environ.get("GIT_AUTHOR_EMAIL")
    if env_email:
        return env_email.strip()
    result = subprocess.run(
        ["git", "config", "user.email"], capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


def main() -> int:
    email = get_author_email()
    if email.endswith(REQUIRED_SUFFIX):
        return 0
    shown = email or "(not set)"
    print(
        f"Commit blocked: author email is {shown}.\n"
        f"Use your GitHub no-reply address (ends with {REQUIRED_SUFFIX}):\n"
        '  git config user.email "ID+username@users.noreply.github.com"',
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
