"""Markdown tables in a body: aligned on an explicit save, edited from the Table button.

`design/body-tables-links-selection.md` §1 is the decision. The formatter is the
page's own JavaScript (`render/tables.py`), so every claim about what it writes
is asked of node running the bytes the record page ships — and every claim
about what a table IS is asked of `_MD`, the renderer whose output is
committed, because a formatter that disagreed with it would pad columns the
rendered table does not have, or realign a paragraph that merely contains
pipes.
"""

from __future__ import annotations

import base64
import json
import random
from pathlib import Path

import pygit2
import pytest
from browser import chrome, measured_in
from fastapi.testclient import TestClient
from test_coedit import _welcome, in_chrome_room, shown_body, stored
from test_injection import run_js
from test_store import commit_directly
from test_web import PATH, SECRET, SEED, TASK

from openproj import coedit
from openproj.model import split_front_matter
from openproj.render.markdown import _MD
from openproj.web import create_app


@pytest.fixture(scope="module")
def page(tmp_path_factory: pytest.TempPathFactory) -> str:
    """The record page a writer gets, rendered once: every question in the first
    half of this file is about a pure function on it, so nothing is typed into
    the page and one copy serves them all."""
    repo = tmp_path_factory.mktemp("tables") / "plan.git"
    pygit2.init_repository(str(repo), bare=True, initial_head="main")
    commit_directly(repo, SEED, "seed the corpus")
    with TestClient(create_app(repo, auth="dev", secret=SECRET)) as served:
        return served.get(f"/detail/{TASK}?editor=plain").text


@pytest.fixture
def plan(tmp_path: Path) -> Path:
    repo = tmp_path / "plan.git"
    pygit2.init_repository(str(repo), bare=True, initial_head="main")
    commit_directly(repo, SEED, "seed the corpus")
    return repo


@pytest.fixture
def client(plan: Path):
    with TestClient(create_app(plan, auth="dev", secret=SECRET)) as served:
        yield served


def shipped(page: str, expression: str) -> object:
    """What the page's own script answers. `expression` sees every global the
    page declared, `alignTables` and `tableEdit` among them."""
    answer = run_js(page, expression)
    assert answer["value"] is not None, f"the page answered nothing: {answer['errors']}"
    return answer["value"]


def aligned(page: str, text: str) -> str:
    return shipped(page, f"alignTables({json.dumps(text)})")


# --------------------------------------------------------------------------- #
# What aligned means
# --------------------------------------------------------------------------- #


def test_a_ragged_table_is_aligned_and_nothing_else_moves(page: str):
    """Every rule of "aligned" in one table, with prose and a fence around it that
    must come back byte for byte — the fence holds a table of its own, which is
    code and not a table."""
    fence = "```\n|x|y|\n|-|-|\n|1|2|\n```"
    text = f"Prose  with  pipes | in it.\n\n|a|b|\n|-|-|\n|long cell|x|\n|y|\n\n{fence}\n"
    assert aligned(page, text) == (
        "Prose  with  pipes | in it.\n\n"
        "| a         | b   |\n"
        "| --------- | --- |\n"
        "| long cell | x   |\n"
        "| y         |     |\n"
        f"\n{fence}\n"
    )


def test_alignment_follows_the_delimiter_row(page: str):
    """`:--` left, `:-:` centre, `--:` right, `---` left; the dashes fill the
    column and keep their colons."""
    text = "| l | c | r | n |\n|:--|:-:|--:|---|\n| left | centre | right | none |\n"
    assert aligned(page, text) == (
        "| l    |   c    |     r | n    |\n"
        "| :--- | :----: | ----: | ---- |\n"
        "| left | centre | right | none |\n"
    )


def test_width_is_counted_in_graphemes(page: str):
    """`👍🏽` is two code points, four UTF-16 units and two columns; `表格` is two
    characters and four columns; `é` written as `e` and a combining accent is two
    code points and one column. Counted in any other unit, the pipes after these
    cells stop lining up in every monospaced editor the file is read in."""
    text = "| a | b | c |\n|---|---|---|\n| 👍🏽 done | 表格 | é |\n| x | y | z |\n"
    assert aligned(page, text) == (
        "| a       | b    | c   |\n"
        "| ------- | ---- | --- |\n"
        "| 👍🏽 done | 表格 | é   |\n"
        "| x       | y    | z   |\n"
    )
    widths = shipped(
        page,
        "['👍🏽 done', '表格', 'e\\u0301', '❤️', '🇨🇭', '☺', 'ｱ', '\\u200b'].map(tableWidth)",
    )
    # A text-presentation `☺` is one column and the same symbol asked for as an
    # emoji is two; a half-width katakana is one; a zero-width space is none.
    assert widths == [7, 4, 1, 2, 2, 1, 1, 0]


