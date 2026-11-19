# Keyboard shortcuts

jcanton, 2026-11-19: *"how about adding keyboard shortcuts for the web app?"* — and, asked what it
was for: *"mostly navigation, plus a ? cheat sheet and all the shortcuts in the popup cards
describing buttons, and unifying those. focusing the search box, switching the editor views."*

## What was there before

Shortcuts existed, each written by the page that needed it, and nothing listed them:

| where              | keys                                                                | said where                      |
| ------------------ | ------------------------------------------------------------------- | ------------------------------- |
| record editor      | ⌘S / Ctrl+S save (Create on the create form)                        | nowhere                         |
| record editor      | Ctrl+Shift+1/2/3 write / split / preview                            | the toggle's `title`            |
| editor toolbar     | ⌘Z ⌘⇧Z ⌘B ⌘I ⌘⇧X ⌘2 ⌘E ⌘⇧E ⌘. ⌘8 ⌘7 ⌘⇧L ⌘K                           | each button's `title`, always ⌘ |
| deck, presenting   | arrows, Space, Enter, PgUp/PgDn, Backspace, Home/End, Escape        | nowhere                         |
| deck thumbnails    | Alt+↑/↓ reorders, Enter/Space opens                                 | nowhere                         |
| table cells        | arrows move, Enter/F2 edits, Enter on the id cell starts a move     | nowhere                         |
| date fields        | Alt+↓ opens the calendar                                            | nowhere                         |
| everywhere         | Escape closes the card, a menu, a popup, a draft, the selection     | nowhere                         |

The labels disagree with each other and with the keyboard. The toolbar says `⌘B` on Windows and
Linux, where the key that works is Ctrl. The view toggle uses a different notation. The Save
buttons mention nothing. Only the record editor answers ⌘S: the cycle page, the graph and the slide
editor each have a Save button the key does not reach.

**And three toolbar labels already lie in Ace**, which is the editor most people write in. Ace's own
commands run before the page's keydown listener and stop the event, and `editor.py` unbinds only
five of them. ⌘⇧E / Ctrl+Shift+E is Ace's `replaymacro`, ⌘⇧L / Ctrl+Shift+L its `expandtoline`, and
Ctrl+K on Windows and Linux its `findnext` — so "Code block", "Check list" and "Link" advertise keys
that do something else. (Read off the bindings in `static/ace.js`; confirm in Chrome before acting.)

Nothing moved between pages and nothing focused a search box.

## Approaches

The open question was how a navigation key is typed. Three were weighed:

1. **Two-key sequences, GitHub- and Gmail-style** — `g` then a letter. No modifier, so nothing to
   collide with a browser binding or with AltGr, and live only when focus is not in something that
   takes text. **Chosen**, by jcanton.
2. **Single letters.** One keystroke faster, and the one most often fired by accident when focus has
   quietly left a field — a stray `t` takes you off the page you were writing on.
3. **Modifier chords** (Ctrl+Shift+letter). Would work while typing, and the browsers have already
   taken most of them: the paragraph above `detail.py`'s view chord is the record of how few were
   left, and of the AltGr+E (€ on Swiss-German) that Ctrl+Alt ate.

The editor's view switch stays on **Ctrl+Shift+1/2/3**. jcanton's one requirement on it was that it
keeps working while typing, which a sequence cannot do, and the chord was already vetted against
AltGr and every browser's own bindings.

## Goals

- Move between the plan's views from the keyboard, anywhere.
- Focus the page's search box from the keyboard.
- `?` opens a sheet listing every shortcut that does something **on this page**.
- Every control that has a shortcut says so in its tooltip, in **one notation**, for **the reader's
  platform** — and the key it names works.

## Non-goals

- A command palette (⌘K). Not asked for, and ⌘K is the editor's Link.
- Remapping bindings. (Turning the single-key ones off is in; see *The off switch*.)
- Record-level verbs (`e` to edit, `j`/`k` through rows). Not asked for; the registry makes each one
  a line when somebody does ask.
- Moving widget-local key handling. The table's grid keys, the editor's Tab and list-continuing
  Enter, the splitter and rail grips, the deck's thumbnails: their handlers stay where they are.

## Anti-goals — what would make this a failure even if it works

- **A shortcut that fires while somebody is typing.** A `g` in a title field, in Ace with vim on,
  or in Excalidraw, that navigates away. Unsaved writing is the one thing git cannot give back.
- **A label that lies.** A tooltip, sheet line or `aria-keyshortcuts` naming a key that does not do
  that on this page, on this platform — including a key for a view `views` left out.
- **A new binding that eats a character somebody types.** No new binding may carry Alt.
- **Two lists.** A handler's key and its label declared in two places drift: that is how the
  toolbar came to say ⌘ on Windows.

## The design

### One registry

One Python table — a new `render/keys.py` — is the only place a shortcut's keys and words are
declared. Each entry: an id, the keys, the description (through `HUMAN` where a word already
exists), the sheet section, and where it is live. Everything reads from it:

