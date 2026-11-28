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

import json
import random

import pygit2
import pytest
from fastapi.testclient import TestClient
from test_injection import run_js
from test_store import commit_directly
from test_web import SECRET, SEED, TASK

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
    with TestClient(create_app(repo, auth="dev", secret=SECRET)) as client:
        return client.get(f"/detail/{TASK}?editor=plain").text


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
