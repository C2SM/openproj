"""The rung picker: a button and the page's own list, in place of every select that
picked a priority or a status.

jcanton, 2026-11-24, after Firefox drew the select's open list without the meter:
the app's own popup list, which draws the meter and the status glyph in every
browser. One markup (`rung_picker`) and one controller (the shell's), for both
fields, shared by the record page, the cycle page, the table's cell editor and
the edit card. And then: one visual object, so the read chip, the closed button
and the list's rows are one width and one height, and entering edit moves
nothing. Asked of real Chrome, because the controller lives in a
`MutationObserver`, a `<template>` and focus, three things the node shim does not
have, and because a width is a pixel.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest
from pages import elements

from openproj.index import Index, build_index
from openproj.model import ISSUE_STATUS, load_repo
from openproj.render import (
    PRIORITIES,
    ROUTES,
    STATUSES,
    render_cycle,
    render_detail,
    render_graph,
    render_table,
)
from openproj.render.tokens import RUNG_VOCAB, RUNG_WIDTH, _human, rung_picker


@pytest.fixture
def index(seed_root: Path) -> Index:
    records, config, unreadable = load_repo(seed_root)
    return build_index(records, config, date(2026, 8, 17), unreadable)


def _task(index: Index) -> str:
    return next(one.id for one in index.records.values() if one.kind == "task" and one.priority)


def test_the_picker_carries_what_the_select_did():
    """The name, the value and the type the save paths read, the attributes a page
    gave its select, what the record's kind accepts, and the combobox's state."""
    (button,) = [
        one
        for one in elements(
            rung_picker(
                "status",
                "ready",
                offers=ISSUE_STATUS,
                label="A status",
                id="s",
                extra={"aria-describedby": "why", "data-required-at": "ready"},
            )
        )
        if one.tag == "button"
    ]
    attrs = button.attrs
    assert (attrs["name"], attrs["value"], attrs["data-type"]) == ("status", "ready", "text")
    assert attrs["role"] == "combobox" and attrs["aria-haspopup"] == "listbox"
    assert attrs["aria-expanded"] == "false" and attrs["aria-controls"] == "stpop"
    assert attrs["aria-label"] == "A status" and attrs["id"] == "s"
    assert attrs["aria-describedby"] == "why" and attrs["data-required-at"] == "ready"
    assert attrs["data-offers"].split() == list(ISSUE_STATUS)


def test_the_widths_are_derived_from_the_words():
    """A renamed rung resizes its chips: the width is the longest label as drawn,
    never a number written down."""
    for field, words in RUNG_VOCAB.items():
        assert RUNG_WIDTH[field] == max(len(_human(word)) for word in words), field


def test_no_server_page_offers_a_priority_or_a_status_as_a_select(index: Index):
    """Every page a server renders that picks one, parsed: no `<select>` named or
    keyed `priority` or `status` is left, and the picker is there instead."""
    task = _task(index)
    pages = {
        "record": render_detail(index, ROUTES, only=task, base_commit="deadbee", may_write=True),
        "create": render_detail(
            index, ROUTES, base_commit="deadbee", may_write=True, creating="task"
        ),
        "cycle": render_cycle(index, 37, ROUTES, base_commit="deadbee"),
        "table": render_table(index, ROUTES, base_commit="deadbee", may_write=True),
        "graph": render_graph(index, ROUTES, base_commit="deadbee", may_write=True),
    }
    for name, page in pages.items():
        found = elements(page)
        selects = [
            one
            for one in found
            if one.tag == "select"
            and {one.attrs.get("name", ""), one.attrs.get("data-field", "")}
            & {"priority", "status"}
        ]
        assert not selects, f"the {name} page still offers a rung as a select"
        if name in ("record", "create", "cycle"):
            assert any("rungpick" in one.attrs.get("class", "") for one in found), name
    # And one list per field, once, with a row per word carrying the mark.
    for field, list_id in (("priority", "pripop"), ("status", "stpop")):
        (listbox,) = re.findall(rf'<ul id="{list_id}".*?</ul>', pages["table"], re.S)
        assert re.findall(rf'<li id="{list_id}-(\w+)"', listbox) == list(RUNG_VOCAB[field])
        assert listbox.count('class="chipmark"') >= len(PRIORITIES), field


# Keys sent the way the controller hears them, from the button, and the list read
# back after each: where the keyboard is, whether it is open, what is held.
_KEYS = """
const key = (target, name) => target.dispatchEvent(new KeyboardEvent('keydown',
  {key: name, bubbles: true, cancelable: true}));