def test_a_pipe_splits_where_markdown_it_splits(page: str):
    """GFM's rule and markdown-it-py's `escapedSplit`: every `|` not after a
    backslash splits, a pipe inside backticks included. The reader's intuition
    that `` `a|b` `` is one cell is not what the page draws, and the formatter
    follows the page."""
    spanned = "| `a|b` | c |\n|---|---|---|\n"
    assert aligned(page, spanned) == "| `a  | b`  | c   |\n| --- | --- | --- |\n"
    escaped = "| a\\|b | c |\n|---|---|\n"
    assert aligned(page, escaped) == "| a\\|b | c   |\n| ---- | --- |\n"


def test_a_short_row_is_padded_and_a_long_row_keeps_its_cells(page: str):
    """The renderer draws a short row's missing cells empty and drops a long
    row's extras. The formatter writes the first and never the second: it does
    not drop text, and what is past the header is the writer's to see."""
    text = "| a | b | c |\n|---|---|---|\n| 1 |\n| 1 | 2 | 3 | four |\n"
    assert aligned(page, text) == (
        "| a   | b   | c   |\n"
        "| --- | --- | --- |\n"
        "| 1   |     |     |\n"
        "| 1   | 2   | 3   | four |\n"
    )


def test_a_body_with_nothing_to_align_gets_no_edit_at_all(page: str):
    """The same string, `===`, and not merely equal: a save with nothing to align
    must not be an edit, and the save path asks exactly this."""
    already = "| a   | b   |\n| --- | --- |\n| c   | d   |\n"
    for text in ["", "Just prose.\n", already, "```\n|a|b|\n|-|-|\n```\n", "> |a|b|\n> |-|-|\n"]:
        assert shipped(
            page, f"(() => {{ const t = {json.dumps(text)}; return alignTables(t) === t; }})()"
        ), text
        assert shipped(page, f"alignedRuns({json.dumps(text)}).length") == 0, text


# --------------------------------------------------------------------------- #
# The formatter and the renderer read the same tables
# --------------------------------------------------------------------------- #

# The minimum the spec asks for — a table in a fence, in a blockquote, in a list
# item, beside an HTML block, with `\|`, with a pipe in a code span, with an
# emoji splitting a column, and a line of pipes that is not a table — and the
# shapes that took a second look at markdown-it's block rules to get right.
CORPUS = {
    "ragged": "Prose.\n\n|a|b|\n|-|:-:|\n|long cell|x|\n\nAfter.\n",
    "fenced": "```\n| a | b |\n|---|---|\n| c | d |\n```\n",
    "unclosed fence": "~~~\n| a | b |\n|---|---|\n",
    "blockquote": "> | a | b |\n> |---|---|\n> | c | d |\n",
    "lazy under a quote": "> quote\n| a | b |\n|---|---|\n",
    "list item": "- item\n\n  | a | b |\n  |---|---|\n  | c | d |\n",
    "lazy under an item": "- item\n| a | b |\n|---|---|\n",
    "after a list": "- item\n\n| a | b |\n|---|---|\n",
    "beside an HTML block": "<div>\n| a | b |\n|---|---|\n</div>\n",
    "inside an HTML block": "<div>\n\n| a | b |\n|---|---|\n\n</div>\n",
    "escaped pipe": "| a \\| b | c |\n|---|---|\n| d | e \\| f |\n",
    "pipe in a code span": "| `a|b` | c |\n|---|---|---|\n| d | e | f |\n",
    "emoji": "| 👍🏽 done | 表格 |\n|---|---|\n| é | x |\n",
    "pipes that are not a table": "a | b | c\nmore | pipes\n",
    "only pipes": "|||\n|||\n",
    "interrupting a paragraph": "Some text\n| a | b |\n|---|---|\n| c | d |\nnext line\n",
    "a setext heading": "| a | b |\n---\n",
    "short and long rows": "| a | b | c |\n|---|---|---|\n| 1 |\n| 1 | 2 | 3 | 4 |\n",
    "indented code": "    | a | b |\n    |---|---|\n",
    "maths": "$$\n| a | b |\n|---|---|\n$$\n",
    "two tables": "| a |\n|---|\n\ntext\n\n| b | c |\n|:--|--:|\n| x | y |\n",
    "ended by an item": "| a | b |\n|---|---|\n| c | d |\n- item\n",
    "ended by a heading": "| a | b |\n|---|---|\n# head\n",
    "ended by a rule": "| a | b |\n|---|---|\n***\n",
    "a list item for a delimiter": "a | b\n- | -\n",
    "no outer pipes": "a | b\n--|--\nc | d\n",
    "indented three": "   | a | b |\n   |---|---|\n   | c | d |\n",
    "a table opening an item": "- | a | b |\n  |---|---|\n",
    "after an empty quote line": ">\n| a | b |\n|---|---|\n",
    "after a fence": "```\nx\n```\n| a | b |\n|---|---|\n",
    "a fence in an item": "- ```\n  | a | b |\n  |---|---|\n  ```\n",
    "a tab of indent": "\t| a | b |\n\t|---|---|\n",
    "after a reference": "[ref]: /url\n2. two\n--|--\n--|--\n",
    "no delimiter": "| a | b |\n| c | d |\n",
    "a delimiter one short": "| a | b |\n|---|\n",
}


