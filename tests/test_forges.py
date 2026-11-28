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
UNREACHABLE = "https://git.example.me/j/site"

LISTED = ROUTES.model_copy(
    update={
        "repositories": (
            (GITHUB, "github"),
            (FORGEJO, "forgejo"),
            (GITLAB, "unsupported"),
            (UNREACHABLE, "unreachable"),
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


# Each URL, and the reference it is drawn as — jcanton, 2026-11-28: plan-d stored
# its Forgejo pull requests as full URLs and the page drew them that way. A listed
# repository's page with GitHub's or Forgejo's spelling, an issue, a trailing tab
# or anchor, a host in capitals; GitHub's whether listed or not; and the near
# misses that must stay as written: a dot segment that would send the link to
# another pull request than the one drawn, a host that only LOOKS like github.com
# (a dotless ı, which Python's case folding let through), a name that is not
# ASCII, a repository whose name only STARTS like a listed one, a number with a
# letter on it, GitLab's own spelling, and anything that is already a reference or
# is not a link at all. A repository whose forge could not be asked is drawn short
# too: the href is still the URL.
SHORTENED = {
    "https://git.example.org/jacopo/watchface/pulls/3": "jacopo/watchface#3",
    "https://git.example.org/jacopo/watchface/issues/7": "jacopo/watchface#7",
    "https://GIT.example.org/jacopo/watchface/pulls/3/files": "jacopo/watchface#3",
    "https://github.com/C2SM/icon4py/pull/12#discussion_r1": "C2SM/icon4py#12",
    "https://github.com/GridTools/gt4py/pull/5": "GridTools/gt4py#5",
    "https://github.com/GridTools/gt4py/issues/6?x=1": "GridTools/gt4py#6",
    "https://git.example.me/j/site/pulls/1": "j/site#1",
    "https://github.com/a/b/pull/1/../../x/y/pull/9": "",
    "https://github.com/a/b/pull/1/%2e%2e/9": "",
    "https://gıthub.com/C2SM/icon4py/pull/1": "",
    "https://github.com/ä/b/pull/1": "",
    "https://git.example.org/jacopo/watchface-two/pulls/3": "",
    "https://git.example.org/jacopo/watchface/pulls/3x": "",
    "https://gitlab.com/someone/thing/-/merge_requests/4": "",
    "C2SM/icon4py#12": "",
    "see the meeting notes": "",
}


@pytest.mark.parametrize(("url", "ref"), SHORTENED.items())
def test_a_pull_request_url_is_drawn_as_the_reference_it_names(url: str, ref: str):
    """And links to the URL as written: the file is not what changes."""
    from openproj.render.markdown import _pr_link, pr_href, pr_reference

    assert pr_reference(url, LISTED) == ref
    link = [e for e in elements(str(_pr_link(url, LISTED))) if e.tag == "a"]
    if pr_href(url, LISTED):
        assert [(e.attrs["href"], e.text) for e in link] == [(pr_href(url, LISTED), ref or url)]


def test_the_page_reads_a_url_back_into_the_reference_the_server_does(seed_index):
    """`prReference` is `pr_reference` over the same map, `Links.pr_pages`."""
    from test_injection import run_js

    from openproj.render import render_table

    page = render_table(seed_index, LISTED)
    said = run_js(page, f"{json.dumps(list(SHORTENED))}.map(prReference)", page=True)

    assert said["value"] == list(SHORTENED.values())


def test_the_table_draws_a_stored_url_as_its_number(seed_index):
    """The cell keeps only the number, as it does for a reference, with the whole
    reference in the title."""
    from test_injection import run_js

    from openproj.render import render_table

    url = "https://git.example.org/jacopo/watchface/pulls/3"
    page = render_table(seed_index, LISTED)
    drawn = run_js(page, f"prLink({json.dumps(url)})", page=True)["value"]

    assert [(e.attrs["href"], e.attrs["title"], e.text) for e in elements(drawn)] == [
        (url, "jacopo/watchface#3", "#3")
    ]


def test_the_prs_box_writes_a_pasted_url_as_the_reference_it_names(seed_index):
    """The box used to read the plan's pages out of its own copy of the rule, and it
    is the shell's `prReference` now."""
    from test_injection import run_js

    from openproj.render import render_detail

    url = "https://git.example.org/jacopo/watchface/pulls/3"
    page = render_detail(
        seed_index, LISTED, only=next(iter(seed_index.plan)), base_commit="deadbee", may_write=True
    )

    unread = f"{UNREACHABLE}/pulls/1"
    said = run_js(page, f"[asReference({json.dumps(url)}), asReference({json.dumps(unread)})]",
                  page=True)["value"]

    # And a paste from a forge that cannot be linked by reference keeps its URL
    assert said == ["jacopo/watchface#3", None]


def test_a_bare_url_in_prose_reads_as_its_reference_and_written_words_are_kept():
    from openproj.render.markdown import _markdown

    forgejo = "https://git.example.org/jacopo/watchface/pulls"
    body = (
        f"landed in {forgejo}/3 and <https://github.com/a/b/pull/9>, "
        f"see [the fix]({forgejo}/4), and `{forgejo}/5` is code"
    )
    links = [(e.attrs["href"], e.text) for e in elements(str(_markdown(body, LISTED)))
             if e.tag == "a"]

    assert links == [
        (f"{forgejo}/3", "jacopo/watchface#3"),
        ("https://github.com/a/b/pull/9", "a/b#9"),
        (f"{forgejo}/4", "the fix"),
    ]


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