- the handlers, which get the registry as JSON through a template variable (never by substitution —
  `test_no_page_is_assembled_by_substitution`);
- every control's tooltip suffix and `aria-keyshortcuts`, through a `data-keys="<id>"` attribute
  the shell fills in;
- the `?` sheet.

**What is in it:** the new sequences; Save; the view chord; the toolbar's `FORMATS` keys (all
thirteen, ⌘2 included); the deck's presenting keys; and the widget keys worth telling somebody about
— the table's Enter/F2, Enter-on-id and Escape, the deck thumbnails' Alt+↑/↓, the date field's
Alt+↓. Those widget entries are **labels only**: their handlers stay local and do not read the
registry for the match, so the registry holds their words and a test holds the words to the
handler. Arrows in a grid and Tab in an editor are what those controls do everywhere and are not
listed.

**The Alt rule is about new bindings.** Alt+↓ on date fields and Alt+↑/↓ on the deck thumbnails
predate this and are focused-widget keys, not page-wide ones. The registry names them as the two
exemptions, and the census fails on any third.

### Navigation: sequences

`g` arms a sequence for 1.5 s; the next key completes it or disarms it.

| keys  | goes to  | keys  | goes to      |
| ----- | -------- | ----- | ------------ |
| `g r` | Records  | `g c` | Cycles       |
| `g t` | Table    | `g p` | People       |
| `g g` | Graph    | `g i` | Issues       |
| `g l` | Timeline, `g t` if Table is not in the nav | `g n` | Notes |
| `g h` | Help     | `/`   | Focus search |
| `n`   | New      | `?`   | This sheet   |

**A letter goes to the first nav item that wants it.** Each item carries its preferred letters —
Timeline's are `t` then `l`, every other item has one — and the nav's own order hands them out,
each item taking its first letter nobody before it has. Table precedes Timeline, so with both drawn
Timeline is `g l`; a plan that leaves Table out of `views`, as `icon4py-plan` does, gets `g t` for
Timeline. jcanton, 2026-11-19: *"when table/ is disabled (e.g. for icon4py-plan) the t goes to
timeline instead of table?"* A key that moves between plans is acceptable because nobody has to
remember it: the badges and the sheet always draw the letter this plan gives, and a team works in
one deployment. The assignment is computed once, in Python, from `Links.nav`, so the handler, the
badges, the tooltips and the sheet cannot disagree about it.

**An armed `g` labels its targets**, as Vimium's `f` does — jcanton, mid-design: *"when starting a
sequence labels pop up? e.g. in firefox with the vim plugin if I type `f` I get cards with letters on
all things."* Pressing `g` draws a small badge with the second key on each nav link and on Help,
centred above the link on the accent ground — the spike's placement, which jcanton kept — and they go when the sequence completes, times out or meets Escape. The
badges are the same registry entries the sheet draws, so a link with no live sequence gets no badge.
They are `aria-hidden` — the announcement *Go to: r Records, t Table, …* through `announce` is the
reader's version of the same picture. On a phone the nav is folded and nobody is typing, so the
guard has already said no before a badge could be drawn.

**A sequence exists only where its link does.** The nav sequences are live exactly for the items
`Links.nav` draws, so a view the plan left out of `views` has no binding, no tooltip and no sheet
line. `g h` is the one that is not a nav item — Help is in the footer — and it follows `links.help`.

**`n` follows the page's own create control, and falls back to `links.new`.** On the records lists
it is the `Create …` link, so on `/issues` and `/notes` it carries the kind. On the Table it opens
the inline draft row, because that is the Table's own way to create. Elsewhere it goes to
`links.new`, and where that is empty — the static export — `n` does not exist.

**`/` focuses the page's search box** — `#q` on the views with the facet bar, `#betfind` on the cycle
page — and selects its text. A page with no search box does not list `/`. Its default is prevented,
which also keeps Firefox's quick-find off it.

**Matched on `event.key`, case-folded, which is deliberately the opposite of the view chord.** The
chord matches `event.code` because Shift changes a digit's `key` from layout to layout. Here the
reader means the letter printed on the key, and `?` is Shift+' on Swiss-German and Shift+/ on US,
both of which deliver `key === '?'`. Shift is ignored for letters (Caps Lock, a held Shift); any of
Ctrl, Alt or Meta means the key is not ours.

### The guard — when a bare key is not a shortcut

One function in the shell. The sequences, `n`, `/` and `?` answer only when **none** of these hold:

- focus is in an `input`, `textarea`, `select` or anything `contenteditable`, or inside an Ace
  editor (a hidden textarea, but name it);
- a drawing is open, a `<dialog>` is open, a right-click menu or popup is open, or a card is pinned;
- the deck is presenting — the deck owns the keyboard then;
- `event.isComposing` (an IME mid-character) or `event.repeat`;
- the single-key shortcuts are switched off (below).

