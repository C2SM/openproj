"""A record from a selection: right-click words in the editor, make a record of
them, and the words become a link to it.

`design/body-tables-links-selection.md` §3 is the argument. The record page is
the right-click menu's fourth host (`pop.py`), it is one only while an edit is
open, and what it offers there is one item and nothing else.

The menu's own items are asked of the page's script in node, which is enough to
say what the box holds. The gesture is asked of Chrome, because whether a
right-click had a selection before it pressed is a fact about a real selection
in a real `<textarea>` and a real Ace — neither of which the node shim has.
"""

from __future__ import annotations

from pathlib import Path

import pygit2
import pytest
from fastapi.testclient import TestClient
from test_injection import run_js
from test_store import commit_directly
from test_web import ANN, PITCH, SECRET, SEED

from openproj.auth import sign_session
from openproj.web import SESSION_COOKIE, create_app

PLAIN = "?editor=plain"


def _served(tmp_path: Path, seed: dict[str, str]):
    path = tmp_path / "plan.git"
    pygit2.init_repository(str(path), bare=True, initial_head="main")
    commit_directly(path, seed, "seed the corpus")
    client = TestClient(create_app(path, auth="dev", secret=SECRET))
    client.cookies.set(SESSION_COOKIE, sign_session(ANN, SECRET))
    return client


@pytest.fixture
def client(tmp_path: Path):
    with _served(tmp_path, SEED) as made:
        yield made


# The menu's items as the page builds them, opened the way the gesture opens it
# but without one: `popMenu` on the edited record, which is the only id this host
# answers for. The press itself is Chrome's question, further down.
_ITEMS = """(() => {
  const id = document.getElementById('edit').dataset.id;
  const shut = popMenu(10, 10, id);
  flipEditing();
  const open = popMenu(10, 10, id);
  const top = popItems(POP_HOST.rows(id));
  const kinds = top[0].items ? top[0].items() : [];
  return {shut, open, top: top.map(one => [one.kind, one.text]),
          kinds: kinds.map(one => one.kind)};
})()"""


def test_in_a_session_the_menu_holds_one_item_and_the_kinds_this_plan_has(tmp_path: Path):
    """`New record from selection ▸ <kind>` and nothing else, and only the kinds
    `Config.allows`.

    Not the menu the other three hosts draw: on this page `Status ▸` and `Edit…`
    would be a second write path to the record whose own form is open around the
    editor, and `Delete…` would delete the document under it. And a kind this
    plan has switched off is a create the route refuses, so it is not offered.

    Asked first with no session open, because the page registers itself only
    while one is: a reader of the record keeps the browser's menu everywhere.
    """
    seed = dict(SEED)
    seed["config/defaults.yaml"] = SEED["config/defaults.yaml"] + "kinds: [note]\n"
    with _served(tmp_path, seed) as client:
        page = client.get(f"/detail/{PITCH}{PLAIN}").text
    answer = run_js(page, _ITEMS, page=True)
    assert not answer["errors"], answer["errors"]
    found = answer["value"]
    assert found["shut"] is False, "the menu answered on a record page with no edit open"
    assert found["open"] is True, "the menu did not open on the record page in a session"
    assert found["top"] == [["from-selection", "New record from selection"]], found["top"]
    # The planned four are always on, and `kinds: [note]` adds notes and not
    # issues — so issues are the control: the one kind the route would refuse.
    assert found["kinds"] == [
        "from-selection-product",
        "from-selection-project",
        "from-selection-pitch",
        "from-selection-task",
        "from-selection-note",
    ], found["kinds"]


def test_the_record_page_hands_the_menu_the_commit_it_was_rendered_at(client: TestClient):
    """`popStart` reads `#base` and a create advances it, so the record page's
    own `base_commit` input carries that id — and it is the same element the
    page's own save reads, so the two writes move one base and not two."""
    page = client.get(f"/detail/{PITCH}{PLAIN}").text
    answer = run_js(
        page,
        "(() => { const base = document.getElementById('base');"
        " return {named: base && base.name, same: base === BASE}; })()",
        page=True,
    )
    assert not answer["errors"], answer["errors"]
    assert answer["value"] == {"named": "base_commit", "same": True}
