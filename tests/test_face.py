"""A plan's name and colour: the tab title, the favicon and the start of the nav.

jcanton, 2026-11-24, with two plans open side by side and every tab of both
reading `openproj — table`. `name` and `colour` in `config/defaults.yaml` are
resolved the way `views` and `kinds` are, so a value that cannot be used costs
that setting and is said, and never takes the file around it down.
"""

from __future__ import annotations

import inspect
from datetime import date
from pathlib import Path
from urllib.parse import unquote

import pytest
from pages import elements

from openproj import render
from openproj.index import Index, build_index
from openproj.model import _MISSING, load_repo, plan_colour, read_config, resolve_face

ORANGE = "#e08a1e"


@pytest.mark.parametrize(
    ("written", "drawn"),
    [
        ("#e08a1e", ORANGE),
        ("E08A1E", ORANGE),
        ("#e81", "#ee8811"),
        ("rgb(224, 138, 30)", ORANGE),
        ("RGB(224,138,30)", ORANGE),
        ("rgb(256, 0, 0)", None),
        ("orange", None),
        ("#e08a1", None),
        ("#e08a1e; background: url(x)", None),
        ("", None),
    ],
)
def test_a_colour_is_one_of_the_spellings_a_picker_gives_and_nothing_else(written, drawn):
    """An allowlist, because the value is written into an SVG attribute and a
    stylesheet. The last two are the reason it is one."""
    assert plan_colour(written) == drawn


def test_a_plan_that_sets_neither_is_unnamed_and_says_nothing():
    assert resolve_face(_MISSING, _MISSING, "config/defaults.yaml", "config/defaults.yaml") == (
        "",
        "",
        [],
    )


@pytest.mark.parametrize(
    ("name", "colour", "got", "fields"),
    [
        ("  icon4py  ", "#27899e", ("icon4py", "#27899e"), []),
        (2026, _MISSING, ("2026", ""), []),
        (["a", "b"], _MISSING, ("", ""), ["name"]),
        ("", _MISSING, ("", ""), ["name"]),
        # An unquoted `colour: #e08a1e` is a YAML comment, so the key reads as empty.
        (_MISSING, None, ("", ""), ["colour"]),
        (_MISSING, "teal", ("", ""), ["colour"]),
        (_MISSING, 27899, ("", ""), ["colour"]),
    ],
)
def test_what_cannot_be_used_is_one_unusable_naming_the_setting(name, colour, got, fields):
    *answer, unusable = resolve_face(name, colour, "config/defaults.yaml", "config/defaults.yaml")
    assert tuple(answer) == got
    assert [one.field for one in unusable] == fields
    assert all(one.path == "config/defaults.yaml" for one in unusable)


def test_a_long_name_is_cut_and_said():
    name, _, unusable = resolve_face("x" * 200, _MISSING, "config/defaults.yaml", "")
    assert len(name) <= 60
    assert [one.field for one in unusable] == ["name"]


def test_an_unquoted_colour_costs_the_colour_and_not_the_file():
    """`#` opens a YAML comment, so the most natural way to write a colour is the
    one way that reads as nothing. The file's other settings must still hold, and
    the sentence must say how to write it."""
    text = "name: plan-d\ncolour: #e08a1e\ncooldown_weeks: 3\n"
    config, refused = read_config(["config/defaults.yaml"], lambda _: text)
    assert refused == []
    assert (config.name, config.colour, config.cooldown_weeks) == ("plan-d", "", 3)
    (said,) = config._unusable
    assert said.field == "colour" and "quotes" in said.why


def test_a_name_that_is_not_text_costs_the_name_and_not_the_file():
    """Validated by pydantic with the rest, `name: [a, b]` would have dropped
    `defaults.yaml` whole, `views` and `cooldown_weeks` with it."""
    text = "name: [a, b]\ncolour: '#e08a1e'\ncooldown_weeks: 3\nviews: [table]\n"
    config, refused = read_config(["config/defaults.yaml"], lambda _: text)
    assert refused == []
    assert (config.name, config.colour, config.cooldown_weeks) == ("", ORANGE, 3)
    assert config.views == ("table",)
    assert [one.field for one in config._unusable] == ["name"]


