"""The priority picker: a button and the page's own list, in place of every select.

jcanton, 2026-11-24, after Firefox drew the select's open list without the meter:
the app's own popup list, which draws `priority_bars` in every browser. One
markup (`priority_picker`) and one controller (the shell's), shared by the record
page, the cycle page, the table's cell editor and the edit card. Asked of real
Chrome, because the controller lives in a `MutationObserver`, a `<template>` and
focus, three things the node shim does not have.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest
from pages import elements

from openproj.index import Index, build_index
from openproj.model import load_repo
from openproj.render import (
    PRIORITIES,
    ROUTES,
    render_cycle,
    render_detail,
    render_graph,
    render_table,
)
from openproj.render.tokens import priority_picker


@pytest.fixture
def index(seed_root: Path) -> Index:
    records, config, unreadable = load_repo(seed_root)
    return build_index(records, config, date(2026, 8, 17), unreadable)


def _task(index: Index) -> str:
    return next(one.id for one in index.records.values() if one.kind == "task" and one.priority)


def test_the_picker_carries_what_the_select_did():
    """The name, the value and the type the save paths read, the attributes a page
    gave its select, and the combobox's own state."""
    (button,) = [
        one
        for one in elements(
            priority_picker(
                "high",
                label="A priority",
                id="p",
                extra={"aria-describedby": "why", "data-required-at": "ready"},
            )
        )
        if one.tag == "button"
    ]
    attrs = button.attrs
    assert (attrs["name"], attrs["value"], attrs["data-type"]) == ("priority", "high", "text")
    assert attrs["role"] == "combobox" and attrs["aria-haspopup"] == "listbox"
    assert attrs["aria-expanded"] == "false" and attrs["aria-controls"] == "pripop"
    assert attrs["aria-label"] == "A priority" and attrs["id"] == "p"
    assert attrs["aria-describedby"] == "why" and attrs["data-required-at"] == "ready"


def test_no_server_page_offers_a_priority_as_a_select(index: Index):
    """Every page a server renders that picks a priority, parsed: no `<select>` named
    or keyed `priority` is left, and the picker is there instead."""
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
            and "priority" in (one.attrs.get("name", ""), one.attrs.get("data-field", ""))
        ]
        assert not selects, f"the {name} page still offers a priority as a select"
        if name in ("record", "create", "cycle"):
            assert any("pripick" in one.attrs.get("class", "") for one in found), name
    # And the one list, once, with a row per rung carrying the meter.
    (listbox,) = re.findall(r'<ul id="pripop".*?</ul>', pages["table"], re.S)
    rows = re.findall(r'<li id="pripop-(\w+)"', listbox)
    assert rows == list(PRIORITIES)
    assert listbox.count('class="pribars"') == len(PRIORITIES)


# Keys sent the way the controller hears them, from the button, and the list read
# back after each: where the keyboard is, whether it is open, what is held.
_KEYS = """
const key = (target, name) => target.dispatchEvent(new KeyboardEvent('keydown',
  {key: name, bubbles: true, cancelable: true}));
const list = document.getElementById('pripop');
const look = b => ({open: !list.hidden, expanded: b.getAttribute('aria-expanded'),
  at: (list.querySelector('.on') || {}).dataset?.value || null, value: b.value,
  active: b.getAttribute('aria-activedescendant'), focused: document.activeElement === b});
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


def test_the_table_editor_picks_by_keyboard_and_commits_on_enter(index: Index, tmp_path: Path):
    """The cell editor's blur-to-commit is the thing a select-shaped popup broke
    last time: the list took the focus and the cell closed under the pointer. The
    focus stays on the button now, so nothing commits while somebody picks, and
    Enter on the closed button commits as it did on the select."""
    from browser import chrome, measured_in

    script = (
        _FETCHES
        + _KEYS
        + """
const cell = document.querySelector('td.edit[data-field="priority"]');
const record = cell.dataset.record;
cell.dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
const b = cell.querySelector('.pripick');
const steps = {opened: look(b)};
key(b, 'ArrowDown'); steps.open = look(b);
key(b, 'ArrowDown'); key(b, 'End'); steps.end = look(b);
key(b, 'Home'); steps.home = look(b);
key(b, 'm'); steps.typed = look(b);
key(b, 'Escape'); steps.escaped = look(b);
steps.editorAfterEscape = !!cell.querySelector('.pripick');
key(b, 'ArrowDown'); key(b, 'ArrowDown'); key(b, 'Enter'); steps.picked = look(b);
steps.editorAfterPick = !!cell.querySelector('.pripick');
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
    assert got["opened"]["focused"] and not got["opened"]["open"], got["opened"]
    assert got["open"]["open"] and got["open"]["at"] == was, "ArrowDown opens on the value held"
    assert got["open"]["active"] == f"pripop-{was}", got["open"]
    assert got["end"]["at"] == PRIORITIES[-1] and got["home"]["at"] == PRIORITIES[0]
    assert got["typed"]["at"] == "medium", "type-ahead by first letter"
    assert not got["escaped"]["open"] and got["escaped"]["value"] == was
    assert got["escaped"]["focused"] and got["editorAfterEscape"], (
        "Escape in the list closed the cell as well"
    )
    picked = got["picked"]["value"]
    assert picked != was and not got["picked"]["open"] and got["editorAfterPick"]
    assert got["sentBeforeCommit"] == 0, "a pick committed before the cell was left"
    (patch,) = got["sent"]
    assert patch["method"] == "PATCH" and got["record"] in patch["url"], patch
    assert '"priority": "' + picked + '"' in patch["body"].replace('":"', '": "'), patch


def test_the_record_page_saves_the_rung_that_was_picked(index: Index, tmp_path: Path):
    """The record page reads every `[data-type]` control by name and value, so the
    button is read where the select was, and a pick is a change Save sends."""
    from browser import chrome, measured_in

    script = (
        _FETCHES
        + _KEYS
        + """
showEditing(true);
const b = document.querySelector('.pripick.field');
b.focus();
const before = look(b);
b.click();
const opened = look(b);
document.querySelector('#pripop [data-value="very_low"]').click();
const picked = look(b);
document.getElementById('save').click();
await new Promise(done => setTimeout(done, 300));
return {before, opened, picked, label: document.querySelector('label[for="' + b.id + '"]')
  ? document.querySelector('label[for="' + b.id + '"]').textContent.trim() : null,
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


# The list's box against the window, opened on a phone-width page.
_ON_A_PHONE = """
const cell = document.querySelector('td.edit[data-field="priority"]');
cell.scrollIntoView({block: 'center', inline: 'end'});
cell.dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
const b = cell.querySelector('.pripick');
b.click();
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


def test_the_cycle_page_sorts_priority_by_rung(index: Index, tmp_path: Path):
    """The betting table sorted a ladder by the select's `selectedIndex`. A button
    has none, and its text holds every rung's word to keep its width, so the
    rung is read from where its value sits in the page's list."""
    from browser import chrome, measured_in

    script = """
const th = [...BETS.querySelectorAll('th[data-sort]')].find(t => /priority/i.test(t.textContent));
betSort(Number(th.dataset.sort), false);
return betRows().map(row => row.querySelector('.pripick'))
  .filter(Boolean).map(button => button.value);
"""
    page = render_cycle(index, 37, ROUTES, base_commit="deadbee")
    got = measured_in(chrome(), page, tmp_path / "sort.html", 1300, script)
    assert len(set(got)) > 1, f"one rung only, so the order proves nothing: {got}"
    ranks = [PRIORITIES.index(value) for value in got]
    assert ranks == sorted(ranks), got
