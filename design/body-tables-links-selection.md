# Tables, record cards, a record from a selection, done without a PR, forge references

Asked for on 2026-11-27 and 2026-11-28, five features, decided in one conversation and built as
five pull requests in this order:

1. **Tables are aligned on save**, and the Table button edits the table the caret is in.
2. **Every record has a card, and a link to one in a body opens it.**
3. **Selected text becomes a new record**: right-click a selection in the editor, create a record
   titled from it, and the selection becomes a link to that record.
4. **A record may be done without a pull request**, on purpose and on the record.
5. **A pull request URL is drawn as `owner/repo#N`** for a Forgejo repository as it is for GitHub.

4 and 5 are small and independent of the first three; they may go first. What follows is what was
decided, why, and what was left to whoever builds it.

## 1. Tables aligned on save

### What it is for

A markdown table typed by hand is ragged: the pipes do not line up, and a table you cannot read as
source is a table nobody edits. The ask is that a save leaves every table in the body aligned.

### Decided

- **When.** On an explicit save: the Save button and Ctrl-S / ⌘S. Not on the room's 20-second idle
  commit, which would realign a table under somebody still typing in it.
- **Where.** In the browser, inside the editor, as an ordinary edit — so it reaches the room as a
  splice like any other keystroke and every member sees it. **Never on the server and never at
  commit.** A server that rewrote the body at commit would move text under co-editors' cursors
  through `absorb`, and would reformat files people edit in git, which is what the round-tripping
  `patch_text` exists to prevent. A file edited only in git is left as it is until somebody saves
  it in the app.
- **A preference.** "Format tables on save", per person, beside the draft interval, on by default,
  stored through `remembered` like every other editor preference.
- **Both editors.** Ace and the textarea, through the surface adapter the toolbar marks use.
- **Top-level tables only.** A table inside a blockquote or a list item is left exactly as typed:
  aligning it means parsing and preserving `> ` and list-indent prefixes, nested, which is a much
  larger formatter for a case shaping documents rarely have.
- **What aligned means.**
  - Every column padded to its widest cell, one space inside each pipe, leading and trailing pipes
    on every row.
  - Cells padded according to the delimiter row: `:--` left, `:-:` centre, `--:` right, `---`
    left. The delimiter row's dashes fill the column width and keep their colons.
  - Width is display width: an emoji or a CJK character counts two columns, a combining mark zero.
    Measured per grapheme (`Intl.Segmenter`), not per UTF-16 unit — this repository has already
    shipped one defect from counting the wrong unit.
  - **Cells split exactly where markdown-it splits them**: on every `|` not preceded by a
    backslash, *including* one inside backticks. That is GFM's rule and markdown-it-py's
    `escapedSplit`, and the formatter follows the renderer rather than a reader's intuition —
    otherwise *Add column* acts on columns the rendered table does not have. (Proposed the other
    way in the conversation and reversed after the builder check read the parser.)
  - A row with fewer cells than the header gets empty cells. A row with more keeps them: the
    formatter never drops text.
  - Tables inside fenced or indented code are not tables and are not touched.
- **A body with nothing to align** gets no edit at all, and saves byte-for-byte as typed.

### The Table button

The `▤` button already exists in `FORMATS` (`controls.py`), between Drawings and Horizontal rule,
and today only inserts a starter table. It becomes two buttons in one:

- **Caret outside a top-level table:** inserts the starter table it inserts now.
- **Caret inside one:** opens a small menu under the button — *Add row below*, *Add column
  right*, *Delete row*, *Delete column* — each acting on the caret's row or column and then
  re-aligning that table at once, so a new cell is already the right width.

No shortcuts: the comment above the button says every letter the page could spare is spoken for.
The keyboard path is the button itself — Tab to it, Enter, arrows.

### Approaches

- **A. The formatter in the browser — chosen.** One JavaScript formatter finds the tables in the
  editor's text and aligns them; the same code serves the save and the button's menu. Instant, no
  round trip, both surfaces. Its risk is disagreeing with markdown-it — the *two readers walk the
  same tree* failure in `AGENTS.md`. So a test holds the two together over a corpus of awkward
  bodies, on **two** things: the line ranges the formatter calls top-level tables equal the
  `token.map` of markdown-it's top-level `table_open` tokens, and each table's cells split the same
  way (cell count per row, cell text) as markdown-it's `td`/`th` tokens. Nested tables are in the
  corpus too, and the assertion there is that the formatter leaves them byte-for-byte alone.
- **B. The server finds and aligns.** Cannot disagree with the renderer. Refused: every save waits
  on a round trip, a keystroke during it makes the answer stale so that save has to skip
  formatting, and each click in the button's menu becomes a request.