def _rendered_tables(text: str) -> list[dict]:
    """`_MD`'s top-level tables: the lines each spans and every row's cell texts."""
    found = []
    tokens = _MD.parse(text)
    for at, token in enumerate(tokens):
        if token.type != "table_open" or token.level != 0:
            continue
        rows, cells = [], []
        for inner in tokens[at:]:
            if inner.type == "table_close" and inner.level == 0:
                break
            if inner.type == "tr_open":
                cells = []
            elif inner.type == "inline":
                cells.append(inner.content)
            elif inner.type == "tr_close":
                rows.append(cells)
        found.append({"lines": list(token.map), "rows": rows})
    return found


_FORMATTER_TABLES = """Object.fromEntries(Object.entries(CORPUS).map(([name, text]) => {
  const lines = text.split('\\n');
  return [name, topTables(lines).map(table => ({
    lines: [table.first, table.last],
    // Every row but the delimiter, as `escapedSplit` hands the renderer its
    // cells: trimmed, and with the backslash of an escaped pipe gone.
    rows: [table.first, ...Array.from({length: table.last - table.first - 2},
                                      (_, k) => table.first + 2 + k)]
      .map(i => {
        const {text: row} = tableRow(lines[i]);
        return tableCells(row).map(cell =>
          row.slice(cell.from, cell.to).trim().split('\\\\|').join('|'));
      }),
  }))];
}))
"""


def test_the_formatter_and_markdown_it_agree_on_every_table(page: str):
    """The two readers walk the same tree, asked of both on two things: which
    lines are a top-level table — the formatter's line ranges against
    `table_open.map` — and where each row's cells split, against the `th` and
    `td` contents. A nested table is not top-level for either, and the
    assertion there is that the formatter leaves it byte for byte alone."""
    got = shipped(
        page, f"(() => {{ const CORPUS = {json.dumps(CORPUS)}; return {_FORMATTER_TABLES}; }})()"
    )
    for name, text in CORPUS.items():
        theirs = _rendered_tables(text)
        ours = got[name]
        assert [t["lines"] for t in ours] == [t["lines"] for t in theirs], (
            f"{name}: the formatter calls lines {[t['lines'] for t in ours]} tables and "
            f"the renderer draws {[t['lines'] for t in theirs]}"
        )
        for mine, rendered in zip(ours, theirs, strict=True):
            # The renderer pads a short row and drops a long row's extras, which
            # is what it DRAWS; the split is what is being compared.
            count = len(rendered["rows"][0])
            drawn = [(row + [""] * count)[:count] for row in mine["rows"]]
            assert drawn == rendered["rows"], f"{name}: cells split differently"

    untouched = [
        "fenced",
        "blockquote",
        "lazy under a quote",
        "list item",
        "lazy under an item",
        "a table opening an item",
        "a fence in an item",
        "indented code",
        "maths",
    ]
    for name in untouched:
        assert aligned(page, CORPUS[name]) == CORPUS[name], f"{name} was rewritten"


def test_aligning_twice_changes_nothing(page: str):
    """Idempotent over the corpus — and over the one shape where writing a table
    out changed what it was. `- | -` under a line of text is a table's header,
    because a delimiter row may not open with `- `; written `| - | - |` it IS a
    delimiter row, and the line above becomes the header of a table it was never
    part of. Found by fuzzing this formatter against the renderer, and left as
    typed."""
    dashed = "a | b\n- | -\n--|--\n"
    bodies = [*CORPUS.values(), dashed]
    got = shipped(
        page,
        f"{json.dumps(bodies)}.map(t => [alignTables(t), alignTables(alignTables(t))])",
    )
    for body, (once, twice) in zip(bodies, got, strict=True):
        assert once == twice, f"aligning {body!r} twice moved it again: {once!r} then {twice!r}"
    assert aligned(page, dashed) == dashed


# The lines the bodies below are made of: every block start the scan has a rule
# for, and the table shapes, in random order. A fixed seed, so a failure here is
# a body that can be pasted into the assertion's message and run again.
_PIECES = [
    "",
    "",
    "text",
    "a | b",
    "| a | b |",
    "|---|---|",
    "--|--",
    "- | -",
    ":-:|---",
    "| c |",
    "- item",
    "* item",
    "1. one",
    "2. two",
    "1) x",
    "-",
    "> quote",
    ">",
    "> | a | b |",
    "```",
    "~~~",
    "    code | x",
    "  | a | b |",
    "  |---|---|",
    "# head",
    "***",
    "---",
    "===",
    "$$",
    "$$x$$",
    "[ref]: /url",
    "<div>",
    "\t| t | u |",
    "a \\| b | c",
    "`x|y` | z",
    "  - nested",
    "   text",
    "| 👍🏽 | 表 |",
    "| long long cell | é |",
]


