"""What a record's card draws, for any record: the one builder every card host reads.

The card used to draw the table's row (`rows.py`'s `_row`), which reads
`index.plan[record_id]` and so raised for an issue or a note, and a link to one
in a body could therefore open nothing. The preview is built from
`index.records`, and the table's row is this preview plus the table's own
columns, so the table, the graph, the timeline and a link in a body draw one card
and not one per view.
"""

from __future__ import annotations

from functools import cache

from ..index import Index, _title_of
from ..model import KINDS, RUNG, Record, size_weeks, unread_fields
from .tokens import card_facts


@cache
def fact_names(kind: str) -> tuple[str, ...]:
    """The fields a card of this kind lists, by name: `card_facts`, asked once.

    Cached because `card_facts` asks `_editable_for` over a blank record of every
    kind, and the table builds a row for every planned record on every render.
    Its answer is a fact about the code, not about a plan.
    """
    return tuple(fact["name"] for fact in card_facts()[kind]["facts"])


# Every field a card of any planned kind lists. The table's row carries all of
# them on every row, filled or not, because the table's columns and its gate read
# them by key whatever the kind: a product row says `owner: null`, which is how
# the table knows to draw nothing there.
PLANNED_FACTS: tuple[str, ...] = tuple(
    dict.fromkeys(name for rung in KINDS if rung.planned for name in fact_names(rung.name))
)

# The fields that hold other records' ids, which the card draws by title.
_NAMING = ("parent", "pitched_into", "became")


def _iso(day) -> str | None:
    return day.isoformat() if day else None


def card_fields(index: Index, record: Record, names: tuple[str, ...]) -> dict:
    """The keys the card draws `names` from, for this record.

    Most fields are drawn as the file holds them, under their own name. Four are
    not, and each is drawn from what the card actually shows:

    - `person_weeks` is `size`, the appetite somebody stated (`size_weeks`).
    - `start_date` and `end_date` are `start` and `end`, the date the scheduler
      gave this record, falling back to the stated date where it gave none.
      That is the table's own bargain in its Start and End columns, because a
      cell that edits a field must show what the field holds. The stated date
      travels too, under its own name, because the table's gate asks whether
      the file holds one.
    - `depends_on` is `blocked_by`, the count of unfinished blockers.
    - `parent` is the parent where the plan can draw it, and `off_plan_parent`
      where the stored field holds one it cannot. A boolean and never the id,
      because the exclusion sweep forbids an inbox id in a plan page's bytes.

    A field the kind does not read is None, through `unread_fields`, the same
    list the validator and the editors use.
    """
    unread = unread_fields(record.kind)

    def read(name, value):
        return None if name in unread else value

    span = index.spans.get(record.id)
    fields: dict = {}
    for name in names:
        if name == "person_weeks":
            fields["size"] = read(name, size_weeks(record))
        elif name in ("start_date", "end_date"):
            column = name.removesuffix("_date")
            stated = getattr(record, name)
            drawn = getattr(span, column) if span else read(name, stated)
            fields[column] = _iso(drawn)
            fields[name] = _iso(stated)
        elif name == "depends_on":
            # Looked up in `records`, never `plan`: `blocked_by` is total over
            # records, so a planned task whose hand-written `depends_on` names an
            # unplanned record keeps that edge, and the plan-only lookup was a
            # KeyError that 500ed /table over one hand-edited file. `done` and
            # `shelved` stop counting: one is finished and the other is parked.
            fields["blocked_by"] = read(
                name,
                sum(
                    1
                    for blocker in index.blocked_by.get(record.id, [])
                    if index.records[blocker].status not in ("done", "shelved")
                ),
            )
        elif name == "parent":
            fields["parent"] = record.parent if record.parent in index.plan else None
            fields["off_plan_parent"] = bool(record.parent) and record.parent not in index.plan
        else:
            fields[name] = read(name, getattr(record, name, None))
    return fields


def card_head(index: Index, record: Record) -> dict:
    """What every card draws above and below its list, for any kind: the title,
    the chips and the progress meter.

    Status is the record's state, which for an issue or a note is derived from
    what it was pitched into or became, as the record page draws it; for a plan
    record it is the written status. A ladder the kind does not read is None, so a
    product draws no status and no priority chip.
    """
    # The model defaults `status` to `shaping` and `priority` to `medium` for
    # every record, so a product, which has neither, arrived at the table as a
    # shaping, medium-priority record and was drawn with both chips.
    # `unread_fields` is the same list the validator reports from and the editors
    # decline to offer.
    unread = unread_fields(record.kind)
    counted = index.progress.get(record.id)
    # Counted only for a rung that is work: "42% done" beside a codebase is a
    # sentence about the plan wearing the name of the thing it is filed under.
    works = RUNG[record.kind].schedules
    return {
        "id": record.id,
        "title": record.title,
        "kind": record.kind,
        "status": None if "status" in unread else record.state(index.records),
        "priority": None if "priority" in unread else record.priority,
        "progress": round(counted.fraction, 4) if counted and works else None,
        "progress_text": counted.text if counted and works else "",
    }


def card_preview(index: Index, record_id: str) -> dict:
    """What the card draws for one record, of any kind.

    The fields that kind's card lists (`card_facts`) and nothing else: a pitch
    carries dates and a size, an issue and a note carry neither key at all, so a
    card cannot draw a dash for a field the kind does not have.

    `titles` names the records the fields point at. A plan view's own payload
    already names every plan record, which is why the table's row leaves it out;
    a link in a body is drawn on a page that names none of them.
    """
    record = index.records[record_id]
    preview = card_head(index, record) | card_fields(index, record, fact_names(record.kind))
    titles: dict[str, str] = {}
    for name in _NAMING:
        value = preview.get(name)
        for other in value if isinstance(value, list) else [value]:
            if other in index.records:
                titles[other] = _title_of(index.records, other) or other
    preview["titles"] = titles
    return preview
