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

import base64
import contextlib
import json
import time
from pathlib import Path

import pygit2
import pytest
from browser import _devtools, _evaluated, chrome, measured_in, press
from fastapi.testclient import TestClient
from test_coedit import _ROOM_STUB, _welcome
from test_editor import client, repo_path  # noqa: F401 - the record page, served to a writer
from test_injection import run_js
from test_store import commit_directly
from test_web import ANN, PITCH, PROJECT, SECRET, SEED

from openproj import coedit
from openproj.auth import sign_session
from openproj.web import SESSION_COOKIE, create_app

PLAIN = "?editor=plain"
_EDITORS = ("plain", "ace")


# --------------------------------------------------------------------------- #
# What the box holds
# --------------------------------------------------------------------------- #

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
    path = tmp_path / "plan.git"
    pygit2.init_repository(str(path), bare=True, initial_head="main")
    seed = dict(SEED)
    seed["config/defaults.yaml"] = SEED["config/defaults.yaml"] + "kinds: [note]\n"
    commit_directly(path, seed, "seed a plan that has notes and not issues")
    with TestClient(create_app(path, auth="dev", secret=SECRET)) as served:
        served.cookies.set(SESSION_COOKIE, sign_session(ANN, SECRET))
        page = served.get(f"/detail/{PITCH}{PLAIN}").text
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


def test_the_record_page_carries_only_the_menu_its_one_host_runs(client: TestClient):  # noqa: F811
    """`_pop_js(…, rows=False)`: the box, the form and the create door, and none
    of what only a row's menu runs — the standard list, the one-field writes,
    Edit…'s save, the delete face and the two doors only those reach. Asked of
    the bytes because the point is the bytes, and of a function from each part
    that went, so a part that came back is named."""
    page = client.get(f"/detail/{PITCH}{PLAIN}").text
    for kept in ("function popForm(", "async function popCreate(", "function popMenu("):
        assert kept in page, f"the record page lost {kept}"
    for gone in (
        "function popRowItems(",
        "function popCopy(",
        "function popWriteItems(",
        "function popStatusItem(",
        "function popEdited(",
        "function popLanded(",
        "function popAsk(",
        "async function popWrite(",
        "async function popDelete(",
        "#pop .popconfirm",
    ):
        assert gone not in page, f"the record page carries {gone}, which its host never runs"
    table = client.get("/table").text
    for kept in ("function popRowItems(", "async function popDelete(", "#pop .popconfirm"):
        assert kept in table, f"the table lost {kept} with the split"


_TITLES = {
    "**Port** the   transport": "Port the transport",
    "the `halo_exchange` _fast_ path": "the halo_exchange fast path",
    "~~old~~ new\n  wrapped line": "old new wrapped line",
    "👍 *done* — 表格": "👍 done — 表格",
}


def test_the_title_is_the_words_without_their_marks(client: TestClient):  # noqa: F811
    """What the form's title box opens holding: the markdown marks gone, every
    run of spaces and newlines one space. An underscore goes only at a word's
    edge, because `halo_exchange` is a name and `_fast_` is emphasis."""
    page = client.get(f"/detail/{PITCH}{PLAIN}").text
    answer = run_js(page, f"{json.dumps(list(_TITLES))}.map(selectionTitle)", page=True)
    assert not answer["errors"], answer["errors"]
    assert answer["value"] == list(_TITLES.values()), answer["value"]


# --------------------------------------------------------------------------- #
# The gesture, asked of Chrome
# --------------------------------------------------------------------------- #
#
# A right press is `press` (`browser.py`), so the browser itself decides the
# order of `pointerdown`, `mousedown` and `contextmenu` and Ace's own handlers run
# on it — which is the half of the claim a script-built event cannot make: a
# `MouseEvent` a page constructs runs no default action and no library code that
# a real press would. What the page decides about the browser's menu is
# `preventDefault()`, and that is what `__native` reads, after every listener of
# ours has run.

# The keyboard's way to the menu over a range, which every question below opens
# it by: a keydown, then a `contextmenu` at the focused element with no pointer
# behind it — the order a browser delivers ContextMenu and Shift+F10 in.
_OPEN_BY_KEY = """
window.__input = () => SURFACE.el.matches('textarea') ? SURFACE.el
  : SURFACE.el.querySelector('textarea');
window.openByKey = (from, to, key = 'ContextMenu', shift = false) => {
  popClose();
  SURFACE.setCaret(from, to);
  const input = window.__input();
  input.focus();
  input.dispatchEvent(new KeyboardEvent('keydown',
    {key: key, shiftKey: shift, bubbles: true, cancelable: true}));
  const menu = new MouseEvent('contextmenu',
    {bubbles: true, cancelable: true, shiftKey: shift, clientX: 0, clientY: 0});
  input.dispatchEvent(menu);
  return menu;
};
"""