def _body(rng: random.Random) -> str:
    """Lines from `_PIECES`, and in most bodies a ragged table dropped in among
    them — at the top, under a line of text, under an item or a quote — so that
    most of what is asked is a table next to something."""
    lines = [rng.choice(_PIECES) for _ in range(rng.randint(1, 7))]
    if rng.random() < 0.8:
        width = rng.randint(1, 3)

        def row(cells: int) -> str:
            return "|".join(
                rng.choice(["x", " long cell ", "👍🏽", "", "a\\|b"]) for _ in range(cells)
            )

        rule = "|".join(rng.choice(["-", ":-", "-:", ":-:"]) for _ in range(width))
        table = [f"|{row(width)}|", f"|{rule}|"]
        table += [rng.choice(["", "|"]) + row(rng.randint(1, width + 1)) for _ in range(3)]
        at = rng.randint(0, len(lines))
        lines[at:at] = table[: rng.randint(2, 5)]
    return "\n".join(lines)


def test_aligning_never_changes_what_the_page_draws(page: str):
    """The property the whole feature rests on, asked of the renderer: a body and
    the same body with its tables aligned render to the same HTML, source lines
    included. Six hundred bodies assembled from the block starts the scan knows
    about — lists, quotes, fences, maths, headings, rules, references, lazy
    lines — so a scan that called a paragraph a table, or wrote one out so that
    it read as something else, shows up as a page that changed."""
    rng = random.Random(20261128)
    bodies = [_body(rng) for _ in range(600)]
    got = shipped(page, f"{json.dumps(bodies)}.map(alignTables)")
    changed = [b for b, a in zip(bodies, got, strict=True) if _MD.render(b) != _MD.render(a)]
    assert not changed, f"aligning changed what {len(changed)} bodies draw, first {changed[0]!r}"
    assert sum(b != a for b, a in zip(bodies, got, strict=True)) > 200, (
        "almost nothing was aligned, so the property above was asked of nothing"
    )


# --------------------------------------------------------------------------- #
# The Table button's four edits
# --------------------------------------------------------------------------- #

_TABLE = "Intro\n\n|a|b|\n|-|-|\n|cell one|x|\n|two|y|\n\nEnd\n"


def edit(page: str, op: str, text: str = _TABLE, word: str = "one") -> dict:
    """`tableEdit` with the caret on `word`, and what is right of the caret."""
    return shipped(
        page,
        f"(() => {{ const t = {json.dumps(text)};"
        f" const e = tableEdit(t, t.indexOf({json.dumps(word)}), {json.dumps(op)});"
        " if (e === null) return 'no edit';"
        " return e.text ? {...e, after: e.text.slice(e.caret).split('\\n')[0]} : e; })()",
    )


def test_add_row_below_puts_an_empty_row_under_the_caret_and_the_caret_in_it(page: str):
    got = edit(page, "row-below")
    assert got["text"] == (
        "Intro\n\n"
        "| a        | b   |\n"
        "| -------- | --- |\n"
        "| cell one | x   |\n"
        "|          |     |\n"
        "| two      | y   |\n"
        "\nEnd\n"
    )
    assert got["after"] == "         |     |", "the caret is not in the new row's first cell"
    # On the header the new row is the first one under it, not under the
    # delimiter row, which is not a row anybody types in.
    head = edit(page, "row-below", word="a|")
    assert head["text"].split("\n")[4] == "|          |     |"


def test_add_column_right_puts_an_empty_column_beside_the_caret(page: str):
    got = edit(page, "column-right")
    assert got["text"] == (
        "Intro\n\n"
        "| a        |     | b   |\n"
        "| -------- | --- | --- |\n"
        "| cell one |     | x   |\n"
        "| two      |     | y   |\n"
        "\nEnd\n"
    )
    assert got["after"] == "    | x   |", "the caret is not in the new column, on its own row"


def test_delete_row_takes_the_caret_s_row_and_never_the_header(page: str):
    got = edit(page, "delete-row")
    assert got["text"] == "Intro\n\n| a   | b   |\n| --- | --- |\n| two | y   |\n\nEnd\n"
    assert got["after"] == "two | y   |", "the caret is not on the row that took its place"
    last = edit(page, "delete-row", word="two")
    assert last["after"] == "cell one | x   |", "deleting the last row left the caret nowhere"
    assert edit(page, "delete-row", word="a|") == {
        "refused": "The header row is what makes this a table, so it stays."
    }


