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

import contextlib
import time
from pathlib import Path

import pygit2
import pytest
from browser import PRESSES, _devtools, _evaluated, chrome
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


# The menu's items as the page builds them, opened by the keyboard's path — a
# `contextmenu` with no press before it, over a selection in the box. Whether a
# POINTER's press opens it is Chrome's question, further down; this one is only
# about what the box holds once it is up.
_ITEMS = """(() => {
  const id = document.getElementById('edit').dataset.id;
  const box = document.querySelector('[name=body]');
  const ask = () => {
    box.selectionStart = 0;
    box.selectionEnd = 4;
    box.dispatchEvent(new Event('contextmenu'));
    return popIsOpen();
  };
  const shut = ask();
  flipEditing();
  const open = ask();
  const top = popItems(POP_HOST.rows(id));
  const kinds = top[0].items ? top[0].items() : [];
  return {shut, open, top: top.map(one => [one.kind, one.text, one.why || '']),
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
    assert found["top"] == [["from-selection", "New record from selection", ""]], found["top"]
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


# --------------------------------------------------------------------------- #
# The gesture, asked of Chrome with trusted presses
# --------------------------------------------------------------------------- #
#
# A right press is `Input.dispatchMouseEvent`, so the browser itself decides the
# order of `pointerdown`, `mousedown` and `contextmenu` and Ace's own handlers run
# on it — which is the half of the claim a script-built event cannot make: a
# `MouseEvent` a page constructs runs no default action and no library code that
# a real press would. What the page decides about the browser's menu is
# `preventDefault()`, and that is what `__native` reads, after every listener of
# ours has run.

_EDITORS = ("plain", "ace")


@contextlib.contextmanager
def _in_chrome(client: TestClient, tmp_path: Path, editor: str):
    """The record page in a session, in Chrome, on the surface asked for.

    The query goes on the request AND on the file's URL: the server decides from
    it whether Ace's bytes are in the page, and the page decides from
    `location.search` which surface to mount on them.
    """
    page = client.get(f"/detail/{PITCH}?editor={editor}").text
    where = tmp_path / f"{editor}.html"
    where.write_text(page)
    with _devtools(
        chrome(),
        where.as_uri() + f"?editor={editor}",
        tmp_path / f"profile-{editor}",
        ("--window-size=1280,900",),
    ) as (call, said):
        time.sleep(2)
        yield call, said


# Opens a session and answers where to press: on the first line of the document,
# inside the text, which every case below has selected or not as it needs. On Ace
# that is inside `.ace_content`, past the gutter, where its own mouse handler is.
_SETUP = """(async () => {
  window.__native = null;
  addEventListener('contextmenu', event => {
    window.__native = {prevented: event.defaultPrevented, shift: event.shiftKey};
  });
  // The macOS case, made on any machine: the press itself selects the word under
  // it, after `pointerdown` and before `contextmenu` — which is `mousedown`.
  window.__mac = false;
  document.addEventListener('mousedown', () => { if (window.__mac) window.__all(); }, true);
  if (!document.querySelector('article.record').classList.contains('editing')) flipEditing();
  await new Promise(done => setTimeout(done, 300));
  window.__all = () => SURFACE.setCaret(0, SURFACE.text().replace(/\\s+$/, '').length);
  window.__none = () => SURFACE.setCaret(3);
  window.__input = SURFACE.el.matches('textarea') ? SURFACE.el
    : SURFACE.el.querySelector('textarea');
  const box = (SURFACE.el.querySelector('.ace_content') || SURFACE.el).getBoundingClientRect();
  return [Math.round(box.left + 30), Math.round(box.top + 10)];
})()"""

_AFTER = """(() => {
  const item = POP.querySelector('.popitem');
  return {open: popIsOpen(), native: window.__native,
          kinds: [...POP.querySelectorAll(':scope > .popitem')].map(one => one.dataset.kind),
          why: item ? item.dataset.why || '' : null};
})()"""


def _right_press(call, at: list[int], *, shift: bool = False) -> dict:
    for kind in ("mousePressed", "mouseReleased"):
        call(
            "Input.dispatchMouseEvent",
            {
                "type": kind,
                "x": at[0],
                "y": at[1],
                "button": "right",
                "clickCount": 1,
                "buttons": PRESSES["right"] if kind == "mousePressed" else 0,
                # CDP's modifier mask: Shift is 8.
                "modifiers": 8 if shift else 0,
            },
        )
        time.sleep(0.1)
    time.sleep(0.4)
    return _evaluated(call, _AFTER)


def _before(call, select: str, mac: bool = False) -> None:
    """The editor focused, as it is when somebody has just selected in it: a
    press on an unfocused `<textarea>` focuses it first, and focusing one by the
    mouse puts the caret where it was pressed — which is a selection the press
    changed, and so the browser's menu, correctly."""
    _evaluated(
        call,
        f"popClose(); window.__native = null; window.__mac = {str(mac).lower()};"
        f" window.__input.focus(); window.__{select}(); true",
    )


