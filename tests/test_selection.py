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
from browser import PRESSES, _devtools, _evaluated, chrome, measured_in
from fastapi.testclient import TestClient
from test_injection import run_js
from test_store import commit_directly
from test_web import ANN, PITCH, PROJECT, SECRET, SEED

from openproj import coedit
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


_TITLES = {
    "**Port** the   transport": "Port the transport",
    "the `halo_exchange` _fast_ path": "the halo_exchange fast path",
    "~~old~~ new\n  wrapped line": "old new wrapped line",
    "👍 *done* — 表格": "👍 done — 表格",
}


def test_the_title_is_the_words_without_their_marks(client: TestClient):
    """What the form's title box opens holding: the markdown marks gone, every
    run of spaces and newlines one space. An underscore goes only at a word's
    edge, because `halo_exchange` is a name and `_fast_` is emphasis."""
    page = client.get(f"/detail/{PITCH}{PLAIN}").text
    answer = run_js(page, f"{json.dumps(list(_TITLES))}.map(selectionTitle)", page=True)
    assert not answer["errors"], answer["errors"]
    assert answer["value"] == list(_TITLES.values()), answer["value"]


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


# --------------------------------------------------------------------------- #
# The form, the create, and the link
# --------------------------------------------------------------------------- #

# What the create route answers, and a socket that never leaves the page — the
# frames the editor writes are kept for the test to hand to a real `Room`, and the
# frames the test delivers go in through `onmessage`. Installed before the page's
# own scripts, the way `tests/test_coedit.py` installs its own: the session opens
# the socket, and a stub put in afterwards would be put in after it was asked for.
_STUBS = """
window.__errors = [];
addEventListener('error', event => window.__errors.push(String(event.message)));
window.__posts = [];
window.fetch = async (url, options) => {
  const asked = options || {};
  if (String(url) === '/api/record' && asked.method === 'POST') {
    window.__posts.push(JSON.parse(asked.body));
    return new Response(JSON.stringify(
      {id: 'task-000123', outcome: 'committed', commit: 'c0ffee1', pushed: true}),
      {status: 201, headers: {'content-type': 'application/json'}});
  }
  return new Response(JSON.stringify({html: '<p data-startline="1">rendered</p>'}),
    {status: 200, headers: {'content-type': 'application/json'}});
};
window.__sent = [];
function FakeSocket() {
  this.readyState = 1;
  window.__room = this;
  setTimeout(() => { if (this.onopen) this.onopen(); }, 0);
}
FakeSocket.OPEN = 1;
FakeSocket.prototype.send = function (data) { window.__sent.push(JSON.parse(data)); };
FakeSocket.prototype.close = function () { this.readyState = 3; };
window.WebSocket = FakeSocket;
"""

# The keyboard's way to the menu over a range, and the way into the form for one
# kind: the item, then the kind in the list that opens beside it.
_HELPERS = """
const rest = ms => new Promise(done => setTimeout(done, ms));
const input = () => SURFACE.el.matches('textarea') ? SURFACE.el
  : SURFACE.el.querySelector('textarea');
const menuOn = (from, to) => {
  popClose();
  SURFACE.setCaret(from, to);
  input().focus();
  input().dispatchEvent(new MouseEvent('contextmenu',
    {bubbles: true, cancelable: true, clientX: 0, clientY: 0}));
};
const choose = kind => {
  POP.querySelector('.popitem[data-kind="from-selection"]').click();
  document.querySelector(`#popsub .popitem[data-kind="from-selection-${kind}"]`).click();
};
const save = () => POP.querySelector('[data-kind="form-save"]').click();
const said = () => document.getElementById('state').textContent;
const titleBox = () => POP.querySelector('[data-field="title"] input, input[data-field="title"]');
if (!document.querySelector('article.record').classList.contains('editing')) flipEditing();
await rest(100);
"""


def _at_the_record(
    client: TestClient, tmp_path: Path, script: str, editor: str = "plain", name: str = "page"
) -> dict:
    page = client.get(f"/detail/{PITCH}?editor={editor}").text
    stubbed = page.replace('<link rel="icon"', f"<script>{_STUBS}</script><link rel=\"icon\"", 1)
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
  menuOn(at, at + words.length);
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
menuOn(at, at + words.length);
choose('task');
await rest(50);
popOpenField('parent');
const picker = POP.querySelector('select[data-field="parent"]');
picker.value = '';
picker.dispatchEvent(new Event('change', {bubbles: true}));
const base = document.getElementById('base').value;
save();
await rest(700);
return {opened, cancelled, posts: window.__posts, base, now: document.getElementById('base').value,
        text: SURFACE.text(), said: said(), open: popIsOpen(),
        focus: SURFACE.el.contains(document.activeElement), errors: window.__errors};