def test_delete_column_takes_the_caret_s_column_from_every_row(page: str):
    got = edit(page, "delete-column")
    assert got["text"] == "Intro\n\n| b   |\n| --- |\n| x   |\n| y   |\n\nEnd\n"
    assert got["after"] == "x   |"
    alone = "| a |\n|---|\n| b |\n"
    assert edit(page, "delete-column", text=alone, word="b") == {
        "refused": "A table needs a column, so its last one stays."
    }


def test_an_edit_outside_a_table_is_no_edit(page: str):
    assert edit(page, "row-below", word="Intro") == "no edit"
    assert edit(page, "row-below", word="End") == "no edit"


def test_the_caret_is_found_in_the_cell_it_is_in_whatever_is_before_it(page: str):
    """An emoji before the caret is two UTF-16 units and one character; the
    offsets here are the surface's units, and the column has to come out the
    same either way."""
    text = "| 👍🏽 | 表 | c |\n|---|---|---|\n| 👍 | 🇨🇭 | z |\n"
    got = shipped(
        page,
        f"(() => {{ const t = {json.dumps(text)}; return [tableAt(t, t.indexOf('z')),"
        " tableAt(t, t.indexOf('表')), tableAt(t, 0), tableAt(t + '\\nafter', t.length + 2)]; })()",
    )
    assert got[0] == {
        "start": 0,
        "end": len(text.encode("utf-16-le")) // 2 - 1,
        "row": 2,
        "column": 2,
    }
    assert got[1]["row"] == 0 and got[1]["column"] == 1
    assert got[2]["column"] == 0, "a caret before the leading pipe is in the first cell"
    assert got[3] is None


def test_the_caret_keeps_its_place_in_its_cell_when_the_table_is_aligned(page: str):
    """Saving realigns the table the caret is in. The caret stays in the same row,
    the same cell and the same place in that cell's text, and a caret after the
    table moves by exactly what the table grew."""
    text = "|a|b|\n|-|-|\n|cell one|x|\n\nAfter 👍 here\n"
    got = shipped(
        page,
        f"(() => {{ const t = {json.dumps(text)}; const runs = alignedRuns(t);"
        " const now = alignTables(t);"
        " const inCell = caretThrough(t, runs, t.indexOf('one') + 1);"
        " const after = caretThrough(t, runs, t.indexOf('here'));"
        " return [now.slice(inCell - 6, inCell), now.slice(after, after + 4)]; })()",
    )
    assert got == ["cell o", "here"]


# --------------------------------------------------------------------------- #
# On an explicit save, and only then
# --------------------------------------------------------------------------- #

# A page with no server behind it: every PATCH is kept for the test and answered
# as committed, the preview is answered, and the socket never opens — so the
# save takes the PATCH path, which is the one that sends the body as the box
# holds it.
_NO_ROOM = """
window.__errors = [];
addEventListener('error', event => window.__errors.push(String(event.message)));
window.__patches = [];
const answered = value => new Response(JSON.stringify(value),
  {status: 200, headers: {'content-type': 'application/json'}});
window.fetch = async (url, init) => {
  if (init && init.method === 'PATCH') {
    window.__patches.push(JSON.parse(init.body).body);
    return answered({commit: 'c'.repeat(40), outcome: 'committed'});
  }
  return answered({html: '<p data-startline="1">rendered</p>'});
};
function Unopened() { this.readyState = 0; }
Unopened.OPEN = 1;
Unopened.prototype.send = function () {};
Unopened.prototype.close = function () {};
window.WebSocket = Unopened;
"""

_SAVED = r"""
const wait = ms => new Promise(go => setTimeout(go, ms));
if (!document.querySelector('article.record.editing')) { flipEditing(); await wait(300); }
const opened = SURFACE.text();
// Typed, as a person's edit: through `splice` outside `apply`.
SURFACE.splice(opened.length, opened.length, RAGGED);
SURFACE.setCaret(SURFACE.text().indexOf('cell one') + 6);
const typed = SURFACE.text();
document.getElementById('save').focus();
document.getElementById('save').click();
await wait(300);
const caret = SURFACE.caret().from;
const clicked = {
  sent: window.__patches[0] ?? null,
  box: SURFACE.text(),
  caret: SURFACE.text().slice(caret - 6, caret),
  focus: document.activeElement.id,
};
historyOf(SURFACE).step('undo');
await wait(100);
const undone = SURFACE.text();
// A row typed under the table, and Ctrl-S this time.
SURFACE.splice(undone.length, undone.length, MORE);
window.dispatchEvent(new KeyboardEvent('keydown',
  {key: 's', ctrlKey: true, bubbles: true, cancelable: true}));
await wait(300);
return {opened, typed, clicked, undone, keyed: window.__patches[1] ?? null,
        patches: window.__patches.length, errors: window.__errors};
"""

