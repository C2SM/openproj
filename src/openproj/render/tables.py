"""Markdown tables in a body: found the way `_MD` finds them, and aligned on save."""

from __future__ import annotations

from markupsafe import Markup

# --- where this is, and where it is not -------------------------------------
#
# A block of its own and not a part of `_COMBOBOX`, on the argument `_ACE_SURFACE`
# makes in `editor.py`: `_COMBOBOX` is emitted on the table and the cycle page as
# well, and neither has a body to hold a table. So this goes out with the toolbar
# that can reach it — on every page that draws `#marks`, which is the record page,
# the create form and the slide editor, when they are editable.
# `test_every_page_with_a_toolbar_carries_the_table_button` holds that list to the
# pages. Nothing here runs at load: `FORMATS`'s Table entry and `save()` call into
# it when they are pressed, so its place among the page's scripts does not matter.
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

// The whitespace Python's `str.strip()` strips, which is what markdown-it-py
// trims a row and a cell with. Not JavaScript's `trim()`: that one also strips
// U+FEFF and leaves U+001C-U+001F and U+0085, so a byte-order mark before a row
// made a table of what the renderer draws as a paragraph.
const TABLE_HEAD_WS = /^[\t-\r\x1c-\x20\x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+/;
const TABLE_TAIL_WS = /[\t-\r\x1c-\x20\x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/;

function stripStart(text) { return text.replace(TABLE_HEAD_WS, ''); }
function stripped(text) { return stripStart(text).replace(TABLE_TAIL_WS, ''); }

// The text as lines, each with where it starts and the line ending after it.
// markdown-it reads `\r\n` and a lone `\r` as `\n`, and so does this: a body
// pasted from Windows into a surface that kept its endings is the same document
// to both, and an edit written back uses the endings the table already had.
function tableModel(text) {
  const lines = [];
  const starts = [];
  const breaks = [];
  const ending = /\r\n|\r|\n/g;
  let from = 0;
  for (let found; (found = ending.exec(text));) {
    lines.push(text.slice(from, found.index));
    starts.push(from);
    breaks.push(found[0]);
    from = found.index + found[0].length;
  }
  lines.push(text.slice(from));
  starts.push(from);
  breaks.push('');
  return {lines, starts, breaks};
}

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

// `context` is whose terminator this is asked for, because markdown-it's list
// rule answers differently inside a paragraph: there an empty item, or an
// ordered one not numbered 1, cannot interrupt.
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
  return {text: stripped(lead.rest), at: lead.at + lead.rest.length - stripStart(lead.rest).length};
}

// Where the text of one cell starts in its row, and the text itself.
function cellSpan(text, cell) {
  const raw = text.slice(cell.from, cell.to);
  return {opens: cell.from + raw.length - stripStart(raw).length, said: stripped(raw)};
}

// The alignments a delimiter row says, one per column, or `null` when the line
// is not one. Asked of the second line of a table — and of the first line this
// writes, see `tableRewritable`.
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
    const piece = stripped(pieces[k]);
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
  const text = stripped(head.rest);
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

// Indented code runs over blank lines and ends after its last indented line.
function codeEnd(lines, i) {
  let j = i + 1;
  let last = j;
  while (j < lines.length) {
    const lead = tableLead(lines[j]);
    if (lead.blank) { j++; continue; }
    if (lead.col < 4) break;
    last = ++j;
  }
  return last;
}

// `$$` opens display maths (`dollarmath_plugin`) that runs to the next line
// ending in `$$`, blank lines and all: `_MD` leaves `allow_blank_lines` at its
// default, which is on. `$$` that never closes is not maths, and the line is
// read as the rest of this scan would read it.
function mathEnd(lines, i) {
  const first = stripped(tableLead(lines[i]).rest);
  if (first.length > 3 && first.endsWith('$$')) return i + 1;
  for (let j = i + 1; j < lines.length; j++) {
    if (stripped(tableLead(lines[j]).rest).endsWith('$$')) return j + 1;
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
// is no HTML block.
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
    if (lead.col >= 4) { i = codeEnd(lines, i); continue; }
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
  let width = 0;
  for (const one of TABLE_SEGMENTER ? TABLE_SEGMENTER.segment(text) : text) {
    const part = typeof one === 'string' ? one : one.segment;
    const point = part.codePointAt(0);
    if (/^[\p{Mn}\p{Me}\p{Cf}]/u.test(part)) continue;
    if (part.includes('\ufe0f') || /^\p{Emoji_Presentation}/u.test(part)
        || TABLE_WIDE.some(([low, high]) => point >= low && point <= high)) {
      width += 2;
    } else {
      width += 1;
    }
  }
  return width;
}

// --- a table, written out aligned -----------------------------------------

// A short row is given empty cells up to the header's count, because the
// renderer draws them anyway; a long row keeps every cell it has, because a
// formatter never drops text — the renderer drops the extras, and that is for
// the writer to see and decide about.
function padded(cells, count) {
  return cells.length >= count ? cells : cells.concat(Array(count - cells.length).fill(''));
}

// The cells of every line of one table, as they are typed — escapes kept, so a
// `\|` is still one cell when it is written back — and every row padded.
function tableMatrix(lines, table) {
  const row = line => {
    const {text} = tableRow(line);
    return tableCells(text).map(cell => cellSpan(text, cell).said);
  };
  const head = row(lines[table.first]);
  return {
    head,
    aligns: table.aligns.slice(),
    body: lines.slice(table.first + 2, table.last).map(line => padded(row(line), head.length)),
  };
}

// The lines of a table: every column as wide as its widest cell and never
// narrower than `---`, one space inside every pipe, a pipe at both ends, each
// cell placed as its column's delimiter says.
function tableLines(matrix) {
  const rows = [matrix.head, ...matrix.body];
  const measured = rows.map(cells => cells.map(tableWidth));
  const widths = [];
  for (const row of measured) {
    row.forEach((width, k) => { widths[k] = Math.max(widths[k] || 3, width); });
  }
  const line = (cells, r) => {
    const placed = cells.map((cell, k) => {
      const gap = widths[k] - measured[r][k];
      const align = matrix.aligns[k] || '';
      if (align === 'right') return ' '.repeat(gap) + cell;
      if (align === 'center') {
        return ' '.repeat(Math.floor(gap / 2)) + cell + ' '.repeat(Math.ceil(gap / 2));
      }
      return cell + ' '.repeat(gap);
    });
    return `| ${placed.join(' | ')} |`;
  };
  const rule = matrix.aligns.map((align, k) => {
    const width = widths[k];
    if (align === 'center') return ':' + '-'.repeat(width - 2) + ':';
    if (align === 'right') return '-'.repeat(width - 1) + ':';
    if (align === 'left') return ':' + '-'.repeat(width - 1);
    return '-'.repeat(width);
  });
  const written = rows.map(line);
  return [written[0], `| ${rule.join(' | ')} |`, ...written.slice(1)];
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

// One run per table that changes: the lines from the first that differs to the
// last that does, as `{from, to, put}` in code units, with the line the run
// starts on, the lines it writes and what it joins them with. Lines that are
// already aligned are not in a run, so somebody typing on one of them is not
// written over.
function tableRun(model, table, now) {
  const {lines, starts} = model;
  const first = table.first;
  let a = 0;
  while (a < now.length && now[a] === lines[first + a]) a++;
  if (a === now.length) return null;
  let b = now.length - 1;
  while (b > a && now[b] === lines[first + b]) b--;
  const join = model.breaks[first] || '\n';
  return {
    from: starts[first + a],
    to: starts[first + b] + lines[first + b].length,
    first: first + a,
    lines: now.slice(a, b + 1),
    join,
    put: now.slice(a, b + 1).join(join),
  };
}

function alignedRuns(model) {
  return topTables(model.lines)
    .map(table => {
      const now = tableLines(tableMatrix(model.lines, table));
      return tableRewritable(now) ? tableRun(model, table, now) : null;
    })
    .filter(Boolean);
}

// --- the caret, across an edit it did not make ----------------------------

// Where a caret is in a table line: in which cell and how far into its text, or
// outside the cells altogether — before the opening pipe or after the closing
// one — which is `edge`. A caret on a pipe belongs to the cell before it, which
// is the one it has just finished typing; a caret after the closing pipe stays
// after it, or "type a row, save, Enter" splits the row it was typing.
function tableCellAt(line, at) {
  const {text, at: start} = tableRow(line);
  const cells = tableCells(text);
  const here = at - start;
  if (!cells.length) return {column: 0, into: 0, edge: here > 0 ? 'end' : 'start'};
  const last = cells[cells.length - 1];
  if (here < 0 || here < cells[0].from) return {column: 0, into: 0, edge: 'start'};
  if (here > last.to || here > text.length) return {column: cells.length - 1, into: 0, edge: 'end'};
  const column = cells.findIndex(cell => here <= cell.to);
  const {opens, said} = cellSpan(text, cells[column]);
  return {column, into: Math.max(0, Math.min(here - opens, said.length)), edge: null};
}

// And back: the offset in a line this wrote of a place `tableCellAt` answered.
// An empty cell puts the caret after the space inside its pipe, where typing
// starts.
function tableCellOffset(line, place) {
  if (place.edge === 'start') return 0;
  if (place.edge === 'end') return line.length;
  const {text, at: start} = tableRow(line);
  const cells = tableCells(text);
  const cell = cells[Math.min(place.column, cells.length - 1)];
  if (!cell) return start;
  const {opens, said} = cellSpan(text, cell);
  if (!said) return start + Math.min(cell.from + 1, cell.to);
  return start + opens + Math.min(place.into, said.length);
}

function tableLineOf(model, at) {
  let line = model.starts.length - 1;
  while (line > 0 && model.starts[line] > at) line--;
  return line;
}

// Where offset `at` is once `runs` are applied. Before a run it does not move;
// after one it moves by the difference; inside one it stays in the same row,
// the same cell and the same place in that cell's text.
function caretThrough(model, runs, at) {
  let shift = 0;
  for (const run of runs) {
    if (at > run.to) { shift += run.put.length - (run.to - run.from); continue; }
    if (at < run.from) break;
    const line = tableLineOf(model, at);
    const row = line - run.first;
    const offset = run.lines.slice(0, row).reduce((n, one) => n + one.length + run.join.length, 0);
    const place = tableCellAt(model.lines[line], at - model.starts[line]);
    return run.from + shift + offset + tableCellOffset(run.lines[row], place);
  }
  return at + shift;
}

// Every top-level table on a surface, aligned as an edit a person made — one
// splice per table, from the last to the first so the offsets before each are
// still true — and the caret put back where it was in the text. Whether there
// was anything to align, because a body with nothing to do gets no edit at all.
function alignSurface(surface) {
  const model = tableModel(surface.text());
  const runs = alignedRuns(model);
  if (!runs.length) return false;
  const {from, to} = surface.caret();
  const caret = [caretThrough(model, runs, from), caretThrough(model, runs, to)];
  for (const run of [...runs].reverse()) surface.splice(run.from, run.to, run.put);
  surface.setCaret(caret[0], caret[1]);
  return true;
}

// --- the table the caret is in, and the Table button's four edits -----------

// The top-level table containing offset `at`, or `null` outside one: where its
// first line starts and its last line ends, the caret's row (0 is the header, 1
// the delimiter) and column, and the scan it was found in, so an edit made from
// it does not scan the body again.
function tableAt(text, at) {
  const model = tableModel(text);
  const line = tableLineOf(model, at);
  const table = topTables(model.lines).find(one => one.first <= line && line < one.last);
  if (!table) return null;
  return {
    model,
    table,
    start: model.starts[table.first],
    end: model.starts[table.last - 1] + model.lines[table.last - 1].length,
    row: line - table.first,
    column: tableCellAt(model.lines[line], at - model.starts[line]).column,
  };
}

// The four edits the Table button's menu offers, each on the caret's row or
// column, each answered with the table re-aligned so a new cell is already the
// right width: `{run, caret}`, or `{refused}` with the sentence to say when the
// edit cannot be made here.
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

function tableEdit(here, op) {
  const {model, table} = here;
  const matrix = tableMatrix(model.lines, table);
  const count = matrix.head.length;
  const column = here.column;
  let row = here.row;
  let to = column;
  // A long row's extra cell is in no column the page draws, so there is no
  // column there to add beside or take away.
  if (column >= count && (op === 'column-right' || op === 'delete-column')) {
    return {refused: 'The caret is past the last column of this table, so there is no '
                     + 'column here to change.'};
  }
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
    for (const cells of matrix.body) cells.splice(column, 1);
    to = Math.min(column, count - 2);
  }
  const now = tableLines(matrix);
  if (!tableRewritable(now)) {
    return {refused: 'This table’s header is all dashes, so it is left as typed.'};
  }
  const join = model.breaks[table.first] || '\n';
  const offset = now.slice(0, row).reduce((n, line) => n + line.length + join.length, 0);
  return {
    run: {from: here.start, to: here.end, put: now.join(join)},
    caret: here.start + offset + tableCellOffset(now[row], {column: to, into: 0, edge: null}),
  };
}

// --- the page's half: the button, the menu, and the save -------------------

// One of the four, on whatever surface is mounted, as a person's edit: one
// splice over the table and nothing else, so it is one undo step and reaches a
// room as typing. Asked of the text and the caret as they are NOW, at the
// press, rather than when the menu opened — somebody in the room may have typed
// in between.
function editTable(surface, op) {
  const here = tableAt(surface.text(), surface.caret().from);
  if (!here) {
    announce('The caret is not in a table any more, so nothing was changed.');
    return;
  }
  const edit = tableEdit(here, op);
  if (edit.refused) { announce(edit.refused); return; }
  surface.splice(edit.run.from, edit.run.to, edit.run.put);
  surface.setCaret(edit.caret);
  announce(TABLE_EDITS[op].said);
}

// The `▤` button, which is two buttons in one: outside a top-level table it
// inserts the starter table it always has, through `applyMark`; inside one it
// opens the menu of four. Answers what a press does, and `attachEditing` binds
// it the way it binds every mark. No shortcut — the comment on its `FORMATS`
// entry says why — so the keyboard path is the button itself: Tab to it, Enter,
// the arrows in the menu, Escape back.
function tablePress(surface, button, mark) {
  const menu = menuUnder(button, 'tablemenu', 'Table', () =>
    Object.entries(TABLE_EDITS).map(([op, edit]) => ({
      text: edit.label,
      choose: () => editTable(surface, op),
    })));
  return () => {
    if (menu.shown()) { menu.close(); return; }
    if (tableAt(surface.text(), surface.caret().from)) menu.open();
    else applyMark(surface, mark);
  };
}

// An explicit save — the Save button and Ctrl-S / ⌘S, while an edit is open —
// aligns every top-level table first, when this person has not switched it off.
// Never the room's quiet commit: that is the server's, twenty seconds after the
// last keystroke, and realigning a table under somebody still typing in it is
// exactly what this must not do. Never the server either: a commit that
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
  const was = document.activeElement;
  if (!alignSurface(surface)) return;
  if (was && was !== document.activeElement && !surface.el.contains(was) && was.focus) {
    was.focus();
  }
}
</script>
""")
