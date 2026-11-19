"""Every keyboard shortcut, declared once, and the ones one page's `Links` make live."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Literal

from .tokens import _NAV

if TYPE_CHECKING:
    from .shell import Links

Section = Literal["go", "page", "editor", "presenting"]


@dataclass(frozen=True)
class Key:
    """One shortcut: what it does, where the sheet lists it, and the keys that do it.

    `keys` are alternatives. A space separates the keys of a sequence (`"g t"`); a `+`
    joins a chord, whose last token is matched against `event.key` with case folded,
    or against `event.code` when it is `Digit<n>` (Shift changes a digit's `key` from
    layout to layout). `Mod` is ⌘ on Apple and Ctrl elsewhere, `Ctrl` is Control
    everywhere.

    `anywhere` entries are live whenever a page's JSON carries them; the rest only
    where an element says `data-keys~="<id>"`. `own` entries are implemented by a
    page's own handler, and the registry is their words and keys.
    """

    id: str
    words: str
    section: Section
    keys: tuple[str, ...]
    anywhere: bool = False
    own: bool = False
    # Vim's own key on Windows and Linux, so the tooltip and the sheet drop it there
    vim: bool = False


def _toolbar(id: str, words: str, chord: str, vim: bool = False) -> Key:
    return Key(id, words, "editor", (chord,), own=True, vim=vim)


KEYS: tuple[Key, ...] = (
    # Live only where the page draws its own create control, which it does only
    # for somebody who may write: a reader is offered no key whose answer is a 403
    Key("new", "Create a record", "page", ("n",)),
    Key("search", "Search", "page", ("/",)),
    Key("sheet", "Keyboard shortcuts", "page", ("?",), anywhere=True),
    Key("save", "Save", "editor", ("Mod+s",), own=True),
    Key("view-write", "Write", "editor", ("Ctrl+Shift+Digit1",), own=True),
    Key("view-both", "Write and preview", "editor", ("Ctrl+Shift+Digit2",), own=True),
    Key("view-preview", "Preview", "editor", ("Ctrl+Shift+Digit3",), own=True),
    _toolbar("undo", "Undo", "Mod+z"),
    _toolbar("redo", "Redo", "Mod+Shift+z"),
    _toolbar("bold", "Bold", "Mod+b", vim=True),
    _toolbar("italic", "Italic", "Mod+i"),
    _toolbar("strike", "Strikethrough", "Mod+Shift+x"),
    _toolbar("heading", "Heading", "Mod+2"),
    _toolbar("code", "Code", "Mod+e", vim=True),
    _toolbar("fence", "Code block", "Mod+Shift+e"),
    _toolbar("quote", "Quote", "Mod+."),
    _toolbar("bullets", "Bullet list", "Mod+8"),
    _toolbar("numbers", "Numbered list", "Mod+7"),
    _toolbar("checklist", "Check list", "Mod+Shift+l"),
    _toolbar("link", "Link", "Mod+k"),
    Key("cell-edit", "Edit the cell", "page", ("Enter", "F2"), own=True),
    Key("row-move", "On the id cell, start moving the row", "page", ("Enter",), own=True),
    Key("escape", "Put down a selection, a draft row or a move", "page", ("Escape",), own=True),
    Key(
        "slide-next",
        "Next slide",
        "presenting",
        ("ArrowRight", "PageDown", "Space", "Enter"),
        own=True,
    ),
    Key(
        "slide-prev", "Previous slide", "presenting", ("ArrowLeft", "PageUp", "Backspace"), own=True
    ),
    Key("slide-first", "First slide", "presenting", ("Home",), own=True),
    Key("slide-last", "Last slide", "presenting", ("End",), own=True),
    Key("present-leave", "Stop presenting", "presenting", ("Escape",), own=True),
    Key("thumb-up", "Move the slide up", "page", ("Alt+ArrowUp",), own=True),
    Key("thumb-down", "Move the slide down", "page", ("Alt+ArrowDown",), own=True),
    Key("thumb-open", "Open the slide", "page", ("Enter", "Space"), own=True),
    Key("calendar", "Open the calendar", "page", ("Alt+ArrowDown",), own=True),
)

# Focused-widget keys that predate the rule that no binding carries Alt (AltGr is
# Ctrl+Alt on Windows, and AltGr+E is the euro sign on Swiss-German)
ALT_EXEMPT = frozenset({"calendar", "thumb-up", "thumb-down"})

# Timeline takes `t` when no Table is drawn before it
_LETTERS = {
    "records": "r",
    "table": "t",
    "graph": "g",
    "timeline": "tl",
    "cycles": "c",
    "people": "p",
    "issues": "i",
    "notes": "n",
}


def go_letters(nav: Sequence[str]) -> dict[str, str]:
    """Give each drawn nav item its first free letter, asking in `_NAV` order."""
    taken: dict[str, str] = {}
    for item, _ in _NAV:
        if item not in nav:
            continue
        free = next((one for one in _LETTERS[item] if one not in taken.values()), None)
        if free:
            taken[item] = free
    return taken


def keys_for(links: Links) -> list[dict]:
    """The shortcuts one page can have, resolved against its links, as JSON for the shell."""
    words = dict(_NAV)
    go = [
        Key(f"go-{item}", words[item], "go", (f"g {letter}",), anywhere=True)
        for item, letter in go_letters(links.nav).items()
    ]
    go.append(Key("go-help", "Help", "go", ("g h",), anywhere=True))
    page = [key for key in KEYS if key.id != "new" or links.new]
    return [{**asdict(key), "keys": list(key.keys)} for key in (*go, *page)]