_RAGGED = "\n\n|a|b|\n|-|-|\n|cell one|x|\n"
_ALIGNED = "\n\n| a        | b   |\n| -------- | --- |\n| cell one | x   |\n"
_MORE = "|three|a much longer cell|\n"
_GROWN = (
    "\n\n| a        | b                  |\n"
    "| -------- | ------------------ |\n"
    "| cell one | x                  |\n"
    "| three    | a much longer cell |\n"
)


def _with_stub(html: str, stub: str) -> str:
    return html.replace('<link rel="icon"', f'<script>{stub}</script><link rel="icon"', 1)


@pytest.mark.parametrize("editor", ["plain", "ace"])
def test_save_aligns_the_tables_in_the_body(client: TestClient, tmp_path: Path, editor: str):
    """The Save button and Ctrl-S both align before the body goes, on both
    surfaces, as an edit: the caret stays in the cell it was in, the focus stays
    on the button that was pressed, and one undo gives back the table as typed."""
    html = client.get(f"/detail/{TASK}?editor={editor}").text
    got = measured_in(
        chrome(),
        _with_stub(html, _NO_ROOM),
        tmp_path / f"saved-{editor}.html",
        1400,
        _SAVED.replace("RAGGED", json.dumps(_RAGGED)).replace("MORE", json.dumps(_MORE)),
        query=f"?editor={editor}",
        patience=4000,
    )
    assert got["errors"] == [], got["errors"]
    assert got["typed"] == got["opened"] + _RAGGED, "the ragged table never reached the box"
    assert got["clicked"]["sent"] == got["opened"] + _ALIGNED, (
        f"Save sent the table as typed: {got['clicked']['sent']!r}"
    )
    assert got["clicked"]["box"] == got["clicked"]["sent"]
    assert got["clicked"]["caret"] == "cell o", "the caret left the cell it was typing in"
    assert got["clicked"]["focus"] == "save", "aligning took the focus off the Save button"
    assert got["undone"] == got["typed"], "one undo did not give back the table as typed"
    assert got["keyed"] == got["opened"] + _GROWN, f"Ctrl-S did not align: {got['keyed']!r}"
    assert got["patches"] == 2


_IN_A_ROOM = r"""
SURFACE.setCaret(SURFACE.text().indexOf('cell one') + 6);
// Bob's sentence, in the paragraph above the table, before the press.
window.__room.onmessage({data: JSON.stringify({t: 'update', u: REMOTE})});
const before = window.__sent.length;
await save();
return {errors: window.__errors, sent: window.__sent, box: SURFACE.text(),
        frames: window.__sent.slice(before).map(frame => frame.t)};
"""

# Long enough that a body replaced whole and a table replaced alone are far apart
# in what the room credits to the person who pressed Save.
_PROSE = "Intro line. " + "The seam shows up only with two ranks, and only at the drum. " * 5


@pytest.mark.parametrize("editor", ["plain", "ace"])
def test_the_alignment_reaches_the_room_as_splices_of_the_table_only(
    client: TestClient, plan: Path, tmp_path: Path, editor: str
):
    """Somebody else is typing in the paragraph above while this tab saves.

    The alignment goes up the socket as an edit of the table's lines and of
    nothing else. Asked of a real `Room` two ways: what it credits to the tab
    that saved, which is the table's characters and not the body's — a body
    written back whole would credit the paragraph to whoever pressed Save — and
    a second sentence of Bob's, made against the document before the alignment
    arrived, which has to land where he typed it. Ace is the surface where this
    can go wrong: it sends its own splices, where the textarea's are recovered
    from a prefix and a suffix and come out minimal whatever the page did.
    """
    body = f"{_PROSE}\n\n|a|b|\n|-|-|\n|cell one|x|\n\nAfter.\n"
    front, _ = split_front_matter(stored(plan))
    commit_directly(plan, {**SEED, PATH: f"---\n{front}\n---\n\n{body}"}, "a ragged table")
    shown = shown_body(client)
    assert shown == body, "the page is not showing the body this test is about"

    room = coedit.Room(TASK, PATH, "0" * 40, shown)
    welcome = _welcome(room)
    bob = coedit.Room(TASK, PATH, "0" * 40, shown)
    above = bob.absorb(shown.replace("Intro line.", "Intro line, by bob."))
    room.apply(above, "bob")
    # Made before Bob's copy sees the alignment: concurrent with it.
    below = bob.absorb(bob.body().replace("After.", "After, and more."))

    answer = in_chrome_room(
        client,
        tmp_path / f"room-{editor}.html",
        room,
        welcome,
        _IN_A_ROOM.replace("REMOTE", json.dumps(base64.b64encode(above).decode())),
        editor=editor,
    )
    room.apply(below, "bob")

    table = "| a        | b   |\n| -------- | --- |\n| cell one | x   |"
    assert answer["frames"][-1] == "save" and "update" in answer["frames"], answer["frames"]
    assert room.body() == body.replace("Intro line.", "Intro line, by bob.").replace(
        "|a|b|\n|-|-|\n|cell one|x|", table
    ).replace("After.", "After, and more."), f"the room holds {room.body()!r}"
    assert room.typed.get("ann", 0) <= len(table), (
        f"the room credits {room.typed.get('ann')} characters to the tab that saved, "
        f"for a table of {len(table)}: the alignment went up as more than the table"
    )


