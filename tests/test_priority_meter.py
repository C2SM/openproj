"""The priority meter: five bars, always all of them, the rung's own number lit.

jcanton, 2026-11-24, replacing a block character per rung: "countable bars [...]
always be there, just colouring/filling the used ones a-la macos wifi icon". What
is asserted here is what that sentence asks for: every bar is drawn, exactly the
rung's level of them is lit, the browser draws the server's meter and not one of
its own, and lit and unlit are told apart by lightness on both themes.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pages import elements

from openproj.index import build_index
from openproj.model import load_repo
from openproj.render import (
    PRIORITIES,
    PRIORITY_BARS,
    PRIORITY_TEXT,
    ROUTES,
    priority_bars,
    render_table,
)
from openproj.render.shell import _page
from openproj.render.tokens import PRIORITY_LEVEL


def _bars(meter: str) -> list[str]:
    return [one.attrs.get("class", "") for one in elements(meter) if one.tag == "rect"]


@pytest.mark.parametrize("rung", PRIORITIES)
def test_every_rung_draws_every_bar_and_lights_its_own_number(rung: str):
    level = PRIORITY_LEVEL[rung]
    assert _bars(priority_bars(rung)) == ["lit"] * level + ["track"] * (len(PRIORITIES) - level)
    assert PRIORITY_TEXT[rung] == "▮" * level + "▯" * (len(PRIORITIES) - level)


def test_the_bars_rise_and_never_touch():
    """Counted, which needs a gap between every pair, and rising, which is what
    makes it read as a meter and not as a row of five equal ticks."""
    pairs = zip(PRIORITY_BARS, PRIORITY_BARS[1:], strict=False)
    for (x, _, width, height), (nx, _, _, taller) in pairs:
        assert nx > x + width, "two bars touch, so they cannot be counted"
        assert taller > height, "the meter does not rise"


@pytest.mark.parametrize("word", ["urgent", "", "None", 'high" onmouseover="x', "__proto__"])
def test_a_word_that_is_not_a_rung_draws_nothing(word: str):
    """`priority` holds whatever a hand-edited file holds, and a meter for a word
    that is not a rung would be a priority somebody then tries to change."""
    assert priority_bars(word) == ""


def test_the_table_draws_the_servers_meter_and_no_meter_of_its_own(seed_root: Path):
    """The rows are drawn in the browser. What the script hands `innerHTML` for a
    priority cell is `priority_bars` itself, picked by key out of the shell, so a
    row and a Jinja chip cannot draw two different meters."""
    from test_injection import run_js

    records, config, unreadable = load_repo(seed_root)
    index = build_index(records, config, date(2026, 8, 17), unreadable)
    held = {record.priority for record in index.records.values() if record.priority}
    assert len(held) >= 2, "the corpus holds one priority, so this proves little"

    answer = run_js(render_table(index, ROUTES), page=True)
    assert not answer["errors"], answer["errors"]
    written = "".join(str(one) for one in answer["written"])
    for rung in held:
        assert str(priority_bars(rung)) in written, f"no row drew the {rung} meter"
    for block in "▂▃▅▇█":
        assert block not in written, f"a row still draws the block character {block!r}"


# One chip per rung, then the fills each rect resolves to, through a canvas so
# that `color-mix()` and `oklab()` come back as sRGB bytes. On both themes, set
# the way the toggle sets them.
_FILLS = """
const bytes = colour => {
  const ctx = document.createElement('canvas').getContext('2d');
  ctx.fillStyle = colour; ctx.fillRect(0, 0, 1, 1);
  return [...ctx.getImageData(0, 0, 1, 1).data].slice(0, 3);
};
const out = {};
for (const theme of ['light', 'dark']) {
  document.documentElement.dataset.theme = theme;
  out[theme] = {
    ground: bytes(getComputedStyle(document.body).backgroundColor),
    rungs: [...document.querySelectorAll('.chip.pri')].map(chip => ({
      rung: chip.dataset.rung,
      lit: bytes(getComputedStyle(chip.querySelector('rect.lit')).fill),
      track: chip.querySelector('rect.track')
        ? bytes(getComputedStyle(chip.querySelector('rect.track')).fill) : null,
    })),
  };
}
return out;
"""


def _contrast(a: list[int], b: list[int]) -> float:
    def luminance(rgb: list[int]) -> float:
        linear = [c / 255 for c in rgb]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in linear]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_lit_and_unlit_bars_differ_in_lightness_on_both_themes(tmp_path: Path):
    """Lightness and not hue, because hue is the channel a dichromat loses. The
    track was `--line-strong` first, and against the light theme's green `low`
    rung that is 1.05:1, two bars nobody can tell apart; it was `--line` next,
    which on the dark page is 1.3:1 against the ground, so a very-low meter read
    as one bar and nothing. 1.5 fails both and passes what shipped."""
    from browser import chrome, measured_in

    content = "".join(
        f'<span class="chip pri pri-{rung}" data-rung="{rung}"><span class="chipmark">'
        f"{priority_bars(rung)}</span>{rung}</span> "
        for rung in PRIORITIES
    )
    got = measured_in(chrome(), _page("meter", content), tmp_path / "meter.html", 900, _FILLS)

    for theme, drawn in got.items():
        assert len(drawn["rungs"]) == len(PRIORITIES), drawn
        for one in drawn["rungs"]:
            if one["track"] is None:
                continue
            ratio = _contrast(one["lit"], one["track"])
            assert ratio >= 1.5, (
                f"{theme}: a lit {one['rung']} bar {one['lit']} is {ratio:.2f}:1 "
                f"against the track {one['track']}"
            )
            ground = _contrast(one["track"], drawn["ground"])
            assert ground >= 1.5, (
                f"{theme}: the track {one['track']} is {ground:.2f}:1 against the "
                f"page {drawn['ground']}, so the unlit bars are not there"
            )