@contextlib.contextmanager
def _in_chrome(client: TestClient, tmp_path: Path, editor: str):  # noqa: F811
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
        yield call


# Opens a session and answers where to press: on the first line of the document,
# inside the text, which every case below has selected or not as it needs. On Ace
# that is inside `.ace_content`, past the gutter, where its own mouse handler is.
_SETUP = (
    """(async () => {
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
  window.__on = SURFACE.el.querySelector('.ace_content') || SURFACE.el;
"""
    + _OPEN_BY_KEY
    + """
  const box = window.__on.getBoundingClientRect();
  return [Math.round(box.left + 30), Math.round(box.top + 10)];
})()"""
)

_AFTER = """(() => {
  const item = POP.querySelector('.popitem');
  return {open: popIsOpen(), native: window.__native,
          kinds: [...POP.querySelectorAll(':scope > .popitem')].map(one => one.dataset.kind),
          why: item ? item.dataset.why || '' : null};
})()"""


def _right_press(call, at: list[int], *, shift: bool = False) -> dict:
    press(call, at[0], at[1], "right", 8 if shift else 0)
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
        f" window.__input().focus(); window.__{select}(); true",
    )


@pytest.mark.parametrize("editor", _EDITORS)
def test_a_right_click_opens_this_menu_only_over_a_selection_made_before_it(
    client: TestClient,  # noqa: F811
    tmp_path: Path,
    editor: str,
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
    with _in_chrome(client, tmp_path, editor) as call:
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


# A context menu off the PRIMARY button: macOS's Ctrl+click, and Android's
# long-press, which arrives as a touch `pointerdown` with button 0. Neither has a
# right press for CDP to make on this machine, so the events are the page's own —
# which is enough here, because the claim is about which branch our listener
# takes and not about the browser's default action.
_PRIMARY = """(() => {
  const ask = (before, after) => {
    popClose();
    before();
    window.__on.dispatchEvent(new PointerEvent('pointerdown',
      {bubbles: true, cancelable: true, button: 0, ctrlKey: true, pointerType: 'mouse'}));
    after();
    const menu = new MouseEvent('contextmenu',
      {bubbles: true, cancelable: true, button: 0, ctrlKey: true, clientX: 60, clientY: 60});
    window.__on.dispatchEvent(menu);
    return {open: popIsOpen(), prevented: menu.defaultPrevented};
  };
  return {
    // The click selected the word under it: the browser's.
    selecting: ask(window.__none, window.__all),
    // The click landed on a selection already there and left it: ours.
    kept: ask(window.__all, () => {}),
  };
})()"""


@pytest.mark.parametrize("editor", _EDITORS)
def test_a_menu_off_the_primary_button_is_a_press_and_not_the_keyboard(
    client: TestClient,  # noqa: F811
    tmp_path: Path,
    editor: str,
):
    """Ctrl+click on a Mac selects the word it lands on and opens a menu, all off
    button 0. Reading only a right press took that for the keyboard, which skips
    the question of whether the press changed the selection — and drew this menu
    over the word the click had just selected, where the browser's belonged.
    Every `pointerdown` is a press; only no press since the last keydown is the
    keyboard. The second case is the control: a Ctrl+click on a selection that
    was already there does open ours."""
    with _in_chrome(client, tmp_path, editor) as call:
        _evaluated(call, _SETUP)
        got = _evaluated(call, _PRIMARY)
    assert got["selecting"] == {"open": False, "prevented": False}, (
        f"{editor}: a Ctrl+click that selected a word opened our menu: {got['selecting']}"
    )
    assert got["kept"] == {"open": True, "prevented": True}, (
        f"{editor}: a Ctrl+click on a selection already there opened nothing: {got['kept']}"
    )


_KEYED = """(() => {
  const answers = {};
  for (const [name, key, shift] of [['menu', 'ContextMenu', false], ['f10', 'F10', true]]) {
    window.__all();
    const {from, to} = SURFACE.caret();
    const menu = window.openByKey(from, to, key, shift);
    const box = POP.getBoundingClientRect();
    answers[name] = {open: popIsOpen(), prevented: menu.defaultPrevented,
                     focus: POP.contains(document.activeElement),
                     placed: box.top >= 0 && box.bottom <= innerHeight};
  }
  return answers;
})()"""


@pytest.mark.parametrize("editor", _EDITORS)
def test_the_menu_key_and_shift_f10_open_it_over_a_selection(
    client: TestClient,  # noqa: F811
    tmp_path: Path,
    editor: str,
):
    """The keyboard path, and no new chord: the two keys a browser already turns
    into a `contextmenu`. Shift+F10 carries Shift, and on this path it is not the
    pointer's way to the browser's menu. The box takes the keyboard, and it opens
    inside the window — on the textarea the focused element is the whole box,
    whose foot can be below it."""
    with _in_chrome(client, tmp_path, editor) as call:
        _evaluated(call, _SETUP)
        got = _evaluated(call, _KEYED)
    for name in ("menu", "f10"):
        assert got[name] == {"open": True, "prevented": True, "focus": True, "placed": True}, (
            f"{editor}, {name}: {got[name]}"
        )


# Every refusal and one control, each asked through the keyboard's path over a
# document written for it. Each paragraph holds one shape the renderer draws as
# something a link around it would break.
_REFUSED = """(() => {
  const body = [
    'Port the [aroma](pitch-b20000) transport.',
    '',
    'A second paragraph.',
    'See https://example.org/x here, and a [bracket.',
    '',
    'See [wrapped link',
    'text](pitch-b20000) now.',
    '',
    'Run `make check` first, see [the port][ref] and C2SM/icon4py#12.',
    '',
    '```',
    'fenced line',
    '```',
    '',
    '    indented line',
    '',
  ].join('\\n');
  SURFACE.splice(0, SURFACE.text().length, body);
  const at = words => body.indexOf(words);
  const ask = (from, to) => {
    window.openByKey(from, to);
    const item = POP.querySelector('.popitem[data-kind="from-selection"]');
    return item ? [item.getAttribute('aria-disabled') || '', item.dataset.why || ''] : null;
  };
  const answers = {
    paragraphs: ask(at('transport'), at(' paragraph')),
    holds: ask(0, at(' transport')),
    cuts: ask(at('aroma'), at(' transport') + 5),
    inside: ask(at('example'), at(' here')),
    bracket: ask(at('a [bracket'), at('bracket.') + 7),
    wrapped: ask(at('text]'), at('text]') + 4),
    code: ask(at('check'), at('check') + 5),
    reference: ask(at('the port'), at('the port') + 8),
    pr: ask(at('icon4py'), at('#12') + 3),
    fenced: ask(at('fenced'), at('fenced') + 11),
    indented: ask(at('indented'), at('indented') + 13),
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
    client: TestClient,  # noqa: F811
    tmp_path: Path,
    editor: str,
):
    """Every way `[words](id)` would be broken, each drawn as the item greyed with
    its reason on it, and one that is fine as the control.

    The link that wraps a line is the case a scan of the selection's own lines
    cannot see: `text` on the second line is as inside that link as a word on
    its first. A PR reference is a link the renderer makes, and one inside a link
    is drawn as text. Code draws a link as the text it is. A `[` or `]` is the
    plan author's addition to the spec's three: a bracket ends a link's text, and
    the result is drawn as literal text with nothing to say it failed.
    """
    with _in_chrome(client, tmp_path, editor) as call:
        _evaluated(call, _SETUP)
        got = _evaluated(call, _REFUSED)
    paragraphs = "The selection runs across more than one paragraph, and a link cannot."
    inside = "The selection is inside a link."
    code = "The selection is in code, where a link would be drawn as plain text."
    expected = {
        "paragraphs": paragraphs,
        "holds": "The selection already holds a link.",
        "cuts": "The selection cuts across a link.",
        "inside": inside,
        "bracket": "The selection holds a [ or a ], which would end the link it becomes.",
        "wrapped": inside,
        "code": code,
        "reference": inside,
        "pr": inside,
        "fenced": code,
        "indented": code,
    }
    for name, why in expected.items():
        assert got[name] == ["true", why], f"{editor}, {name}: {got[name]}"
    assert got["fine"] == ["", ""], f"{editor}: a plain sentence was refused: {got['fine']}"
    assert got["said"] == expected["bracket"] and got["stillOpen"] is True, got


# --------------------------------------------------------------------------- #
# The form, the create, and the link
# --------------------------------------------------------------------------- #

# The room's own stub (`tests/test_coedit.py`) — a socket that never leaves the
# page, and a `fetch` that answers the preview — with the create route on top of
# it. Installed before the page's own scripts: the session opens the socket, and
# a stub put in afterwards would be put in after it was asked for.
_STUBS = (
    _ROOM_STUB
    + """
window.__posts = [];
const previewing = window.fetch;
window.fetch = async (url, options) => {
  const asked = options || {};
  if (String(url) !== '/api/record' || asked.method !== 'POST') return previewing(url, options);
  window.__posts.push(JSON.parse(asked.body));
  return new Response(JSON.stringify(
    {id: 'task-000123', outcome: 'committed', commit: 'c0ffee1', pushed: true}),
    {status: 201, headers: {'content-type': 'application/json'}});
};
"""
)

# The way into the form for one kind — the item, then the kind in the list that
# opens beside it — and what the questions below read.
_HELPERS = (
    _OPEN_BY_KEY
    + """
const rest = ms => new Promise(done => setTimeout(done, ms));
const choose = kind => {
  POP.querySelector('.popitem[data-kind="from-selection"]').click();
  document.querySelector(`#popsub .popitem[data-kind="from-selection-${kind}"]`).click();
};
const save = () => POP.querySelector('[data-kind="form-save"]').click();
const said = () => document.getElementById('state').textContent;
const titleBox = () => POP.querySelector('input[data-field="title"]');
if (!document.querySelector('article.record').classList.contains('editing')) flipEditing();
await rest(100);
"""
)


def _at_the_record(
    client: TestClient,  # noqa: F811
    tmp_path: Path,
    script: str,
    editor: str = "plain",
    name: str = "page",
) -> dict:
    page = client.get(f"/detail/{PITCH}?editor={editor}").text
    stubbed = page.replace('<link rel="icon"', f'<script>{_STUBS}</script><link rel="icon"', 1)
    answer = measured_in(
        chrome(),
        stubbed,
        tmp_path / f"{name}-{editor}.html",
        1280,
        _HELPERS + script,
        patience=4000,
        query=f"?editor={editor}",
    )
    assert not answer.get("errors"), answer.get("errors")
    return answer


_THE_FORM = """
const body = 'Write **Port** the   transport now.\\n';
SURFACE.splice(0, SURFACE.text().length, body);
const words = '**Port** the   transport';
const at = body.indexOf(words);
const opened = {};
for (const kind of ['task', 'project']) {
  window.openByKey(at, at + words.length);
  choose(kind);
  await rest(50);
  const fact = POP.querySelector('.card-fact[data-field="parent"]');
  opened[kind] = {title: titleBox() && titleBox().value,
                  focused: document.activeElement === titleBox(),
                  heading: POP.querySelector('[data-kind="form-heading"]').textContent,
                  locked: fact.classList.contains('poplocked'),
                  opens: fact.classList.contains('popopens'),
                  depends: !!POP.querySelector('.card-fact[data-field="depends_on"] input')};
  popOpenField('parent');
  const picker = POP.querySelector('select[data-field="parent"]');
  opened[kind].parent = picker.value;
  opened[kind].offered = [...picker.options].map(one => one.value);
  opened[kind].disabled = picker.disabled;
  // Cancel, which must leave having sent nothing.
  POP.querySelector('[data-kind="form-cancel"]').click();
  await rest(50);
}
const cancelled = {posts: window.__posts.length, text: SURFACE.text(), open: popIsOpen()};
// And once more, saved: the parent cleared, which is the whole of "not locked".
window.openByKey(at, at + words.length);
choose('task');
await rest(50);
popOpenField('parent');
const picker = POP.querySelector('select[data-field="parent"]');
picker.value = '';
picker.dispatchEvent(new Event('change', {bubbles: true}));
const base = BASE.value;
save();
await rest(700);
return {opened, cancelled, posts: window.__posts, base, now: BASE.value,
        text: SURFACE.text(), said: said(), open: popIsOpen(),
        focus: SURFACE.el.contains(document.activeElement), errors: window.__errors};
"""


def test_a_kind_opens_the_form_titled_from_the_selection_and_filed_where_it_may_be(
    client: TestClient,  # noqa: F811
    tmp_path: Path,
):
    """The title is the words without their marks, and the parent is the record
    being edited where that kind may be its child — and NOT locked.

    `New child ▸` locks its parent because choosing it again is the gesture said
    twice; here nobody has chosen anything yet, so the default is an answer in
    the box like any other, and clearing it sends no parent. A pitch may hold a
    task and may not hold a project, so the project's form opens with no parent
    and offers only the records a project may be filed under — of which this
    corpus has none.

    Cancel is asked first, twice, and must have sent nothing: a create is not
    idempotent, and the form is the thing standing in front of it.

    **And the page's own base does not move.** It is what this record's save is
    compared against, and a create advancing it would move the page past commits
    it never saw — somebody else's change to this record, then this create, then
    the page's Save sent against the create's commit, which writes over theirs
    without a conflict. The create of a new file needs no newer base than the
    page has, so it is sent the page's and leaves it where it was.
    """
    got = _at_the_record(client, tmp_path, _THE_FORM, name="form")
    assert not got["errors"], got["errors"]
    task, project = got["opened"]["task"], got["opened"]["project"]
    for kind, opened in got["opened"].items():
        assert opened["title"] == "Port the transport", f"{kind}: {opened['title']!r}"
        assert opened["focused"], f"{kind}: the form did not open on its title"
        assert opened["locked"] is False and opened["opens"] is True, (
            f"{kind}: the parent is locked, which is New child's rule and not this one's"
        )
        assert opened["depends"] is False
    assert task["heading"] == "New task from the selection"
    assert task["parent"] == PITCH, "a task's form did not default to the pitch it was written in"
    assert task["disabled"] is False
    assert "" in task["offered"] and PROJECT in task["offered"], task["offered"]
    assert project["parent"] == "", "a project was filed under a pitch, which may not hold one"
    assert project["offered"] == [""], project["offered"]

    assert got["cancelled"] == {
        "posts": 0,
        "text": "Write **Port** the   transport now.\n",
        "open": False,
    }, got["cancelled"]

    assert len(got["posts"]) == 1, f"one Save sent {len(got['posts'])} creates"
    sent = got["posts"][0]
    assert sent["fields"]["kind"] == "task"
    assert sent["fields"]["title"] == "Port the transport"
    assert "parent" not in sent["fields"], "a parent cleared in the box was sent anyway"
    assert "depends_on" not in sent["fields"]
    assert sent["body"] is None, "a record made from a selection opens with a body"
    assert sent["base_commit"] == got["base"], "the create was not sent the page's base"
    assert got["now"] == got["base"], (
        f"the create moved the page's base to {got['now']}, past whatever this record's "
        "own save has not seen yet"
    )
    assert got["text"] == "Write [**Port** the   transport](task-000123) now.\n", got["text"]
    assert got["said"] == "Created task-000123 and linked it."
    assert got["open"] is False
    assert got["focus"], "the keyboard did not come back to the editor"


# One person selects words and makes a record of them while the document goes on
# changing — somebody else's frame, or this person's own typing — before Save. The
# welcome is taken before anybody else's edit, so it arrives as a frame while the
# form is open; what the page sends afterwards is applied to the same real `Room`,
# so the claim is about the document everybody holds and not about one tab's box.
_IN_A_ROOM = """
window.__room.onmessage({data: WELCOME});
await rest(150);
const text = SURFACE.text();
const at = text.indexOf(WORDS);
window.openByKey(at, at + WORDS.length);
choose('task');
await rest(50);
const title = titleBox() && titleBox().value;
if (REMOTE) window.__room.onmessage({data: JSON.stringify({t: 'update', u: REMOTE})});
if (MINE) SURFACE.splice(0, 0, MINE);
await rest(150);
const between = SURFACE.text();
save();
await rest(800);
return {title, between, text: SURFACE.text(), said: said(), posts: window.__posts.length,
        focus: SURFACE.el.contains(document.activeElement), sent: window.__sent,
        errors: window.__errors};
"""

WORDS = "blend-weight coefficients"


def _a_room(client: TestClient, theirs=None) -> tuple:  # noqa: F811
    """A real room on the pitch, its welcome, and somebody else's edit to it as a
    frame the page has not yet been sent — or none."""
    shown = client.get("/api/index.json").json()["plan"][PITCH]["body"]
    assert WORDS in shown, "the pitch's body does not hold the words this test selects"
    path = f"pitches/{PITCH}.md"
    room = coedit.Room(PITCH, path, "0" * 40, shown)
    welcome = _welcome(room)
    if theirs is None:
        return room, welcome, "", shown
    bob = coedit.Room(PITCH, path, "0" * 40, shown)
    update = bob.absorb(theirs(shown))
    assert update, "the other copy produced no update"
    room.apply(update, "bob")
    return room, welcome, base64.b64encode(update).decode(), bob.body()


def _in_the_room(client, tmp_path, editor, room, welcome, remote, mine, name) -> dict:  # noqa: F811
    script = (
        f"const WELCOME = {json.dumps(json.dumps(welcome))};\n"
        f"const REMOTE = {json.dumps(remote)};\n"
        f"const MINE = {json.dumps(mine)};\n"
        f"const WORDS = {json.dumps(WORDS)};\n" + _IN_A_ROOM
    )
    got = _at_the_record(client, tmp_path, script, editor=editor, name=name)
    assert not got["errors"], got["errors"]
    for frame in got["sent"]:
        if frame["t"] == "update":
            room.apply(base64.b64decode(frame["u"]), "ann")
    return got


@pytest.mark.parametrize("editor", _EDITORS)
def test_an_edit_before_the_selection_moves_it_and_the_link_lands_on_the_words(
    client: TestClient,  # noqa: F811
    tmp_path: Path,
    editor: str,
):
    """Somebody types an emoji at the top of the document while the form is open,
    and the link still wraps exactly the words that were selected.

    The range is the room's (`COEDIT.mark`, Yjs relative positions), and an
    emoji is two UTF-16 code units, so a range carried by one character instead
    of by its length would wrap the words one unit off — and the words at the
    offsets they had at the press are not the words any more, so without the
    range the page would say they changed and link nothing.
    """
    room, welcome, remote, theirs = _a_room(client, lambda shown: "👍 " + shown)
    got = _in_the_room(client, tmp_path, editor, room, welcome, remote, "", "before")
    assert got["title"] == WORDS
    assert got["between"] == theirs, "the other person's edit did not reach the box"
    linked = theirs.replace(WORDS, f"[{WORDS}](task-000123)")
    assert got["text"] == linked, f"{editor}: {got['text']!r}"
    assert got["said"] == "Created task-000123 and linked it."
    assert got["focus"], "the keyboard did not come back to the editor"
    assert room.body() == linked, (
        f"{editor}: the box and the room disagree after the link: {room.body()!r}"
    )


@pytest.mark.parametrize("editor", _EDITORS)
def test_typing_of_ones_own_before_the_selection_moves_it_too(
    client: TestClient,  # noqa: F811
    tmp_path: Path,
    editor: str,
):
    """The same, typed by the person who opened the form, into the editor, while
    it is open. Their keystrokes reach the room through `typed` on the textarea
    and through Ace's own deltas on Ace, so the room's range follows them as it
    follows anybody's — and the link lands on the words with the writing in
    front of it, in the box and in the room."""
    room, welcome, _, shown = _a_room(client)
    mine = "✍️ A line written while the form was open.\n"
    got = _in_the_room(client, tmp_path, editor, room, welcome, "", mine, "mine")
    assert got["between"] == mine + shown, f"{editor}: the typing did not land: {got['between']!r}"
    linked = (mine + shown).replace(WORDS, f"[{WORDS}](task-000123)")
    assert got["text"] == linked, f"{editor}: {got['text']!r}"
    assert got["said"] == "Created task-000123 and linked it."
    assert room.body() == linked, f"{editor}: the room holds {room.body()!r}"


@pytest.mark.parametrize("editor", _EDITORS)
def test_the_selected_words_changed_meanwhile_so_the_record_is_made_and_not_linked(
    client: TestClient,  # noqa: F811
    tmp_path: Path,
    editor: str,
):
    """Somebody in the room edits the selected words while the form is open: the
    record is still made, nothing is written into the document, and the page
    says so with the id, so it can be linked by hand.

    A link written around somebody else's half-edited sentence would be worse
    than no link at all, and a create held back would throw away the form.
    """
    room, welcome, remote, theirs = _a_room(
        client, lambda shown: shown.replace("blend-weight", "blending-weight")
    )
    got = _in_the_room(client, tmp_path, editor, room, welcome, remote, "", "changed")
    assert got["posts"] == 1, "the record was not made"
    assert got["text"] == theirs, f"{editor}: something was written: {got['text']!r}"
    assert got["said"] == (
        "Created task-000123. The text you selected changed, so it wasn't linked."
    )
    assert room.body() == theirs