@pytest.fixture
def named(seed_root: Path) -> Index:
    records, config, unreadable = load_repo(seed_root)
    index = build_index(records, config, date(2026, 8, 17), unreadable)
    return index.model_copy(update={"name": "kiln & co", "colour": ORANGE})


def _drawn(index: Index):
    """Every page the renderer can draw, found in its namespace rather than listed,
    for `test_every_page_the_renderer_can_draw_carries_the_banner`'s reason: the
    page that forgets `face=` is the one a list written here would not have."""
    for name, entry in sorted(vars(render).items()):
        if not name.startswith("render_") or name == "render_static":
            continue
        wanted = inspect.signature(entry).parameters
        arguments = {"index": index} if "index" in wanted else {}
        if "kind" in wanted:
            arguments |= {"kind": "task", "base_commit": "deadbee"}
        if "number" in wanted:
            arguments |= {"number": 37}
        if "record_id" in wanted:
            arguments |= {"record_id": next(iter(index.records))}
        yield name, entry(**arguments)


def test_every_page_is_titled_page_first_and_wears_the_plans_mark(named: Index):
    """`Table · kiln & co`, a favicon in the plan's colour, and the mark and name at
    the start of the nav, on every page. Parsed, so the `&` is checked as the text
    a tab shows and not as whatever the escaping made of it."""
    seen = 0
    for name, page in _drawn(named):
        found = elements(page)
        # The first `<title>`, the document's, in `<head>`: an SVG drawing on the
        # page carries `<title>`s of its own.
        title = next(el.text for el in found if el.tag == "title")
        assert title.endswith(" · kiln & co") and not title.startswith("openproj"), (name, title)
        (icon,) = [el.attrs["href"] for el in found if el.attrs.get("rel") == "icon"]
        assert f"fill='{ORANGE}'" in unquote(icon), (name, icon[:80])
        (mark,) = [el for el in found if el.attrs.get("class") == "planname"]
        assert mark.text == "kiln & co", (name, mark.text)
        seen += 1
    assert seen >= 10, f"only {seen} pages were drawn, so this stopped watching most of them"


def test_an_unnamed_plan_is_still_named_openproj(seed_root: Path):
    records, config, unreadable = load_repo(seed_root)
    index = build_index(records, config, date(2026, 8, 17), unreadable)
    page = render.render_table(index, render.ROUTES)
    title = next(el.text for el in elements(page) if el.tag == "title")
    assert title == "Table · openproj"


def test_a_served_record_page_is_titled_with_the_record(named: Index):
    record = next(r for r in named.records.values() if r.title)
    page = render.render_detail(named, render.ROUTES, only=record.id)
    title = next(el.text for el in elements(page) if el.tag == "title")
    assert title == f"{record.title} · kiln & co"


def test_the_exports_record_page_retitles_itself_as_the_hash_moves(named: Index):
    """One file holds every record and shows the one the hash names, so the title
    the shell wrote is the list's, and the script has to say which record."""
    from test_injection import run_js

    record = next(r for r in named.records.values() if r.title)
    page = render.render_detail(named, render.STATIC)
    answer = run_js(page, "document.title", page=True, here=f"/detail.html#{record.id}")
    assert not answer["errors"], answer["errors"]
    assert answer["value"] == f"{record.title} · kiln & co"
    listed = run_js(page, "document.title", page=True, here="/detail.html")
    assert not listed["errors"], listed["errors"]
    assert listed["value"] == "Records · kiln & co"


@pytest.mark.parametrize("directory", ["plan-d", "my: plan #1", "'quoted'"])
def test_a_new_plan_is_named_after_its_directory(directory: str):
    """`openproj init` writes the name quoted, so a directory called `my: plan #1`
    is a name and not a mapping with a comment after it."""
    from openproj.bootstrap import Options, plan_files

    text = plan_files(directory, Options())["config/defaults.yaml"]
    config, refused = read_config(["config/defaults.yaml"], lambda _: text)
    assert refused == [] and config._unusable == []
    assert (config.name, config.colour) == (directory, "")