def test_the_room_idle_commit_does_not_align(client: TestClient, plan: Path):
    """The room commits twenty seconds after the last keystroke, and that commit
    is the server's. Nothing in the page answers it by aligning: the box keeps
    the table as typed, and nothing but the keystroke goes up the socket."""
    body = "Intro.\n\n|a|b|\n|-|-|\n|cell one|x|\n"
    front, _ = split_front_matter(stored(plan))
    commit_directly(plan, {**SEED, PATH: f"---\n{front}\n---\n\n{body}"}, "a ragged table")
    shown = shown_body(client)
    page = client.get(f"/detail/{TASK}?editor=plain").text
    room = coedit.Room(TASK, PATH, "0" * 40, shown)
    typed = shown.replace("Intro.", "Intro, typed.")
    quiet = {"t": "saved", "commit": "e" * 40, "outcome": "committed", "pushed": True}
    answer = run_js(
        page,
        "(() => {"
        "  flipEditing();"
        "  __socket.opened();"
        f" __socket.hear({json.dumps(_welcome(room))});"
        "  if (!COEDIT.live()) return 'the room never came up';"
        "  const box = document.querySelector('[name=body]');"
        f" box.value = {json.dumps(typed)};"
        "  box.dispatchEvent(new Event('input', {bubbles: true}));"
        f" __socket.hear({json.dumps(quiet)});"
        "  return {box: box.value, sent: __socket.sent()};"
        "})()",
        page=True,
        socket=True,
    )
    assert not answer["errors"], answer["errors"]
    assert answer["value"]["box"] == typed, "the room's own commit realigned the table"
    for frame in answer["value"]["sent"]:
        if frame["t"] == "update":
            room.apply(base64.b64decode(frame["u"]), "ann")
    assert room.body() == typed
    assert "save" not in [frame["t"] for frame in answer["value"]["sent"]]


_SAVED_AS_TYPED = """(async () => {
  flipEditing();
  const box = document.querySelector('[name=body]');
  box.value = box.value + RAGGED;
  box.dispatchEvent(new Event('input', {bubbles: true}));
  await save();
  const control = document.getElementById('tablefmt');
  const said = control.textContent;
  // The shim's elements have no `click()`, and this is what one runs.
  control.onclick();
  return {said, then: control.textContent, sent: box.value};
})()"""


def test_format_tables_on_save_can_be_switched_off(page: str):
    """Per person, beside the draft interval, on by default, and kept through
    `remembered`: a page opened with it off saves the table as typed, its
    control says so in words a reader can find, and pressing it turns it back on
    for the next page as well as this one."""
    expression = _SAVED_AS_TYPED.replace("RAGGED", json.dumps(_RAGGED))
    answer = run_js(
        page,
        expression,
        page=True,
        storage={"openproj:editor:1": json.dumps({"tables": "off"})},
        replies=[{"status": 200, "json": {"commit": "d" * 40, "outcome": "committed"}}],
    )
    assert answer["settled"], answer["errors"]
    value = answer["value"]
    patches = [call for call in answer["calls"] if call["method"] == "PATCH"]
    assert len(patches) == 1, answer["calls"]
    assert json.loads(patches[0]["body"])["body"] == value["sent"]
    assert value["sent"].endswith(_RAGGED), "the table was aligned with the preference off"
    assert value["said"] == "Format tables on save: off"
    assert value["then"] == "Format tables on save: on"
    assert json.loads(answer["stored"]["openproj:editor:1"])["tables"] == "on"

    fresh = run_js(page, "document.getElementById('tablefmt').textContent", page=True)
    assert fresh["value"] == "Format tables on save: on", "the default is not on"


# --------------------------------------------------------------------------- #
# The Table button, which is two buttons in one
# --------------------------------------------------------------------------- #