"""


def test_a_kind_opens_the_form_titled_from_the_selection_and_filed_where_it_may_be(
    client: TestClient, tmp_path: Path
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
    assert sent["base_commit"] == got["base"] and got["now"] == "c0ffee1", (
        "the create did not advance the page's base, so the page's next save "
        "would collide with the commit it just made"
    )
    assert got["text"] == "Write [**Port** the   transport](task-000123) now.\n", got["text"]
    assert got["said"] == "Created task-000123 and linked it."
    assert got["open"] is False
    assert got["focus"], "the keyboard did not come back to the editor"


# One person selects words and makes a record of them while somebody else in the
# room types. The welcome is taken before the other person's edit, so the edit
# arrives as a frame while the form is open; what the page sends afterwards is
# applied to the same real `Room`, so the claim is about the document everybody
# holds and not about one tab's box.
_IN_A_ROOM = """
window.__room.onmessage({data: WELCOME});
await rest(150);
const text = SURFACE.text();
const at = text.indexOf(WORDS);
menuOn(at, at + WORDS.length);
choose('task');
await rest(50);
const title = titleBox() && titleBox().value;
window.__room.onmessage({data: JSON.stringify({t: 'update', u: REMOTE})});
await rest(150);
const between = SURFACE.text();
save();
await rest(800);
return {title, between, text: SURFACE.text(), said: said(), posts: window.__posts.length,
        focus: SURFACE.el.contains(document.activeElement), sent: window.__sent,
        errors: window.__errors};
"""

WORDS = "blend-weight coefficients"


def _a_room_and_somebody_else(client: TestClient, theirs) -> tuple:
    shown = client.get("/api/index.json").json()["plan"][PITCH]["body"]
    assert WORDS in shown, "the pitch's body does not hold the words this test selects"
    path = f"pitches/{PITCH}.md"
    room = coedit.Room(PITCH, path, "0" * 40, shown)
    welcome = {
        "t": "welcome",
        "seed": room.seed,
        "base": room.base,
        "you": "ann",
        "sv": base64.b64encode(room.state()).decode(),
        "update": base64.b64encode(room.since(None)).decode(),
    }
    bob = coedit.Room(PITCH, path, "0" * 40, shown)
    update = bob.absorb(theirs(shown))
    assert update, "the other copy produced no update"
    room.apply(update, "bob")
    return room, welcome, base64.b64encode(update).decode(), bob.body()


def _in_the_room(client, tmp_path, editor, room, welcome, remote, name) -> dict:
    script = (
        f"const WELCOME = {json.dumps(json.dumps(welcome))};\n"
        f"const REMOTE = {json.dumps(remote)};\n"
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
    client: TestClient, tmp_path: Path, editor: str
):
    """Somebody types an emoji at the top of the document while the form is open,
    and the link still wraps exactly the words that were selected.

    The range is followed through the room's splice — two anchors on Ace, the
    seat bands' arithmetic on the textarea — and an emoji is two UTF-16 code
    units, so a range carried by one character instead of by its length would
    wrap the words one unit off: `[lend-weight coefficients ](…)`-shaped, and
    split nothing visibly in the box until the room committed it.
    """
    room, welcome, remote, theirs = _a_room_and_somebody_else(client, lambda shown: "👍 " + shown)
    got = _in_the_room(client, tmp_path, editor, room, welcome, remote, "before")
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
def test_the_selected_words_changed_meanwhile_so_the_record_is_made_and_not_linked(
    client: TestClient, tmp_path: Path, editor: str
):
    """Somebody in the room edits the selected words while the form is open: the
    record is still made, nothing is written into the document, and the page
    says so with the id, so it can be linked by hand.

    A link written around somebody else's half-edited sentence would be worse
    than no link at all, and a create held back would throw away the form.
    """
    room, welcome, remote, theirs = _a_room_and_somebody_else(
        client, lambda shown: shown.replace("blend-weight", "blending-weight")
    )
    got = _in_the_room(client, tmp_path, editor, room, welcome, remote, "changed")
    assert got["posts"] == 1, "the record was not made"
    assert got["text"] == theirs, f"{editor}: something was written: {got['text']!r}"
    assert got["said"] == (
        "Created task-000123. The text you selected changed, so it wasn't linked."
    )
    assert room.body() == theirs
