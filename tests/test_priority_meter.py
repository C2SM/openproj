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
    PRIORITY_METER_CHAR,
    ROUTES,
    priority_bars,
    render_detail,
    render_graph,
    render_table,
)
from openproj.render.shell import _page
from openproj.render.tokens import PRIORITY_LEVEL

# Every character the meter was ever written in as text: the rising blocks, and the
# filled and empty rectangles that briefly replaced them. None is in Inter, so each
# was drawn by whatever font the platform fell back to.
_BLOCKS = "\u2582\u2583\u2585\u2587\u2588\u25ae\u25af"


def _bars(meter: str) -> list[str]:
    return [one.attrs.get("class", "") for one in elements(meter) if one.tag == "rect"]


@pytest.mark.parametrize("rung", PRIORITIES)
def test_every_rung_draws_every_bar_and_lights_its_own_number(rung: str):
    level = PRIORITY_LEVEL[rung]
    assert _bars(priority_bars(rung)) == ["lit"] * level + ["track"] * (len(PRIORITIES) - level)
    assert f'data-rung="{rung}"' in priority_bars(rung), "the meter cannot colour itself"


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
    for block in _BLOCKS:
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


def test_a_priority_option_is_the_word_to_a_browser_without_base_select(seed_root: Path):
    """The record page's priority select is a customizable one, so each option holds
    the meter. A browser without `base-select` draws an option as its text alone:
    Firefox 160 keeps the SVG in the DOM and draws none of it, and an older parser
    drops the tags. Either way what is drawn is the text, and that has to be the
    word and only the word, never a block character and never nothing."""
    import re

    from openproj.render import HUMAN

    records, config, unreadable = load_repo(seed_root)
    index = build_index(records, config, date(2026, 8, 17), unreadable)
    record = next(one for one in index.records.values() if one.kind == "task")
    page = render_detail(index, ROUTES, only=record.id, base_commit="deadbee", may_write=True)

    (picker,) = re.findall(r'<select[^>]*class="field prisel".*?</select>', page, re.S)
    options = re.findall(r"<option[^>]*>(.*?)</option>", picker, re.S)
    assert len(options) == len(PRIORITIES), options
    for rung, inner in zip(PRIORITIES, options, strict=True):
        assert f'data-rung="{rung}"' in inner, f"the {rung} option has no meter"
        text = re.sub(r"<[^>]+>", "", inner).strip()
        assert text == HUMAN[rung], f"without base-select the {rung} option reads {text!r}"
    assert not any(block in page for block in _BLOCKS)


def test_the_meter_face_is_what_its_script_builds(tmp_path: Path):
    """`static/openproj-meter.ttf` is our own drawing and the script beside it is the
    source. Rebuilt here and compared byte for byte, so the shipped file, the
    geometry and the codepoints the graph writes cannot drift apart."""
    import sys

    from openproj.render import _static_dir

    pytest.importorskip("fontTools")
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    try:
        import meter_font
    finally:
        sys.path.pop(0)
    built = meter_font.build(tmp_path / "meter.ttf")
    assert built == (_static_dir() / "openproj-meter.ttf").read_bytes(), (
        "static/openproj-meter.ttf is not what tools/meter_font.py builds; rebuild it"
    )

    from fontTools.ttLib import TTFont

    drawn = set(TTFont(tmp_path / "meter.ttf").getBestCmap())
    assert drawn == {ord(char) for char in PRIORITY_METER_CHAR.values()}


# A box's name, measured in the stack the graph draws labels in, once the page has
# had time to load its faces: the meter character at 12px is the face's 1070-unit
# advance, and any fallback face measures something else.
_MEASURED = """
await document.fonts.ready;
const ctx = document.createElement('canvas').getContext('2d');
ctx.font = `600 12px "openproj meter", ${getComputedStyle(document.documentElement)
  .getPropertyValue('--font-sans')}`;
return {
  loaded: document.fonts.check('12px "openproj meter"', '\\ue003'),
  width: ctx.measureText('\\ue003').width,
};
"""