_PRESSED = r"""
const wait = ms => new Promise(go => setTimeout(go, ms));
if (!document.querySelector('article.record.editing')) { flipEditing(); await wait(300); }
const button = [...document.querySelectorAll('#marks .mark')].find(one => one.title === 'Table');
const menu = () => document.querySelector('.tablemenu');
const said = () => document.getElementById('state').textContent;
const press = () => button.dispatchEvent(
  new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
const put = (text, word) => {
  SURFACE.apply(() => SURFACE.splice(0, SURFACE.text().length, text));
  SURFACE.setCaret(text.indexOf(word));
};

// Outside a table it is the button it always was.
SURFACE.setCaret(0);
press();
await wait(50);
const outside = {text: SURFACE.text(), menu: !menu().hidden};

// Inside one, from the keyboard: Enter on the focused button is a click with no
// pointer behind it, and the menu takes the focus.
put(TABLE, 'one');
button.focus();
button.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, detail: 0}));
await wait(50);
const key = name => document.activeElement.dispatchEvent(
  new KeyboardEvent('keydown', {key: name, bubbles: true, cancelable: true}));
const keyboard = {
  items: [...menu().querySelectorAll('[role=menuitem]')].map(one => one.textContent),
  expanded: button.getAttribute('aria-expanded'),
  first: document.activeElement.textContent,
};
key('ArrowDown');
keyboard.down = document.activeElement.textContent;
key('ArrowUp');
key('ArrowUp');
keyboard.wrapped = document.activeElement.textContent;
key('End');
keyboard.end = document.activeElement.textContent;
key('Home');
keyboard.home = document.activeElement.textContent;
key('Escape');
keyboard.escaped = {hidden: menu().hidden, back: document.activeElement === button,
                    expanded: button.getAttribute('aria-expanded')};
keyboard.untouched = SURFACE.text() === TABLE;

const edits = {};
for (const label of LABELS) {
  put(TABLE, 'one');
  press();
  await wait(30);
  [...menu().querySelectorAll('button')].find(one => one.textContent === label).click();
  await wait(30);
  const at = SURFACE.caret().from;
  edits[label] = {text: SURFACE.text(), after: SURFACE.text().slice(at).split('\n')[0],
                  said: said(), hidden: menu().hidden};
}
historyOf(SURFACE).step('undo');
await wait(50);
const undone = SURFACE.text();

put(TABLE, 'a|');
press();
await wait(30);
[...menu().querySelectorAll('button')].find(one => one.textContent === 'Delete row').click();
await wait(30);
const refused = {text: SURFACE.text(), said: said()};
return {outside, keyboard, edits, undone, refused};
"""

_LABELS = {
    "row-below": "Add row below",
    "column-right": "Add column right",
    "delete-row": "Delete row",
    "delete-column": "Delete column",
}


@pytest.mark.parametrize("editor", ["plain", "ace"])
def test_the_table_button_inserts_outside_a_table_and_edits_inside_one(
    client: TestClient, page: str, tmp_path: Path, editor: str
):
    """The `▤` button: with the caret outside a top-level table it inserts the
    starter table it always has; inside one it opens a menu of exactly four
    edits, reachable by Tab and Enter, walked with the arrows, closed by Escape
    with the focus handed back. Each item edits as `tableEdit` does, as one undo
    step, and says what it did in the live region."""
    html = client.get(f"/detail/{TASK}?editor={editor}").text
    got = measured_in(
        chrome(),
        html,
        tmp_path / f"table-button-{editor}.html",
        1400,
        _PRESSED.replace("TABLE", json.dumps(_TABLE)).replace(
            "LABELS", json.dumps(list(_LABELS.values()))
        ),
        query=f"?editor={editor}",
        patience=5000,
    )

    assert "| Heading | Heading |\n| --- | --- |\n| Cell | Cell |" in got["outside"]["text"], (
        "outside a table the button no longer inserts the starter table"
    )
    assert got["outside"]["menu"] is False, "and it opened the menu instead of only writing"

    keyboard = got["keyboard"]
    assert keyboard["items"] == list(_LABELS.values())
    assert keyboard["expanded"] == "true" and keyboard["first"] == "Add row below", (
        "the menu opened somewhere the keyboard was not taken to"
    )
    assert keyboard["down"] == "Add column right"
    assert keyboard["wrapped"] == "Delete column", "ArrowUp from the first item did not wrap"
    assert keyboard["end"] == "Delete column" and keyboard["home"] == "Add row below"
    assert keyboard["escaped"] == {"hidden": True, "back": True, "expanded": "false"}
    assert keyboard["untouched"], "opening and closing the menu wrote something"

    said = {
        "row-below": "A row is added below.",
        "column-right": "A column is added to the right.",
        "delete-row": "The row is deleted.",
        "delete-column": "The column is deleted.",
    }
    for op, label in _LABELS.items():
        want = edit(page, op)
        assert got["edits"][label]["text"] == want["text"], f"{label} wrote something else"
        assert got["edits"][label]["after"] == want["after"], f"{label} put the caret elsewhere"
        assert said[op] in got["edits"][label]["said"], got["edits"][label]["said"]
        assert got["edits"][label]["hidden"], f"{label} left the menu open"
    assert got["undone"] == _TABLE, "one undo did not take the last edit back"
    assert got["refused"]["text"] == _TABLE
    assert "header row is what makes this a table" in got["refused"]["said"]