const look = b => { const list = document.getElementById(b.getAttribute('aria-controls'));
  return {open: !list.hidden, expanded: b.getAttribute('aria-expanded'),
  at: (list.querySelector('.on') || {}).dataset?.value || null, value: b.value,
  active: b.getAttribute('aria-activedescendant'), focused: document.activeElement === b}; };
"""

# The fetches a page makes, recorded, answered with a refusal the page can read.
_FETCHES = """
window.__sent = [];
window.fetch = async (url, init) => {
  window.__sent.push({url: String(url), method: (init && init.method) || 'GET',
                      body: init && init.body ? String(init.body) : null});
  return new Response(JSON.stringify({detail: 'stubbed'}),
                      {status: 409, headers: {'content-type': 'application/json'}});
};
"""


@pytest.mark.parametrize("field", ["priority", "status"])
def test_the_table_editor_picks_by_keyboard_and_commits_on_enter(
    index: Index, tmp_path: Path, field: str
):
    """The cell editor's blur-to-commit is the thing a select-shaped popup broke
    once: the list took the focus and the cell closed under the pointer. The focus
    stays on the button now, so nothing commits while somebody picks, and Enter on
    the closed button commits as it did on the select."""
    from browser import chrome, measured_in

    script = (
        _FETCHES
        + _KEYS
        + f"const FIELD = '{field}';"
        + """
const cell = document.querySelector(`td.edit[data-field="${FIELD}"]`);
const record = cell.dataset.record;
cell.dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
const b = cell.querySelector('.rungpick');
const steps = {opened: look(b)};
key(b, 'ArrowDown'); steps.open = look(b);
key(b, 'End'); steps.end = look(b);
key(b, 'Home'); steps.home = look(b);
key(b, 'Escape'); steps.escaped = look(b);
steps.editorAfterEscape = !!cell.querySelector('.rungpick');
// Down a priority, and UP a status: a status moved forward is gated, and the
// table asks for what the new status demands instead of saving, which is the page
// working and not this test's question.
key(b, 'ArrowDown'); key(b, FIELD === 'status' ? 'ArrowUp' : 'ArrowDown'); key(b, 'Enter');
steps.picked = look(b);
steps.editorAfterPick = !!cell.querySelector('.rungpick');
steps.sentBeforeCommit = window.__sent.filter(one => one.method !== 'GET').length;
key(b, 'Enter');
await new Promise(done => setTimeout(done, 300));
steps.sent = window.__sent.filter(one => one.method !== 'GET');
steps.record = record;
return steps;
"""
    )
    page = render_table(index, ROUTES, base_commit="deadbee", may_write=True)
    got = measured_in(chrome(), page, tmp_path / "table.html", 1400, script, patience=3000)

    was = got["opened"]["value"]
    # What the table's column offers, which for a status is the six a planned
    # record reads and not the note's `dropped` the list also holds.
    offered = PRIORITIES if field == "priority" else STATUSES
    assert got["opened"]["focused"] and not got["opened"]["open"], got["opened"]
    assert got["open"]["open"] and got["open"]["at"] == was, "ArrowDown opens on the value held"
    assert (got["home"]["at"], got["end"]["at"]) == (offered[0], offered[-1]), got
    assert not got["escaped"]["open"] and got["escaped"]["value"] == was
    assert got["escaped"]["focused"] and got["editorAfterEscape"], (
        "Escape in the list closed the cell as well"
    )
    picked = got["picked"]["value"]
    assert picked != was and not got["picked"]["open"] and got["editorAfterPick"]
    assert got["sentBeforeCommit"] == 0, "a pick committed before the cell was left"
    (patch,) = got["sent"]
    assert patch["method"] == "PATCH" and got["record"] in patch["url"], patch
    assert f'"{field}":"{picked}"' in patch["body"].replace(" ", ""), patch


def test_the_record_page_saves_the_rung_that_was_picked(index: Index, tmp_path: Path):
    """The record page reads every `[data-type]` control by name and value, so the
    button is read where the select was, and a pick is a change Save sends."""
    from browser import chrome, measured_in

    script = (
        _FETCHES
        + _KEYS
        + """
showEditing(true);
const b = document.querySelector('.rungpick.field');
b.focus();
const before = look(b);
b.click();
const opened = look(b);
document.querySelector('#pripop [data-value="very_low"]').click();
const picked = look(b);
document.getElementById('save').click();
await new Promise(done => setTimeout(done, 300));
const label = document.querySelector('label[for="' + b.id + '"]');
return {before, opened, picked, label: label ? label.textContent.trim() : null,
  sent: window.__sent.filter(one => one.method === 'PATCH')};