def test_a_box_name_is_measured_in_the_meter_face(seed_root: Path, tmp_path: Path):
    """A label measured before its face loads is drawn at the wrong width, and on the
    graph that is a box's name sitting off its box."""
    from browser import chrome, measured_in

    records, config, unreadable = load_repo(seed_root)
    index = build_index(records, config, date(2026, 8, 17), unreadable)
    got = measured_in(
        chrome(), render_graph(index, ROUTES), tmp_path / "graph.html", 1400, _MEASURED
    )
    assert got["loaded"], "the meter face never loaded on the graph"
    assert abs(got["width"] - 12 * 1070 / 1000) < 0.1, got


def test_a_closed_priority_select_lights_its_rung_where_base_select_is_missing():
    """A browser without `base-select` (Firefox 160 measured, Safari) draws an option
    as its text, so the closed control's meter is the select's own background:
    one gradient per bar, coloured per rung. Chrome cannot be made to lack the
    feature, so this is asked of the rules rather than of the pixels; the pixels
    were looked at in headless Firefox."""
    import re

    from openproj.render.shell import _priority_select_css
    from openproj.render.tokens import PRIORITY_LEVEL

    css = _priority_select_css()
    assert css.startswith("@supports not (appearance: base-select) {"), (
        "the fallback is not gated, so Chrome would draw the meter twice"
    )
    for rung, level in PRIORITY_LEVEL.items():
        (rule,) = re.findall(rf'select\.prisel\[data-rung="{rung}"\] {{([^}}]*)}}', css)
        lit = re.findall(r"--pb\d: var\(--pri-(?!track)[a-z-]+\);", rule)
        track = re.findall(r"--pb\d: var\(--pri-track\);", rule)
        assert (len(lit), len(track)) == (level, len(PRIORITIES) - level), rule
    # Bottoms level: each bar is pushed down by half of what it is short of the
    # tallest, from a centred box, so offset + height is one number for all five.
    positions = re.findall(r"top calc\(50% \+ ([\d.]+)px\)", css)
    bottoms = {float(off) * 2 + h for off, (*_, h) in zip(positions, PRIORITY_BARS, strict=True)}
    assert len(bottoms) == 1, bottoms


def test_every_priority_select_says_its_rung(seed_root: Path):
    """`data-rung` is what draws the fallback meter, so a select drawn without it,
    or with one that disagrees with what it shows, draws a wrong closed control."""
    import re

    from openproj.render import render_cycle

    records, config, unreadable = load_repo(seed_root)
    index = build_index(records, config, date(2026, 8, 17), unreadable)
    task = next(one for one in index.records.values() if one.kind == "task" and one.priority)
    pages = {
        "record": render_detail(index, ROUTES, only=task.id, base_commit="deadbee", may_write=True),
        "cycle": render_cycle(index, 37, ROUTES, base_commit="deadbee"),
    }
    for name, page in pages.items():
        selects = re.findall(r"<select[^>]*\bprisel\b[^>]*>.*?</select>", page, re.S)
        assert selects, f"the {name} page draws no priority select"
        for one in selects:
            said = re.search(r'data-rung="([^"]*)"', one)
            chosen = re.search(r'<option value="([^"]*)"\s*selected', one)
            assert said and chosen and said.group(1) == chosen.group(1), (name, one[:200])


def test_a_picked_priority_moves_the_rung_the_closed_control_draws(seed_root: Path):
    """The shell's one `change` listener keeps `data-rung` on the select, for every
    priority select on every page, the ones built in the browser included."""
    from test_injection import run_js

    records, config, unreadable = load_repo(seed_root)
    index = build_index(records, config, date(2026, 8, 17), unreadable)
    task = next(one for one in index.records.values() if one.kind == "task" and one.priority)
    page = render_detail(index, ROUTES, only=task.id, base_commit="deadbee", may_write=True)
    answer = run_js(
        page,
        "(() => { const s = document.querySelector('select.prisel');"
        " const other = s.value === 'low' ? 'high' : 'low'; s.value = other;"
        " s.dispatchEvent(new Event('change', {bubbles: true}));"
        " return {value: s.value, rung: s.dataset.rung}; })()",
        page=True,
    )
    assert not [e for e in answer["errors"] if e.startswith("expression:")], answer["errors"]
    got = answer["value"]
    assert got["rung"] == got["value"], got