**A page with unsaved changes refuses to be left by a key.** With focus on a chip, the status
control or the Save button, `g t` would leave the record page, and only the `pagehide` draft write
would catch it — silently, where storage is refused. So a navigation key on a dirty page does not
navigate; it announces *Save or reset first* through `announce`. A click on a link still goes
through whatever that page already does.

The chords (Save, the view chord, the toolbar) are not under this guard: working while typing is
what they are for.

### The off switch

WCAG 2.1.4 (level A): single-character shortcuts must be possible to turn off, because speech input
fires them by accident. jcanton chose a checkbox at the foot of the `?` sheet — *Single-key shortcuts*
— remembered per browser through `remembered`. Off means the sequences, `n` and `/` stop; `?` itself
stays, because it is how you get back to the checkbox. Chords are unaffected. Where the browser
refuses storage, the switch works for the page and is forgotten on the next one, and the sheet says
so.

### The sheet

A modal `<dialog>` in the shell, opened by `?` and by a `?` button **in the footer beside Help**
(jcanton's choice). The button is hidden on a coarse pointer — a phone has nobody typing keys — so
the phone footer and its `⋯` fold are untouched. Escape and the close button shut the sheet; focus
returns to where it was.

Sections, each drawn only if it has a live entry on this page: **Go to**, **On this page** (search,
new, the table's and thumbnails' widget keys), **Editor** (Save, the view chord, the toolbar),
**Presenting**. Keys in `<kbd>`, in the tooltips' notation. The Help page gets a short *Keyboard
shortcuts* section in `docs/` that points at `?` rather than copying the table, which would be a
second list.

### One notation, for the reader's platform

Decided once in the shell, from `navigator.userAgentData?.platform ?? navigator.platform`:

| reader on  | Save   | view chord   | Bold   | sequences |
| ---------- | ------ | ------------ | ------ | --------- |
| macOS, iOS | ⌘S     | ⌃⇧1          | ⌘B     | `g r`     |
| elsewhere  | Ctrl+S | Ctrl+Shift+1 | Ctrl+B | `g r`     |

A tooltip is the control's own words, two spaces, the keys — `Bold  Ctrl+B`, the shape the toolbar
already uses. Nav links get the same: `Graph  g g`. `aria-keyshortcuts` carries chords in ARIA's
spelling (`Control+S`, `Meta+S`); it has no form for a sequence, so nav links carry none and the
tooltip is their label.

### The toolbar's keys work in Ace

jcanton's choice: make the keys work rather than drop the labels. `editor.py` unbinds Ace's
`replaymacro` (⌘⇧E), `expandtoline` (⌘⇧L) and its Ctrl+K `findnext` on Windows and Linux, the way it
already unbinds five others — after confirming in Chrome that each one really does stop the event.
Find-next keeps Ace's F3 and Ctrl+G. With vim on, Ctrl+B and Ctrl+E are vim's on Windows and Linux,
and vim keeps them: somebody who switched vim on asked for vim's keys, and the tooltip says so for
that surface rather than naming a key that scrolls.

### Save answers ⌘S on every page with a Save button

The cycle page, the graph and the slide editor get ⌘S. Their handler clicks the page's own Save
button if it is visible and enabled, and does nothing otherwise — the shape vim's `:w` already uses
(`vimWritesThroughSave`), so there is never a second path to a save. The record editor's existing
handler keeps calling `save()` and keeps meaning Create on the create form, where the button's
tooltip says `Create  ⌘S`; the only change to it is that it matches `S` as well as `s`, so Caps Lock
stops disabling it.

## Constraints from the repository

- **No npm, no CDN.** Mousetrap and hotkeys-js were the candidates; a sequence matcher and a guard
  is less code than either's adapter, and neither knows about Ace or `Links`. Recorded in the
  commit, per *Look for it before you write it*.
- **Assume the browser refuses.** The off switch goes through `remembered`, and a refused store
  costs the setting, never the page.
- **The sheet is the first `<dialog>` in the app.** Named by its heading, `:focus-visible` on every
  control, a real `aria-label` on the `?` button.
- **Tested in the medium.** The handlers are driven through `tests/js/drive.js`: a `g` typed into an
  input, an Ace box, a contenteditable, with a drawing open, while presenting, on a dirty page, with
  the switch off — none navigates. A census holds the registry against the rendered pages: every
  `data-keys` id is in the registry, every sheet line has a live target on that page, no entry but
  the two named exemptions carries Alt, and a plan whose `views` leaves out Graph has no `g g`
  anywhere. The Ace unbinding is checked in a real browser, because the claim is about which
  listener sees the key first.

## Left to the builder

- Whether the page-wide handlers move into one dispatcher in the shell or keep their own listeners
  and ask the registry.
- The sequence timeout (1.5 s proposed; the badges make a longer one reasonable).
- The sheet's styling, within the tokens.
- Which `docs/` file carries the short section.

🤖 Written by an agent on behalf of @jcanton