@pytest.mark.parametrize("editor", _EDITORS)
def test_a_right_click_opens_this_menu_only_over_a_selection_made_before_it(
    client: TestClient, tmp_path: Path, editor: str
):
    """Ours over a selection that was there before the press; the browser's for
    everything else.

    "Before the press" is the whole rule, and the macOS case is why: a
    right-click on a word in a textarea selects that word before `contextmenu`
    fires, so reading the selection then would take the browser's menu — and its
    spelling suggestions — away from nearly every right-click in the editor. It
    is made here on any machine by selecting the document in `mousedown`, which
    is between the two events, and a page that read the selection at
    `contextmenu` would open its own menu on it.

    The first press is the control for the other three: without it, a page with
    no menu wired at all passes every one of them.
    """
    with _in_chrome(client, tmp_path, editor) as (call, said):
        at = _evaluated(call, _SETUP)
        _before(call, "all")
        selected = _right_press(call, at)
        _before(call, "all")
        shifted = _right_press(call, at, shift=True)
        _before(call, "none")
        bare = _right_press(call, at)
        _before(call, "none", mac=True)
        mac = _right_press(call, at)

    assert selected["native"], "the press produced no contextmenu event at all"
    assert selected["open"] is True, f"{editor}: a right-click on a selection opened nothing"
    assert selected["native"]["prevented"] is True, (
        f"{editor}: the page opened its menu and left the browser's to open on top of it"
    )
    assert selected["kinds"] == ["from-selection"] and selected["why"] == "", selected

    assert shifted["native"]["shift"] is True, "the shift key did not reach the page"
    assert shifted["open"] is False, f"{editor}: Shift and right-click opened our menu"
    assert shifted["native"]["prevented"] is False, (
        f"{editor}: the one press that exists to reach the browser's menu did not"
    )

    assert bare["open"] is False, f"{editor}: a right-click with nothing selected opened ours"
    assert bare["native"]["prevented"] is False, (
        f"{editor}: a right-click with nothing selected took the browser's menu away"
    )

    assert mac["native"], "the macOS press produced no contextmenu event"
    assert mac["open"] is False and mac["native"]["prevented"] is False, (
        f"{editor}: a selection the press itself made was read as one made before "
        "it, which on macOS is nearly every right-click there is"
    )


# The keyboard's two ways to a menu, delivered the way the browser delivers them:
# a keydown, and then a `contextmenu` at the focused element with no pointer
# behind it. Shift+F10 carries Shift, and on this path it is not the pointer's way
# to the browser's menu.
_KEYED = """(() => {
  const answers = {};
  for (const [name, key, shift] of [['menu', 'ContextMenu', false], ['f10', 'F10', true]]) {
    popClose();
    window.__all();
    window.__input.focus();
    window.__input.dispatchEvent(new KeyboardEvent('keydown',
      {key: key, shiftKey: shift, bubbles: true, cancelable: true}));
    const menu = new MouseEvent('contextmenu',
      {bubbles: true, cancelable: true, shiftKey: shift, clientX: 0, clientY: 0});
    window.__input.dispatchEvent(menu);
    const box = POP.getBoundingClientRect();
    answers[name] = {open: popIsOpen(), prevented: menu.defaultPrevented,
                     focus: POP.contains(document.activeElement),
                     placed: box.top >= 0 && box.bottom <= innerHeight};
  }
  return answers;
})()"""


