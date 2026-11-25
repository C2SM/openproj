"""The forges a plan's repositories live on: GitHub, Forgejo, and the ones openproj
cannot read.

jcanton, 2026-11-25, with plan-d's code moved to a Forgejo: `repositories:` names
each repository by its page, the host says which forge it is, and a repository on
a forge openproj does not read is named in the footer in orange rather than
linked to the wrong place.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx
import pytest
from pages import elements

from openproj.forge import forge_of, open_references, reference_state
from openproj.index import Index, build_index
from openproj.model import Config, load_repo
from openproj.render import ROUTES


@pytest.fixture
def seed_index(seed_root: Path) -> Index:
    records, config, _ = load_repo(seed_root)
    return build_index(records, config, date(2026, 8, 17))


FORGEJO = "https://git.example.org/jacopo/watchface"
GITLAB = "https://gitlab.com/someone/thing"
GITHUB = "https://github.com/C2SM/icon4py"

LISTED = ROUTES.model_copy(
    update={
        "repositories": (
            (GITHUB, "github"),
            (FORGEJO, "forgejo"),
            (GITLAB, "unsupported"),
        )
    }
)

# Each reference, and where it has to link: the forge of the repository listed
# under that name, GitHub for a name not listed, nothing for a listed repository
# openproj cannot read, the URL itself when one was written, and nothing for text
# that is neither
REFERENCES = {
    "C2SM/icon4py#12": "https://github.com/C2SM/icon4py/pull/12",
    "c2sm/ICON4PY#12": "https://github.com/C2SM/icon4py/pull/12",
    "jacopo/watchface#3": "https://git.example.org/jacopo/watchface/pulls/3",
    "someone/thing#4": "",
    "GridTools/gt4py#5": "https://github.com/GridTools/gt4py/pull/5",
    "https://git.example.org/jacopo/watchface/pulls/3": (
        "https://git.example.org/jacopo/watchface/pulls/3"
    ),
    "javascript:alert(1)": "",
    "see the meeting notes": "",
}


@pytest.mark.parametrize(
    "written",
    [
        "kilnlab/kiln4py",
        "https://github.com/kilnlab/kiln4py/",
        "https://github.com/kilnlab/kiln4py.git/x",
        "https://someone@github.com/kilnlab/kiln4py",
        "https://github.com/../..",
        "https://github.com/kilnlab/kiln4py?tab=pulls",
        "ftp://github.com/kilnlab/kiln4py",
    ],
)
def test_a_repository_is_named_by_its_page_and_nothing_else(written: str):
    with pytest.raises(ValueError, match="repository's page"):
        Config(repositories=[written])


def test_two_repositories_of_one_name_are_refused_because_a_reference_could_not_choose():
    with pytest.raises(ValueError, match="could not say which one"):
        Config(repositories=["https://github.com/a/b", "https://codeberg.org/A/B"])


@pytest.mark.parametrize(("ref", "href"), REFERENCES.items())
def test_a_reference_links_to_the_forge_its_repository_is_on(ref: str, href: str):
    from openproj.render.markdown import _pr_link, pr_href

    assert pr_href(ref, LISTED) == href
    link = [e for e in elements(str(_pr_link(ref, LISTED))) if e.tag == "a"]
    assert [e.attrs.get("href") for e in link] == ([href] if href else [])


def test_the_page_links_a_reference_where_the_server_does(seed_index):
    """The table draws its links in the browser, so the rule is in two languages.

    The map is one, `Links.pr_bases`, and each side keeps only the lookup. This
    runs the shipped `prHref` over the same references `pr_href` is judged on.
    """
    from test_injection import run_js

    from openproj.render import render_table

    page = render_table(seed_index, LISTED)
    said = run_js(page, f"{json.dumps(list(REFERENCES))}.map(prHref)", page=True)

    assert said["value"] == list(REFERENCES.values())


def _footer_warning(page: str) -> list:
    return [e for e in elements(page) if e.attrs.get("id") == "forgewarn"]


def test_a_repository_openproj_cannot_read_is_named_in_the_footer(seed_index):
    from openproj.render import render_table

    page = render_table(seed_index, LISTED)
    warning = _footer_warning(page)

    assert warning, "a repository on GitLab was listed and the footer said nothing"
    assert GITLAB in warning[0].attrs.get("title", "")
    assert FORGEJO not in warning[0].attrs.get("title", "")


def test_a_plan_whose_repositories_are_all_read_has_no_warning(seed_index):
    from openproj.render import render_table

    readable = ROUTES.model_copy(
        update={"repositories": ((GITHUB, "github"), (FORGEJO, "forgejo"))}
    )
    assert not _footer_warning(render_table(seed_index, readable))


def _host(answers: dict[str, httpx.Response], asked: list[httpx.Request]):
    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(request)
        return answers.get(request.url.path, httpx.Response(404, text="<h1>404</h1>"))

    return httpx.MockTransport(answer)


@pytest.mark.parametrize(
    ("answers", "forge"),
    [
        ({"/api/v1/version": httpx.Response(200, json={"version": "15.0.12"})}, "forgejo"),
        # A Forgejo that wants a signed-in caller, refusing in its own words
        (
            {
                "/api/v1/version": httpx.Response(
                    401,
                    json={
                        "message": "token is required",
                        "url": "https://git.example.org/api/swagger",
                    },
                )
            },
            "forgejo",
        ),
        ({}, "unsupported"),
        ({"/api/v1/version": httpx.Response(404, json={"error": "404 Not Found"})}, "unsupported"),
    ],
)
def test_a_host_is_asked_which_forge_it_is(answers: dict, forge: str):
    asked: list[httpx.Request] = []
    assert forge_of("https://git.example.org", transport=_host(answers, asked)) == forge
    assert [r.url.path for r in asked] == ["/api/v1/version"]


def test_github_is_known_by_its_name_and_never_asked():
    asked: list[httpx.Request] = []
    assert forge_of("https://github.com", transport=_host({}, asked)) == "github"
    assert asked == []


def test_a_host_that_does_not_answer_is_unreachable_and_not_unsupported():
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    assert forge_of("https://git.example.org", transport=httpx.MockTransport(down)) == (
        "unreachable"
    )


def test_a_forgejo_lists_its_open_pull_requests_and_issues_alike():
    asked: list[httpx.Request] = []
    transport = _host(
        {
            "/api/v1/repos/jacopo/watchface/issues": httpx.Response(
                200,
                json=[
                    {"number": 3, "title": "Second hand", "pull_request": {"merged": False}},
                    {"number": 2, "title": "Battery drains", "pull_request": None},
                ],
            )
        },
        asked,
    )
    found = open_references("https://git.example.org", "jacopo/watchface", "t0k", transport)

    assert found == [
        {"number": 3, "title": "Second hand", "pull": True},
        {"number": 2, "title": "Battery drains", "pull": False},
    ]
    assert asked[0].headers["authorization"] == "token t0k"
    assert asked[0].url.params["state"] == "open"


@pytest.mark.parametrize(
    ("said", "state"),
    [
        ({"state": "open"}, {"state": "open", "at": None}),
        (
            {
                "state": "closed",
                "closed_at": "2026-11-20T10:00:00Z",
                "pull_request": {"merged": True, "merged_at": "2026-11-19T10:00:00Z"},
            },
            {"state": "landed", "at": "2026-11-19"},
        ),
        (
            {
                "state": "closed",
                "closed_at": "2026-11-20T10:00:00Z",
                "pull_request": {"merged": False, "merged_at": None},
            },
            {"state": "dropped", "at": "2026-11-20"},
        ),
        (
            {"state": "closed", "closed_at": "2026-11-21T10:00:00Z", "pull_request": None},
            {"state": "landed", "at": "2026-11-21"},
        ),
    ],
)
def test_a_forgejo_reference_is_read_as_landed_dropped_or_open(said: dict, state: dict):
    transport = _host(
        {"/api/v1/repos/jacopo/watchface/issues/3": httpx.Response(200, json=said)}, []
    )
    assert reference_state("https://git.example.org", "jacopo/watchface", 3, "", transport) == (
        state,
        None,
    )
