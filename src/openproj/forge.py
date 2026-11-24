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

Nothing here is imported unless a deployment configures it.
"""

from __future__ import annotations

from dataclasses import dataclass, field


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