@pytest.mark.parametrize("editor", _EDITORS)
def test_the_menu_key_and_shift_f10_open_it_over_a_selection(
    client: TestClient, tmp_path: Path, editor: str
):
    """The keyboard path, and no new chord: the two keys a browser already turns
    into a `contextmenu`. The box takes the keyboard, and it opens inside the
    window — on the textarea the focused element is the whole box, whose foot
    can be below it."""
    with _in_chrome(client, tmp_path, editor) as (call, said):
        _evaluated(call, _SETUP)
        got = _evaluated(call, _KEYED)
    for name in ("menu", "f10"):
        assert got[name] == {"open": True, "prevented": True, "focus": True, "placed": True}, (
            f"{editor}, {name}: {got[name]}"
        )


# Every refusal and one control, each asked through the keyboard's path over a
# document written for it.
_REFUSED = """(() => {
  const body = 'Port the [aroma](pitch-b20000) transport.\\n\\nA second paragraph.\\n'
    + 'See https://example.org/x here, and a [bracket.\\n';
  SURFACE.splice(0, SURFACE.text().length, body);
  const at = words => body.indexOf(words);
  const ask = (from, to) => {
    popClose();
    SURFACE.setCaret(from, to);
    window.__input.focus();
    window.__input.dispatchEvent(new MouseEvent('contextmenu',
      {bubbles: true, cancelable: true, clientX: 0, clientY: 0}));
    const item = POP.querySelector('.popitem[data-kind="from-selection"]');
    return item ? [item.getAttribute('aria-disabled') || '', item.dataset.why || ''] : null;
  };
  const answers = {
    paragraphs: ask(at('transport'), at(' paragraph')),
    holds: ask(0, at(' transport')),
    cuts: ask(at('aroma'), at(' transport') + 5),
    inside: ask(at('example'), at(' here')),
    bracket: ask(at('a [bracket'), at('bracket.') + 7),
    fine: ask(at('A second'), at(' paragraph')),
  };
  // And a refused item, pressed, says why rather than acting.
  ask(at('a [bracket'), at('bracket.') + 7);
  POP.querySelector('.popitem[data-kind="from-selection"]').click();
  answers.said = document.getElementById('state').textContent;
  answers.stillOpen = popIsOpen();
  return answers;
})()"""


@pytest.mark.parametrize("editor", _EDITORS)
def test_a_selection_that_cannot_become_a_link_is_refused_with_the_reason(
    client: TestClient, tmp_path: Path, editor: str
):
    """Four ways `[words](id)` would be broken, each drawn as the item greyed with
    its reason on it, and one that is fine as the control.

    A `[` or `]` is the plan author's addition to the spec's three: a bracket
    ends a link's text or starts another one, and the result is drawn as literal
    text with no link in it and nothing to say it failed.
    """
    with _in_chrome(client, tmp_path, editor) as (call, said):
        _evaluated(call, _SETUP)
        got = _evaluated(call, _REFUSED)
    refused = "true"
    assert got["paragraphs"] == [
        refused,
        "The selection runs across more than one paragraph, and a link cannot.",
    ], got
    assert got["holds"] == [refused, "The selection already holds a link."], got
    assert got["cuts"] == [refused, "The selection cuts across a link."], got
    assert got["inside"] == [refused, "The selection is inside a link."], got
    assert got["bracket"] == [
        refused,
        "The selection holds a [ or a ], which would end the link it becomes.",
    ], got
    assert got["fine"] == ["", ""], f"{editor}: a plain sentence was refused: {got['fine']}"
    assert got["said"] == got["bracket"][1] and got["stillOpen"] is True, got