"""
    )
    page = render_detail(index, ROUTES, only=_task(index), base_commit="deadbee", may_write=True)
    got = measured_in(chrome(), page, tmp_path / "record.html", 1300, script, patience=3000)

    assert got["label"], "the picker lost the field's label"
    assert got["opened"]["open"] and got["opened"]["at"] == got["before"]["value"]
    assert got["picked"]["value"] == "very_low" and not got["picked"]["open"]
    (patch,) = got["sent"]
    assert '"priority":"very_low"' in patch["body"].replace(" ", ""), patch


# Every chip of each field in the table's columns, the picker's face and its open
# rows, measured; and the row and the cell, before and after the cell goes into
# edit. Rounded to a tenth, which is below what a browser lays out.
_ONE_OBJECT = """
const box = el => { const r = el.getBoundingClientRect();
  return [Math.round(r.width * 10) / 10, Math.round(r.height * 10) / 10]; };
const out = {};
for (const field of ['priority', 'status']) {
  const column = [...document.querySelectorAll(`td[data-col="${field}"] > .chip`)].map(box);
  const cell = document.querySelector(`td.edit[data-field="${field}"]`);
  const row = cell.parentNode;
  const read = {row: box(row), cell: box(cell), chip: box(cell.querySelector('.chip'))};
  cell.dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
  const b = cell.querySelector('.rungpick');
  const edit = {row: box(row), cell: box(cell), chip: box(b.querySelector('.chip'))};
  b.focus(); b.click();
  const list = document.getElementById(b.getAttribute('aria-controls'));
  const rows = [...list.querySelectorAll('[role="option"]:not([hidden]) .chip')];
  const lefts = [b.querySelector('.chip'), ...rows].map(one =>
    Math.round(one.getBoundingClientRect().left * 10) / 10);
  out[field] = {column, read, edit, rows: rows.map(box), lefts};
  b.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
  draw();
}
return out;
"""


def test_a_vocabulary_is_one_width_and_entering_edit_moves_nothing(
    index: Index, tmp_path: Path
):
    """jcanton, 2026-11-24: the read chip, the closed button and the list were three
    sizes, the row grew when its cell went into edit, and a column of chips of
    different widths read as a ragged edge. So every chip of a field is one width,
    in the column, on the button and in the list, the rows stand under the
    button's chip, and the row and the cell are the same height in edit."""
    from browser import chrome, measured_in

    page = render_table(index, ROUTES, base_commit="deadbee", may_write=True)
    got = measured_in(chrome(), page, tmp_path / "one.html", 1400, _ONE_OBJECT, patience=3000)

    for field, seen in got.items():
        widths = {w for w, _ in seen["column"]} | {w for w, _ in seen["rows"]}
        widths |= {seen["read"]["chip"][0], seen["edit"]["chip"][0]}
        assert len(seen["column"]) > 1, f"one {field} chip in the column proves nothing"
        assert max(widths) - min(widths) <= 0.2, f"{field} chips are {sorted(widths)} wide"
        assert seen["edit"]["row"] == seen["read"]["row"], f"the {field} row moved: {seen}"
        assert seen["edit"]["cell"] == seen["read"]["cell"], f"the {field} cell moved: {seen}"
        assert seen["edit"]["chip"] == seen["read"]["chip"], f"the {field} chip moved: {seen}"
        assert max(seen["lefts"]) - min(seen["lefts"]) <= 0.2, (
            f"the {field} list's chips do not stand under the button's: {seen['lefts']}"
        )


# The pointer over the third row: the row Enter would pick moves with it.
_HOVER = """
const cell = document.querySelector('td.edit[data-field="status"]');
cell.dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
const b = cell.querySelector('.rungpick');
b.focus(); b.click();
// A row other than the one held, or a pick of it would prove nothing.
const target = [...document.querySelectorAll('#stpop [role="option"]:not([hidden])')]
  .find(row => row.dataset.value !== b.value);
const was = b.value;
target.dispatchEvent(new MouseEvent('mousemove', {bubbles: true}));
const hovered = {on: (document.querySelector('#stpop .on') || {}).dataset?.value, was,
                 active: b.getAttribute('aria-activedescendant'), row: target.dataset.value};
b.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));
return {...hovered, value: b.value};
"""


def test_the_pointer_moves_the_row_enter_would_pick(index: Index, tmp_path: Path):
    from browser import chrome, measured_in

    page = render_table(index, ROUTES, base_commit="deadbee", may_write=True)
    got = measured_in(chrome(), page, tmp_path / "hover.html", 1400, _HOVER)
    assert got["row"] != got["was"], got
    assert got["on"] == got["row"] and got["active"] == f"stpop-{got['row']}", got
    assert got["value"] == got["row"], "Enter picked a row other than the one under the pointer"


