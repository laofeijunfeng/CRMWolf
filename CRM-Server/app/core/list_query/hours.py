from __future__ import annotations

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import FunctionElement
from sqlalchemy.types import Integer


class HoursBetween(FunctionElement):
    """Dialect-portable whole hours from start to end."""

    type = Integer()
    inherit_cache = True
    name = "hours_between"


@compiles(HoursBetween, "mysql")
def _mysql_hours_between(element, compiler, **kw):
    start, end = list(element.clauses)
    return "TIMESTAMPDIFF(HOUR, %s, %s)" % (compiler.process(start, **kw), compiler.process(end, **kw))


@compiles(HoursBetween, "sqlite")
def _sqlite_hours_between(element, compiler, **kw):
    start, end = list(element.clauses)
    return "CAST((julianday(%s) - julianday(%s)) * 24 AS INTEGER)" % (
        compiler.process(end, **kw),
        compiler.process(start, **kw),
    )


def hours_between(start, end) -> HoursBetween:
    return HoursBetween(start, end)
