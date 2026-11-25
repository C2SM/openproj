"""An access token for a plan remote that is not on GitHub: Forgejo, Gitea, or any
host that takes a username and a token over HTTP basic auth.

Why a token and not an App: `github.py` says why GitHub gets an App, and its
argument is about properties a self-hosted forge does not offer. Forgejo has no
installation tokens, so the narrowest credential it has is a personal token with
the `write:repository` scope. It lives until revoked and belongs to one person,
which is the trade the App was chosen to avoid, and on a forge one person runs
for a plan they share with a handful of others it is the credential that exists.

A value and not a path, unlike the App's key. The key is a multi-line PEM, which
is why it is mounted as a file; a token is one line, and both places this runs
hand a secret over as a variable: compose through an `env_file`, Cloud Run
through `--set-secrets`.

The token is imported only when a deployment configures it. The reads at the
foot of this file are for the repositories a plan names, which may be on any
Forgejo, and are imported by whoever asks a forge about one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx


@dataclass
class ForgeToken:
    """Pushes as `user` with `token` as the password.

    The user is the token's owner: Forgejo and Gitea check that the two belong
    together, and refuse a token presented under any other name. Nothing beyond
    `callbacks()`, so the store's optional GitHub calls (`offer_pull_request`,
    `api_headers`) find nothing and a parked branch is left on the remote for a
    person to see, which is what the store already does for a credential
    without them.
    """

    user: str
    token: str = field(repr=False)

    NEEDS = ("OPENPROJ_REMOTE_USER", "OPENPROJ_REMOTE_TOKEN")

    @classmethod
    def missing(cls, environ: dict[str, str]) -> list[str]:
        return [name for name in cls.NEEDS if not environ.get(name, "").strip()]

    @classmethod
    def from_environment(cls, environ: dict[str, str]) -> ForgeToken | None:
        if cls.missing(environ):
            return None
        return cls(
            environ["OPENPROJ_REMOTE_USER"].strip(), environ["OPENPROJ_REMOTE_TOKEN"].strip()
        )

    def callbacks(self):
        import pygit2

        return pygit2.RemoteCallbacks(credentials=pygit2.UserPass(self.user, self.token))


# How long a host has to say which forge it is. A page waits on the first answer,
# so this is short, and an unanswered host is asked again later, not given up on.
_PROBE_SECONDS = 4.0
# Forgejo's page size ceiling unless an admin raised it, so asking for more gets this
_OPEN_LIMIT = 50


def forge_of(origin: str, token: str = "", transport: httpx.BaseTransport | None = None) -> str:
    """Which forge answers at `origin`: `github`, `forgejo`, `unsupported` or
    `unreachable`.

    github.com by its name, and anything else by asking `/api/v1/version`, which
    Forgejo and Gitea (and therefore Codeberg) answer and GitLab does not. A
    Forgejo that requires sign-in refuses an anonymous caller there with its own
    JSON error, whose `url` points at its API docs, so that refusal is an answer
    too. `token` only for a host the deployment names, see `create_app`'s `token_for`.
    """
    if origin == "https://github.com":
        return "github"
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"token {token}"
    try:
        with httpx.Client(transport=transport, timeout=_PROBE_SECONDS) as client:
            response = client.get(f"{origin}/api/v1/version", headers=headers)
    except httpx.HTTPError:
        return "unreachable"
    try:
        said = response.json()
    except ValueError:
        return "unsupported"
    if not isinstance(said, dict):
        return "unsupported"
    if response.status_code == 200 and isinstance(said.get("version"), str):
        return "forgejo"
    if str(said.get("url", "")).endswith("/api/swagger"):
        return "forgejo"
    return "unsupported"


def _ask(
    origin: str,
    path: str,
    params: dict[str, object] | None,
    token: str,
    transport: httpx.BaseTransport | None,
) -> httpx.Response:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"token {token}"
    with httpx.Client(transport=transport, timeout=10.0) as client:
        response = client.get(f"{origin}/api/v1{path}", headers=headers, params=params)
    response.raise_for_status()
    return response


def open_references(
    origin: str,
    repository: str,
    token: str = "",
    transport: httpx.BaseTransport | None = None,
) -> list[dict[str, object]]:
    """The open pull requests and issues in one Forgejo repository.

    The shape `github.open_references` answers, for the reason it gives: the
    issues endpoint lists both, and marks a pull request with `pull_request`.
    Raises on a refusal, and the caller decides what that means.
    """
    response = _ask(
        origin,
        f"/repos/{repository}/issues",
        {"state": "open", "limit": _OPEN_LIMIT},
        token,
        transport,
    )
    return [
        {
            "number": int(one["number"]),
            "title": str(one.get("title") or ""),
            "pull": bool(one.get("pull_request")),
        }
        for one in response.json()
    ]


def reference_state(
    origin: str,
    repository: str,
    number: int,
    token: str = "",
    transport: httpx.BaseTransport | None = None,
) -> tuple[dict[str, object], int | None]:
    """Where one Forgejo pull request or issue stands, in `github.reference_state`'s
    shape.

    A closed issue is landed: Forgejo records no reason for closing one, so
    "not planned" cannot be told from "done". No rate limit comes back, because
    Forgejo sends none by default.
    """
    one = _ask(origin, f"/repos/{repository}/issues/{number}", None, token, transport).json()
    if one.get("state") != "closed":
        return {"state": "open", "at": None}, None
    pull = one.get("pull_request") or {}
    landed = bool(pull.get("merged")) if pull else True
    when = str((pull.get("merged_at") if pull else None) or one.get("closed_at") or "")[:10]
    return {"state": "landed" if landed else "dropped", "at": when or None}, None