# A status picker for an issue, built the way the edit card builds one.
_AN_ISSUE = """
const b = rungPicker('status', 'ready', 'Status', %s);
document.body.append(b);
b.focus(); b.click();
return [...document.querySelectorAll('#stpop [role="option"]')]
  .filter(row => !row.hidden).map(row => row.dataset.value);
"""


def test_a_kind_is_offered_only_the_statuses_it_reads(index: Index, tmp_path: Path):
    """An issue has four statuses where a task has six, and the select offered an
    issue its four; the list narrows to what the button says its kind accepts."""
    import json

    from browser import chrome, measured_in

    page = render_table(index, ROUTES, base_commit="deadbee", may_write=True)
    script = _AN_ISSUE % json.dumps(list(ISSUE_STATUS))
    got = measured_in(chrome(), page, tmp_path / "issue.html", 1400, script)
    assert got == list(ISSUE_STATUS), got


# The hover card asked to show while a picker's list is open, as a pointer
# crossing a title would ask it.
_NO_CARD = """
const row = Object.values(DATA.rows).find(r => r.kind === 'task');
await showCard(row, 300, 300);
const before = !CARD.hidden;
const cell = document.querySelector('td.edit[data-field="priority"]');
cell.dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
const b = cell.querySelector('.rungpick'); b.focus(); b.click();
const shut = CARD.hidden;
await showCard(row, 300, 300);
const z = id => Number(getComputedStyle(document.getElementById(id)).zIndex);
return {before, shut, stillShut: CARD.hidden, list: z('pripop'), card: z('card'), pop: z('pop')};
"""


def test_an_open_list_keeps_the_hover_card_away(index: Index, tmp_path: Path):
    """jcanton, 2026-11-24: the title's hover card opened over the list being picked
    from. Opening a list shuts the card, the card will not open over it, and the
    list is above both the card and the right-click menu."""
    from browser import chrome, measured_in

    page = render_table(index, ROUTES, base_commit="deadbee", may_write=True)
    got = measured_in(chrome(), page, tmp_path / "card.html", 1400, _NO_CARD)
    assert got["before"], "the card never showed, so this proves nothing"
    assert got["shut"] and got["stillShut"], got
    assert got["list"] > got["pop"] > got["card"], got


# The list's box against the window, opened on a phone-width page.
_ON_A_PHONE = """
const cell = document.querySelector('td.edit[data-field="priority"]');
cell.scrollIntoView({block: 'center', inline: 'end'});
cell.dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
const b = cell.querySelector('.rungpick');
b.focus(); b.click();
const r = document.getElementById('pripop').getBoundingClientRect();
return {left: r.left, right: r.right, top: r.top, bottom: r.bottom,
        width: innerWidth, height: innerHeight};
"""


def test_the_list_stays_inside_a_phone(index: Index, tmp_path: Path):
    """Through the viewport override and not `measured_in`, whose window has a
    500px floor: a phone claim asked of a 500px window is no phone claim."""
    from browser import chrome, measured_on_a_phone

    page = render_table(index, ROUTES, base_commit="deadbee", may_write=True)
    found = measured_on_a_phone(chrome(), {"table": page}, tmp_path / "phone", _ON_A_PHONE)
    got = found["table"]
    assert got["width"] == 390, f"this is not a phone: {got}"
    assert got["left"] >= 0 and got["right"] <= got["width"], got
    assert got["top"] >= 0 and got["bottom"] <= got["height"], got


def test_the_cycle_page_sorts_a_rung_by_its_ladder(index: Index, tmp_path: Path):
    """The betting table sorted a ladder by the select's `selectedIndex`. A button
    has none, so the rung is read from where its value sits in the field's list."""
    from browser import chrome, measured_in

    script = """
const out = {};
for (const field of ['priority', 'status']) {
  const th = [...BETS.querySelectorAll('th[data-sort]')]
    .find(t => t.textContent.toLowerCase().includes(field));
  betSort(Number(th.dataset.sort), false);
  out[field] = betRows().map(row => row.querySelector(`.rungpick[data-field="${field}"]`))
    .filter(Boolean).map(button => button.value);
}
return out;
"""
    page = render_cycle(index, 37, ROUTES, base_commit="deadbee")
    got = measured_in(chrome(), page, tmp_path / "sort.html", 1300, script)
    for field, values in got.items():
        assert len(set(values)) > 1, f"one {field} only, so the order proves nothing: {values}"
        ranks = [RUNG_VOCAB[field].index(value) for value in values]
        assert ranks == sorted(ranks), (field, values)
