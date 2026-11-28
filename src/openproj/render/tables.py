"""Markdown tables in a body: found the way `_MD` finds them, and aligned on save."""

from __future__ import annotations

from markupsafe import Markup

# --- where this is, and where it is not -------------------------------------
#
# A block of its own and not a part of `_COMBOBOX`, on the argument `_ACE_SURFACE`
# makes in `editor.py`: `_COMBOBOX` is emitted on the table and the cycle page as
# well, and neither has a body to hold a table. So this goes out with the toolbar
# that can reach it — the record page and the create form, when they are
# editable — and nowhere else. Nothing here runs at load: `FORMATS`'s Table
# entry and `save()` call into it when they are pressed, so its place among the
# page's scripts does not matter.
_TABLES = Markup(r"""
<script>
// --- tables in the body, found the way the renderer finds them ---------------
//
// jcanton, 2026-11-27: a markdown table typed by hand is ragged, and a table
// you cannot read as source is a table nobody edits. So an explicit save leaves
// every top-level table in the body aligned, and the Table button edits the
// table the caret is in. `design/body-tables-links-selection.md` §1 is the
// decision; what follows is the part of it that has to be exact.
//
// **The renderer decides what a table is, and this follows it.** `_MD`
// (`render/markdown.py`) is markdown-it-py with `table` switched on and `html`
// off, and its `table` rule is the authority on three things: which lines are a
// table, where a row's cells split, and how many columns the table has. A
// formatter that disagreed would pad columns the rendered table does not have,
// or realign a paragraph that merely contains pipes — the "two readers walk the
// same tree" failure in `AGENTS.md`. So the block scan below is markdown-it's
// own block order at the top level, rule by rule, and
// `test_the_formatter_and_markdown_it_agree_on_every_table` holds the two
// together over a corpus of awkward bodies.
//
// **Top level only.** A table inside a blockquote or a list item is left exactly
// as typed: aligning it means rewriting `> ` and list-indent prefixes, nested,
// for a case shaping documents rarely have. Where this scan cannot be sure a
// line is outside a list or a quote — a lazy continuation line — it says "not a
// table", because a table left ragged costs nothing and a paragraph realigned
// is somebody's prose rewritten.
//
// **Every offset here is a UTF-16 code unit**, the surfaces' unit, and every
// edit this produces is whole lines: a splice that starts and ends at a line
// boundary cannot land inside a surrogate pair, which is the defect this
// repository has already shipped twice.

// Spaces and tabs only, which is what markdown-it counts as indentation, with a
// tab to the next multiple of four.
function tableLead(line) {
  let col = 0, at = 0;
  while (at < line.length && (line[at] === ' ' || line[at] === '\t')) {
    col = line[at] === '\t' ? col + 4 - (col % 4) : col + 1;
    at++;
  }
  return {col, at, blank: at === line.length, rest: line.slice(at)};
}

// The block starts that end a paragraph, a table or a blockquote, each the
// regular expression of markdown-it's rule of the same name. All of them refuse
// a line indented four or more, which is code.
const TABLE_FENCE = /^(`{3,}|~{3,})(.*)$/;
const TABLE_HR = /^([*_-])[ \t]*(?:\1[ \t]*){2,}$/;
const TABLE_HEADING = /^#{1,6}(?:[ \t]|$)/;
const TABLE_ITEM = /^(?:([*+-])|(\d{1,9})[.)])(?:[ \t]|$)/;
const TABLE_UNDERLINE = /^(?:=+|-+)[ \t]*$/;

function fenceOf(lead) {
  if (lead.col >= 4) return null;
  const found = TABLE_FENCE.exec(lead.rest);
  if (!found) return null;
  // A backtick fence's info string may not hold a backtick: `` ```a`b `` is
  // a code span, not a fence.
  if (found[1][0] === '`' && found[2].includes('`')) return null;
  return {mark: found[1][0], length: found[1].length};
}

function closesFence(lead, fence) {
  if (lead.col >= 4) return false;
  let at = 0;
  while (lead.rest[at] === fence.mark) at++;
  return at >= fence.length && /^[ \t]*$/.test(lead.rest.slice(at));
}

// `context` is whose terminator this is asked for, because markdown-it's list
// rule answers differently inside a paragraph: there an empty item, or an
// ordered one not numbered 1, cannot interrupt.
function itemOf(lead) {
  if (lead.col >= 4) return null;
  const found = TABLE_ITEM.exec(lead.rest);
  if (!found) return null;
  return {
    width: found[0].trimEnd().length,
    one: found[2] === undefined || Number(found[2]) === 1,
    empty: /^[ \t]*$/.test(lead.rest.slice(found[0].trimEnd().length)),
  };
}

function endsABlock(lead, context) {
  if (lead.blank || lead.col >= 4) return false;
  if (fenceOf(lead) || lead.rest[0] === '>' || TABLE_HR.test(lead.rest)) return true;
  if (TABLE_HEADING.test(lead.rest)) return true;
  const item = itemOf(lead);
  if (!item) return false;
  return context !== 'paragraph' || (item.one && !item.empty);
}

// Where a row's cells are: markdown-it's `escapedSplit`, which splits on every
// `|` not immediately after a backslash — including one inside backticks. That
// is GFM's rule, and a reader's intuition that `` `a|b` `` is one cell is not
// what the renderer draws. The first and last pieces are dropped when they are
// exactly empty, which is what a leading and a trailing pipe leave. Positions
// are into `text`, which is the line already trimmed, as markdown-it trims it.
function tableCells(text) {
  const cells = [];
  let from = 0;
  for (let at = 0; at < text.length; at++) {
    if (text[at] === '|' && text[at - 1] !== '\\') {
      cells.push({from, to: at});
      from = at + 1;
    }
  }
  cells.push({from, to: text.length});
  if (cells.length && cells[0].from === cells[0].to) cells.shift();
  if (cells.length && cells[cells.length - 1].from === cells[cells.length - 1].to) cells.pop();
  return cells;
}

// The trimmed row and where it starts in its line.
function tableRow(line) {
  const lead = tableLead(line);
  const text = lead.rest.trim();
  return {text, at: lead.at + (lead.rest.length - lead.rest.trimStart().length)};
}

// Whether line `i` opens a table: markdown-it's `table` rule up to the point it
// pushes a token. Answers the delimiter row's alignments, one per column.
// The alignments a delimiter row says, one per column, or `null` when the line
// is not one. Asked of the second line of a table — and of the first line this
// writes, see `tableLines`.
function delimiterOf(rule) {
  if (rule.length < 2 || !'|-:'.includes(rule[0])) return null;
  if (!'|-: \t'.includes(rule[1])) return null;
  // `- ` is a list item, which the rule refuses before it looks any further.
  if (rule[0] === '-' && (rule[1] === ' ' || rule[1] === '\t')) return null;
  if (!/^[|\-: \t]*$/.test(rule)) return null;
  // Split on every pipe — the delimiter row has no escapes to honour — and an
  // empty piece is allowed only at either end.
  const pieces = rule.split('|');
  const aligns = [];
  for (let k = 0; k < pieces.length; k++) {
    const piece = pieces[k].trim();
    if (!piece) {
      if (k === 0 || k === pieces.length - 1) continue;
      return null;
    }
    if (!/^:?-+:?$/.test(piece)) return null;
    aligns.push(piece.endsWith(':') ? (piece.startsWith(':') ? 'center' : 'right')
      : piece.startsWith(':') ? 'left' : '');
  }
  return aligns;
}

// Whether line `i` opens a table: markdown-it's `table` rule up to the point it
// pushes a token. Answers the delimiter row's alignments, one per column.
function tableHead(lines, i) {
  if (i + 1 >= lines.length) return null;
  const head = tableLead(lines[i]);
  const under = tableLead(lines[i + 1]);
  if (head.col >= 4 || under.col >= 4) return null;
  const aligns = delimiterOf(under.rest);
  if (!aligns) return null;
  const text = head.rest.trim();
  if (!text.includes('|')) return null;
  const count = tableCells(text).length;
  return count && count === aligns.length ? aligns : null;
}

// The line after a table's last row: a blank line, a line of code, or anything
// that would start a block of its own ends it.
function tableEnd(lines, i) {
  let j = i + 2;
  while (j < lines.length) {
    const lead = tableLead(lines[j]);
    if (lead.blank || lead.col >= 4 || endsABlock(lead, 'table')) break;
    j++;
  }
  return j;
}

// `$$` opens a display equation (`dollarmath_plugin`) only if it closes before a
// blank line; one that does not is a paragraph that starts with two dollars.
function mathEnd(lines, i) {
  const first = tableLead(lines[i]).rest.trim();
  if (first.length > 3 && first.endsWith('$$')) return i + 1;
  for (let j = i + 1; j < lines.length; j++) {
    const said = tableLead(lines[j]).rest.trim();
    if (said.endsWith('$$')) return j + 1;
    if (!said) return null;
  }
  return null;
}

// A blockquote takes every `>` line and every lazy line after one, until a blank
// line, a `>` line with nothing in it followed by anything else, or a block
// start. markdown-it adds the lazy line whatever the quote's last block was.
function quoteEnd(lines, i) {
  let empty = /^>[ \t]*$/.test(tableLead(lines[i]).rest);
  let j = i + 1;
  while (j < lines.length) {
    const lead = tableLead(lines[j]);
    if (lead.blank) break;
    if (lead.rest[0] === '>') {
      empty = /^>[ \t]*$/.test(lead.rest);
      j++;
      continue;
    }
    if (empty || endsABlock(lead, 'blockquote')) break;
    j++;
  }
  return j;
}

// A list, as far as a top-level scan needs one: every line indented to an
// item's content, every further item, and every lazy line after a line of text.
// The lazy line is where this is deliberately wider than markdown-it, which
// takes it only when the item's last block is a paragraph — so a table typed
// straight under a list item without a blank line is left alone even in the
// rare case the renderer would draw it.
function listEnd(lines, i) {
  const indentOf = lead => {
    const item = itemOf(lead);
    const after = tableLead(' '.repeat(lead.col + item.width) + lead.rest.slice(item.width));
    const gap = after.col - (lead.col + item.width);
    return lead.col + item.width + (after.blank || gap >= 5 ? 1 : gap);
  };
  let indent = indentOf(tableLead(lines[i]));
  let blank = false;
  let j = i + 1;
  let last = j;
  while (j < lines.length) {
    const lead = tableLead(lines[j]);
    if (lead.blank) { blank = true; j++; continue; }
    if (lead.col >= indent) { blank = false; last = ++j; continue; }
    if (itemOf(lead) && !TABLE_HR.test(lead.rest)) {
      indent = indentOf(lead);
      blank = false;
      last = ++j;
      continue;
    }
    if (blank || endsABlock(lead, 'list')) break;
    last = ++j;
  }
  return last;
}

// A paragraph, or a setext heading, which is a paragraph with an underline: it
// runs to a blank line or to a block that may interrupt one. An indented line
// does not end it, and a table does — markdown-it lets a table interrupt a
// paragraph, so `Text\n| a |\n| - |` is a paragraph and a table.
function paragraphEnd(lines, i) {
  let j = i + 1;
  while (j < lines.length) {
    const lead = tableLead(lines[j]);
    if (lead.blank) break;
    if (lead.col >= 4) { j++; continue; }
    if (TABLE_UNDERLINE.test(lead.rest)) return j + 1;
    if (tableHead(lines, j) || endsABlock(lead, 'paragraph')) break;
    j++;
  }
  return j;
}

// Every top-level table, as `{first, last, aligns}` in lines, `last` exclusive.
// markdown-it's block order at the top level: table, code, math, fence,
// blockquote, rule, list, heading, paragraph. `html` is off in `_MD`, so there
// is no HTML block, and a reference definition is a paragraph as far as a table
// is concerned, because a table interrupts both.
function topTables(lines) {
  const found = [];
  let i = 0;
  while (i < lines.length) {
    const lead = tableLead(lines[i]);
    if (lead.blank) { i++; continue; }
    const aligns = tableHead(lines, i);
    if (aligns) {
      const last = tableEnd(lines, i);
      found.push({first: i, last, aligns});
      i = last;
      continue;
    }
    if (lead.col >= 4) {
      let j = i + 1;
      let last = j;
      while (j < lines.length) {
        const next = tableLead(lines[j]);
        if (next.blank) { j++; continue; }
        if (next.col < 4) break;
        last = ++j;
      }
      i = last;
      continue;
    }
    if (lead.rest.startsWith('$$')) {
      const last = mathEnd(lines, i);
      if (last !== null) { i = last; continue; }
    }
    const fence = fenceOf(lead);
    if (fence) {
      let j = i + 1;
      while (j < lines.length && !closesFence(tableLead(lines[j]), fence)) j++;
      i = Math.min(j + 1, lines.length);
      continue;
    }
    if (lead.rest[0] === '>') { i = quoteEnd(lines, i); continue; }
    if (TABLE_HR.test(lead.rest) || TABLE_HEADING.test(lead.rest)) { i++; continue; }
    if (itemOf(lead)) { i = listEnd(lines, i); continue; }
    // A link reference definition is a block of its own and not the start of
    // a paragraph, so the line after it starts a block, and there `2. two` is a
    // list where under a paragraph it would be a line of text. One line, which
    // is how a plan writes one; a definition wrapped across two is read as
    // ending at the first, which can only cost a table, never invent one.
    if (/^\[(?:[^\]\\]|\\.)+\]:/.test(lead.rest)) { i++; continue; }
    i = paragraphEnd(lines, i);
  }
  return found;
}

// --- how wide a cell is drawn ---------------------------------------------
//
// Per grapheme, not per UTF-16 unit and not per code point: `👍🏽` is two code
// points and four units and one thing on the screen, and `é` written as `e` and
// a combining accent is two code points and one column. An emoji and a CJK
// character take two columns in every monospaced editor this is read in.
//
// The wide ranges are the W and F classes of Unicode's `EastAsianWidth.txt`, as
// Markus Kuhn's `wcwidth.c` folds them into ranges — compact, and right for the
// scripts a plan is written in. An emoji is wide when it is drawn as one:
// `Emoji_Presentation`, or anything followed by the U+FE0F that asks for it.
const TABLE_WIDE = [
  [0x1100, 0x115f], [0x2329, 0x232a], [0x2e80, 0x303e], [0x3041, 0x33ff],
  [0x3400, 0x4dbf], [0x4e00, 0x9fff], [0xa000, 0xa4cf], [0xac00, 0xd7a3],
  [0xf900, 0xfaff], [0xfe10, 0xfe19], [0xfe30, 0xfe6f], [0xff00, 0xff60],
  [0xffe0, 0xffe6], [0x20000, 0x2fffd], [0x30000, 0x3fffd],
];
let TABLE_SEGMENTER = null;

function tableWidth(text) {
  // A browser without `Intl.Segmenter` gets code points, which is right for
  // every cell without a combining mark or an emoji sequence in it.
  if (TABLE_SEGMENTER === null) {
    TABLE_SEGMENTER = typeof Intl !== 'undefined' && Intl.Segmenter
      ? new Intl.Segmenter(undefined, {granularity: 'grapheme'}) : false;
  }
  const parts = TABLE_SEGMENTER
    ? Array.from(TABLE_SEGMENTER.segment(text), part => part.segment) : Array.from(text);
  let width = 0;
  for (const part of parts) {
    const point = part.codePointAt(0);
    if (/^[\p{Mn}\p{Me}\p{Cf}]/u.test(part)) continue;
    if (part.includes('️') || /^\p{Emoji_Presentation}/u.test(part)
        || TABLE_WIDE.some(([low, high]) => point >= low && point <= high)) {
      width += 2;
    } else {
      width += 1;
    }
  }
  return width;
}

// --- a table, written out aligned -----------------------------------------

// The cells of every line of one table, as they are typed — escapes kept, so a
// `\|` is still one cell when it is written back.
function tableMatrix(lines, table) {
  const row = line => {
    const {text} = tableRow(line);
    return tableCells(text).map(cell => text.slice(cell.from, cell.to).trim());
  };
  return {
    head: row(lines[table.first]),
    aligns: table.aligns.slice(),
    body: lines.slice(table.first + 2, table.last).map(row),
  };
}

// The lines of a table: every column as wide as its widest cell and never
// narrower than `---`, one space inside every pipe, a pipe at both ends, each
// cell placed as its column's delimiter says. A short row is given empty cells
// up to the header's count, because the renderer draws them anyway; a long row
// keeps every cell it has, because a formatter never drops text — the renderer
// drops the extras, and that is for the writer to see and decide about.
function tableLines(matrix) {
  const count = matrix.head.length;
  const rows = matrix.body.map(cells =>
    cells.length >= count ? cells : cells.concat(Array(count - cells.length).fill('')));
  const widths = [];
  for (const cells of [matrix.head, ...rows]) {
    cells.forEach((cell, k) => { widths[k] = Math.max(widths[k] || 3, tableWidth(cell)); });
  }
  const placed = (cell, k) => {
    const gap = widths[k] - tableWidth(cell);
    const align = matrix.aligns[k] || '';
    if (align === 'right') return ' '.repeat(gap) + cell;
    if (align === 'center') {
      return ' '.repeat(Math.floor(gap / 2)) + cell + ' '.repeat(Math.ceil(gap / 2));
    }
    return cell + ' '.repeat(gap);
  };
  const line = cells => `| ${cells.map(placed).join(' | ')} |`;
  const rule = matrix.aligns.map((align, k) => {
    const width = widths[k];
    if (align === 'center') return ':' + '-'.repeat(width - 2) + ':';
    if (align === 'right') return '-'.repeat(width - 1) + ':';
    if (align === 'left') return ':' + '-'.repeat(width - 1);
    return '-'.repeat(width);
  });
  return [line(matrix.head), `| ${rule.join(' | ')} |`, ...rows.map(line)];
}

// Where in `lines` each line starts, in code units.
function tableLineStarts(lines) {
  const starts = [];
  let at = 0;
  for (const line of lines) { starts.push(at); at += line.length + 1; }
  return starts;
}

// One run per table that changes: the lines from the first that differs to the
// last that does, as `{from, to, put}` in code units over `text`. Lines that
// are already aligned are not in a run, so somebody typing on one of them is
// not written over.
function tableRun(lines, starts, first, now) {
  let a = 0;
  while (a < now.length && now[a] === lines[first + a]) a++;
  if (a === now.length) return null;
  let b = now.length - 1;
  while (b > a && now[b] === lines[first + b]) b--;
  return {
    from: starts[first + a],
    to: starts[first + b] + lines[first + b].length,
    put: now.slice(a, b + 1).join('\n'),
  };
}

// **A header made of dashes is left as typed.** `- | -` under a paragraph is a
// table's header, because a delimiter row may not open with `- `; written
// `| - | - |` it IS a delimiter row, and the paragraph line above it becomes the
// header of a table it was never part of. Found by fuzzing this against the
// renderer, and pinned in `test_aligning_twice_changes_nothing`. Such a header
// is a table nobody meant, so it is not worth a rule of its own to rescue.
function tableRewritable(now) {
  return delimiterOf(now[0]) === null;
}

function alignedRuns(text) {
  const lines = text.split('\n');
  const starts = tableLineStarts(lines);
  return topTables(lines)
    .map(table => {
      const now = tableLines(tableMatrix(lines, table));
      return tableRewritable(now) ? tableRun(lines, starts, table.first, now) : null;
    })
    .filter(Boolean);
}

function withRuns(text, runs) {
  let out = text;
  for (const run of [...runs].reverse()) out = out.slice(0, run.from) + run.put + out.slice(run.to);
  return out;
}

// Every top-level table in `text`, aligned. The same string, `===`, when there
// is nothing to align — a body with nothing to do gets no edit at all.
function alignTables(text) {
  const runs = alignedRuns(text);
  return runs.length ? withRuns(text, runs) : text;
}

// --- the caret, across an edit it did not make ----------------------------

// Which cell of a table line an offset into it is in, and how far into the
// cell's text. A caret on a pipe belongs to the cell before it, which is the
// one it has just finished typing.
function tableCellAt(line, at) {
  const {text, at: start} = tableRow(line);
  const cells = tableCells(text);
  if (!cells.length) return {column: 0, into: 0};
  const here = at - start;
  let column = cells.findIndex(cell => here <= cell.to);
  if (column === -1) column = cells.length - 1;
  const cell = cells[column];
  const raw = text.slice(cell.from, cell.to);
  const opens = cell.from + raw.length - raw.trimStart().length;
  return {column, into: Math.max(0, Math.min(here - opens, raw.trim().length))};
}

// And back: the offset, in a line this wrote, of `into` characters into the
// text of cell `column`. An empty cell puts the caret after the space inside
// its pipe, where typing starts.
function tableCellOffset(line, column, into) {
  const {text, at: start} = tableRow(line);
  const cells = tableCells(text);
  const cell = cells[Math.min(column, cells.length - 1)];
  if (!cell) return start;
  const raw = text.slice(cell.from, cell.to);
  const said = raw.trim();
  if (!said) return start + Math.min(cell.from + 1, cell.to);
  const opens = cell.from + raw.length - raw.trimStart().length;
  return start + opens + Math.min(into, said.length);
}

// Where offset `at` in `text` is once `runs` are applied. Before a run it does
// not move; after one it moves by the difference; inside one it stays in the
// same row, the same cell and the same place in that cell's text.
function caretThrough(text, runs, at) {
  let shift = 0;
  for (const run of runs) {
    if (at > run.to) { shift += run.put.length - (run.to - run.from); continue; }
    if (at < run.from) break;
    const before = text.slice(run.from, at).split('\n');
    const row = before.length - 1;
    const lineStart = at - before[row].length;
    const lineEnd = text.indexOf('\n', at);
    const was = text.slice(lineStart, lineEnd === -1 || lineEnd > run.to ? run.to : lineEnd);
    const {column, into} = tableCellAt(was, at - lineStart);
    const now = run.put.split('\n');
    const offset = now.slice(0, row).reduce((n, line) => n + line.length + 1, 0);
    return run.from + shift + offset + tableCellOffset(now[row], column, into);
  }
  return at + shift;
}

// The runs, written into a surface as edits a person made — one splice per
// table, from the last to the first so the offsets before each are still true —
// and the caret put back where it was in the text.
function spliceTables(surface, runs) {
  if (!runs.length) return;
  const text = surface.text();
  const {from, to} = surface.caret();
  const caret = [caretThrough(text, runs, from), caretThrough(text, runs, to)];
  for (const run of [...runs].reverse()) surface.splice(run.from, run.to, run.put);
  surface.setCaret(caret[0], caret[1]);
}

// --- the table the caret is in, and the Table button's four edits -----------

// The top-level table containing offset `at`: where its first line starts,
// where its last line ends, and the caret's row (0 is the header, 1 the
// delimiter) and column. `null` outside one.
function tableAt(text, at) {
  const lines = text.split('\n');
  const starts = tableLineStarts(lines);
  let line = starts.length - 1;
  while (line > 0 && starts[line] > at) line--;
  const table = topTables(lines).find(one => one.first <= line && line < one.last);
  if (!table) return null;
  return {
    start: starts[table.first],
    end: starts[table.last - 1] + lines[table.last - 1].length,
    row: line - table.first,
    column: tableCellAt(lines[line], at - starts[line]).column,
  };
}

// The four edits the Table button's menu offers, each on the caret's row or
// column, each answered with the table re-aligned so a new cell is already the
// right width. `{text, caret}`; `{refused}` with the sentence to say when the
// edit cannot be made here; `null` outside a table.
//
// The caret goes where the next thing is typed: into the new row or the new
// column, in the column or row the caret was in; after a deletion, into the row
// or column that took the deleted one's place, or the one before it at the end.
const TABLE_EDITS = {
  'row-below': {label: 'Add row below', said: 'A row is added below.'},
  'column-right': {label: 'Add column right', said: 'A column is added to the right.'},
  'delete-row': {label: 'Delete row', said: 'The row is deleted.'},
  'delete-column': {label: 'Delete column', said: 'The column is deleted.'},
};

function tableEdit(text, at, op) {
  const lines = text.split('\n');
  const starts = tableLineStarts(lines);
  const here = tableAt(text, at);
  if (!here) return null;
  const table = topTables(lines).find(one => starts[one.first] === here.start);
  const matrix = tableMatrix(lines, table);
  const count = matrix.head.length;
  matrix.body = matrix.body.map(cells =>
    cells.length >= count ? cells : cells.concat(Array(count - cells.length).fill('')));
  const column = Math.min(here.column, count - 1);
  let row = here.row;
  let to = here.column;
  if (op === 'row-below') {
    const below = Math.max(0, row - 1);
    matrix.body.splice(below, 0, Array(count).fill(''));
    row = below + 2;
  } else if (op === 'column-right') {
    matrix.head.splice(column + 1, 0, '');
    matrix.aligns.splice(column + 1, 0, '');
    for (const cells of matrix.body) cells.splice(column + 1, 0, '');
    to = column + 1;
  } else if (op === 'delete-row') {
    if (row < 2) return {refused: 'The header row is what makes this a table, so it stays.'};
    matrix.body.splice(row - 2, 1);
    if (row - 2 >= matrix.body.length) row = matrix.body.length ? row - 1 : 0;
  } else if (op === 'delete-column') {
    if (count === 1) return {refused: 'A table needs a column, so its last one stays.'};
    matrix.head.splice(column, 1);
    matrix.aligns.splice(column, 1);
    for (const cells of matrix.body) if (cells.length > column) cells.splice(column, 1);
    to = Math.min(column, count - 2);
  } else {
    return null;
  }
  const now = tableLines(matrix);
  if (!tableRewritable(now)) {
    return {refused: 'This table’s header is all dashes, so it is left as typed.'};
  }
  const put = now.join('\n');
  const offset = now.slice(0, row).reduce((n, line) => n + line.length + 1, 0);
  return {
    text: text.slice(0, here.start) + put + text.slice(here.end),
    caret: here.start + offset + tableCellOffset(now[row], to, 0),
    run: {from: here.start, to: here.end, put},
  };
}

// --- the page's half: the button, the menu, and the save -------------------

// One of the four, on whatever surface is mounted, as a person's edit: one
// splice over the table and nothing else, so it is one undo step and reaches a
// room as typing. Asked of the text and the caret as they are NOW, at the
// press, rather than when the menu opened — somebody in the room may have typed
// in between.
function editTable(surface, op) {
  const edit = tableEdit(surface.text(), surface.caret().from, op);
  if (!edit) {
    announce('The caret is not in a table any more, so nothing was changed.');
    return;
  }
  if (edit.refused) { announce(edit.refused); return; }
  surface.splice(edit.run.from, edit.run.to, edit.run.put);
  surface.setCaret(edit.caret);
  announce(TABLE_EDITS[op].said);
}

// The `▤` button, which is two buttons in one: outside a top-level table it
// inserts the starter table it always has, through `applyMark`; inside one it
// opens the menu of four. No shortcut — the comment on its `FORMATS` entry says
// why — so the keyboard path is the button itself: Tab to it, Enter, the arrows
// in the menu, Escape back.
//
// `menuUnder` binds the button's click to open and close its menu, and this
// binds it again, because here a press asks the caret first. mousedown and not
// click for the pointer, for the reason every mark on the bar is: a click comes
// after the box has lost the focus, and a press that moved the caret would be
// asking about the wrong place. A click with `detail === 0` is Enter or Space.
function attachTableButton(surface, button, mark) {
  const menu = menuUnder(button, 'tablemenu', 'Table', () =>
    Object.entries(TABLE_EDITS).map(([op, edit]) => ({
      text: edit.label,
      choose: () => editTable(surface, op),
    })));
  const press = () => {
    if (menu.shown()) { menu.close(); return; }
    if (tableAt(surface.text(), surface.caret().from)) menu.open();
    else applyMark(surface, mark);
  };
  button.onmousedown = event => { event.preventDefault(); press(); };
  button.onclick = event => { if (event.detail === 0) press(); };
}

// An explicit save — the Save button and Ctrl-S / ⌘S, which both call `save()`
// — aligns every top-level table first, when this person has not switched it
// off. Never the room's quiet commit: that is the server's, twenty seconds after
// the last keystroke, and realigning a table under somebody still typing in it
// is exactly what this must not do. Never the server either: a commit that
// rewrote the body would move text under co-editors' cursors and reformat files
// people edit in git.
//
// One splice per table that changes, over the lines that change, so a room
// hears a few lines of the table and not a new body: whoever is typing in the
// paragraph above keeps their place and their authorship. The focus goes back
// where it was — a splice is a person's edit and focuses the box, and pressing
// Save is not asking to be put back in the document.
function alignForSave(surface) {
  if (EDITOR.tables !== 'on') return;
  const runs = alignedRuns(surface.text());
  if (!runs.length) return;
  const was = document.activeElement;
  spliceTables(surface, runs);
  if (was && was !== document.activeElement && !surface.el.contains(was) && was.focus) {
    was.focus();
  }
}
</script>
""")