- **Libraries.** `markdown-table` (wooorm) lays out a matrix you have already parsed, and parsing
  is the work. prettier and mdformat reformat the whole document, which is the opposite of what a
  save here may do. Neither was taken.

## 2. Every record has a card

### Decided

- **The card is a preview of a record, any record.** It does not ask whether the record is
  scheduled. It draws the fields that record's kind has — dates and size for a planned kind, none
  for an issue or a note — and its body.
- **One builder for what a card draws.** Today the card draws the table's row view model
  (`rows.py`'s `_row`), which reads `index.plan[record_id]` and so raises for an issue or a note.
  The card's data moves out into one preview built for any record in `index.records`, used by every
  card host — table, graph, timeline, body links — so there is one card and not one per view.
- **`carded` goes.** It was on the ladder (`model.py`) because a hover over a product on the graph
  opened a card while the pointer was only crossing it on the way to another node. The graph has
  opened its card on a click since 2026-10-12, so the reason is gone, and products, issues and
  notes get the card like everything else. Delete the field and every reader of it (`CARDED` in
  `graph.py` and the rest).
- **A link in a body to a record** — what `_link` (`markdown.py`) already turns into
  `links.record + id` — opens the card on hover, after the same `CARD_DELAY`, as the table's rows
  do. The right-click menu kills it, it does not follow the pointer, and a click still follows the
  link.
- **Where:** the record page, in the reading view and in the split view's preview pane. Not inside
  the card's own body (no card in a card), not on the deck, not in the static export.
- **A link to a record the plan has not got** opens no card and stays a broken link, as `_link`'s
  docstring already decided.
- **Where the data comes from:** `/api/body/<id>`, which the card already asks for, also returns
  the preview's fields. The record page does not embed them: the preview pane's links change as
  somebody types, and a page-time list would be wrong by the first keystroke.

## 3. A record from a selection

### What it is for

Writing a pitch, you name a piece of work that deserves its own record. Today that is: open a new
tab, create the record, copy its id, come back, write the link. The ask is one gesture from the
words already on the page.

### Decided

- **In the editor only**, while an edit is open — Ace or the textarea. Not in the reading view: a
  selection there is rendered text, and `bold word` selected out of `**bold** word`, or a selection
  ending inside a link, has no exact source range to wrap. In the editor the selection *is* the
  source.
- **The gesture.** Right-click on a selection that **existed before the press** opens this app's
  menu (`pop.py`) in place of the browser's. "Before the press" because on macOS a right-click on a
  word in a textarea selects that word before `contextmenu` fires, so reading the selection then
  would take the browser's menu — and its spelling suggestions — away from nearly every right-click.
  Capture it on `pointerdown` on both surfaces. Shift-right-click still gives the browser's menu,
  and with no prior selection right-click is the browser's, untouched. The ContextMenu key and
  Shift+F10 open the same menu and are the keyboard path; no new chord is registered.
- **The menu holds one item and nothing else.** "New record from selection ▸ \<kind>", listing only
  the kinds `Config.allows`. Not the record menu the other hosts get (`Status ▸`, `Edit…`,
  `Delete…`, `Open`…): on this page those would be a second write path to the record whose own form
  is open, and `Delete…` would delete the document under the editor. So `popItems` needs a host
  that supplies its own items in place of the standard ones.
- **Choosing a kind opens the menu's existing form face** with:
  - the title filled from the selection, with markdown markers stripped and whitespace collapsed,
    and editable;
  - the parent defaulting to the record being edited when that kind may be its child
    (`CHILD_KINDS` / `PARENT_KINDS`), and — unlike `New child ▸` — **not locked**: it may be changed
    or cleared;
  - no dependency added in either direction;
  - an empty body.
- **Refused, with the reason on the greyed item:** a selection spanning more than one paragraph, one
  that already contains a link, and one that cuts across a link's boundary.
- **What a save of the form does.** Creates the record at once, in its own commit, through
  `popCreate`. Then the selection is replaced by `[<selection exactly as typed>](<new id>)` as an
  ordinary edit in the open session, committed with it.
- **If the selected text changed while the form was open** — somebody in the room edited or
  deleted it — the record is still created, the link is not written, and the page says so with the
  id: "Created pitch-000123. The text you selected changed, so it wasn't linked." The selection is
  tracked through other people's edits: an Ace anchor on that surface, and on the textarea the
  offset arithmetic its seat bands already do through the room's splices.
- **After it lands** the editor keeps focus, nothing navigates, and the receipt — "Created
  pitch-000123 and linked it." — goes to the live region as well as the screen.
- **Cancelling the session afterwards** discards the link and keeps the record. A record nothing
  points to is harmless and is in the table; holding the create until the session saves would mean
  writing a link to an id the server has not handed out.

### Approach

One sensible way: the record page becomes a fourth host of the menu (`popServes`), registered only
while a session is open, with the editor as what it is about rather than a row, and supplying its
own items. That puts `pop.py`'s script on the record page — measure the bytes and write the number
in the commit — and the form face, `popCreate` and its refusal reading come with it. The record
page's `base_commit` input needs the `id="base"` that `popStart` reads and the create advances. A
second, smaller menu for this one item was not taken: it would be a second box with its own
placement, dismissal and keyboard, which is what `context-menus.md` argues against.

## 4. Done without a pull request

### What it is for

Some work is finished with nothing merged — a decision, an investigation, a task done outside any
repository. Today `validate_all` refuses `done` with an empty `prs:` ("a done record needs at least
one PR"), so such a record can never be closed.

### Decided

- **A stored waiver, `prs_waived: true`**, beside `status: done` — the same shape as
  `review_waived`, which already lets work start without a reviewer. The done rule accepts a
  waiver, so `openproj check`, the server and every page agree, and git shows the record was closed
  without a PR on purpose. Turning the rule into a warning was refused: every such record would
  carry a warning for ever, and "closed on purpose" would look the same as "forgot the PR".
- **A confirmation at every door that sets a status** — the hill, the table's status cell,
  `Status ▸` in the right-click menu, the record page: "No pull request is linked. Mark done
  anyway?", with **Mark done without a PR** and **Cancel**. Confirming writes `status: done` and
  `prs_waived: true` in one write. Without the waiver the server goes on refusing as now.
- **It is visible.** Where the record's PRs are drawn — the record page's facts, the table's PRs
  cell, the card and the slide — a waived record reads "Done without a PR" rather than nothing.
- **A PR added later** leaves the waiver where it is; it does no harm.
- **No schema bump**: the waiver only relaxes a rule, so nothing written before it is newly
  invalid.

## 5. Forge references

### What it is for

On plan-d, `prs:` holds `https://git.ciccia.synology.me/jacopo/strc-site/pulls/1` and is drawn as
that URL, where a GitHub pull request is drawn as `owner/repo#N`.

### What was found

The prs box already rewrote a pasted link to `owner/repo#N` (`asReference`, `controls.py`) — a
github.com URL by its shape, and a listed repository's against its page — but only a paste into the
box, and only from then on. plan-d's two entries were stored as URLs some other way, and nothing
reads a stored entry back, so they were drawn as written.

Separately, measured on 2026-11-28: the served plan-d's footer said "2 repositories not read", both
"the server could not reach its host to ask which forge it is". On the NAS, `git.ciccia.synology.me`
resolved to the public address and the connection never completed; asked through the NAS's own
reverse proxy (`--resolve …:443:127.0.0.1`) Forgejo answered 403, which `forge_of` counts as
Forgejo. That was a deployment fix — an `extra_hosts` entry in plan-d's `compose.yaml`, made by
jcanton the same day — and not this code's; it is what lets `owner/repo#N` LINK there, which is a
different question from how a URL is drawn.

### Decided

- **Drawn short, stored as written.** Wherever a PR reference is drawn — the facts, the table's PRs
  cell, the card, the slide, and prose in a body — a URL to `<a listed repository>/pulls/N` (or
  `/pull/N`, or `/issues/N`), or to a github.com pull request or issue, is drawn as `owner/repo#N`
  and links to the URL as written. Decided by the URL's shape against `repositories:`, so it needs
  no answer from the forge and covers entries already stored. No file is rewritten.
- One rule in Python beside `pr_href`, and the page script reading the same data the way
  `pr_bases` is shared now — not a second spelling of the rule in JavaScript.

## Left to the builder

- The formatter's module boundary, and whether it lives beside `FORMATS` or in a block of its own
  emitted only where an editor is (`_ACE_SURFACE`'s reasoning in `editor.py` about bytes on pages
  with no editor applies).
- The wide-character table: a compact range check is enough; its source goes in the comment.
- The formatter test corpus, which must include at least: a table in a fence, in a blockquote, in a
  list item, beside an HTML block, with `\|`, with a pipe in a code span, with an emoji splitting a
  column, and a line of pipes that is not a table.
- Where the caret lands after the Table menu adds or deletes a row or column.
- The shape of the record preview the card draws, and the module it lives in.
- How the form is told the title and the unlocked parent: a new spec shape beside `new` in
  `popForm`, or `new` with the lock made optional.
- How each status door asks the done-without-a-PR question: one shared confirmation, or each
  door's own; either way one sentence, written once.

🤖 Written by an agent on behalf of @jcanton
