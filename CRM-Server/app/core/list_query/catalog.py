from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.core.list_query.types import (
    DEFAULT_OPS,
    DateKind,
    DateSemantics,
    FieldType,
    FilterCondition,
    JoinSpec,
    ListQueryContext,
    SortCondition,
)

PredicateBuilder = Callable[[FilterCondition, "ListQueryField", ListQueryContext, Any], Any]
ValueResolver = Callable[[list[Any], ListQueryContext], list[Any]]
ExpressionBuilder = Callable[[ListQueryContext], Any]


@dataclass
class ListQueryField:
    key: str
    type: FieldType
    expression: Any = None
    sort_expression: Any = None
    allowed_ops: Sequence[str] | None = None
    date_semantics: DateSemantics = "day_bounds"
    date_kind: DateKind = "datetime"
    joins: Sequence[JoinSpec] = ()
    sort_joins: Sequence[JoinSpec] = ()
    blank_is_empty: bool | None = None
    enum_type: Any = None
    enum_persist: str = "name"
    resolve_values: ValueResolver | None = None
    resolve_person_aliases: bool = False
    neq_includes_null: bool = False
    predicate_builder: PredicateBuilder | None = None
    expression_builder: ExpressionBuilder | None = None
    sort_expression_builder: ExpressionBuilder | None = None

    def ops(self) -> frozenset[str]:
        if self.allowed_ops is not None:
            return frozenset(self.allowed_ops)
        return DEFAULT_OPS[self.type]

    def filter_expression(self, context: ListQueryContext | None = None) -> Any:
        if self.expression_builder is not None:
            return self.expression_builder(context or ListQueryContext())
        return self.expression

    def order_expression(self, context: ListQueryContext | None = None) -> Any:
        if self.sort_expression_builder is not None:
            return self.sort_expression_builder(context or ListQueryContext())
        if self.sort_expression is not None:
            return self.sort_expression
        return self.filter_expression(context)

    def treats_blank_as_empty(self) -> bool:
        if self.blank_is_empty is not None:
            return self.blank_is_empty
        return self.type == "text"

    def supports_filtering(self) -> bool:
        return self.predicate_builder is not None or self.expression is not None or self.expression_builder is not None

    def supports_sorting(self) -> bool:
        return (
            self.sort_expression is not None
            or self.sort_expression_builder is not None
            or self.expression is not None
            or self.expression_builder is not None
        )


@dataclass
class ListQueryCatalog:
    name: str
    fields: Sequence[ListQueryField]
    default_sorts: Sequence[SortCondition] = ()
    _index: dict[str, ListQueryField] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        index: dict[str, ListQueryField] = {}
        for item in self.fields:
            if item.key in index:
                raise ValueError(f"Duplicate list query field: {item.key}")
            index[item.key] = item
        object.__setattr__(self, "_index", index)

    def get(self, key: str) -> ListQueryField | None:
        return self._index.get(key)

    def require(self, key: str) -> ListQueryField:
        field = self.get(key)
        if field is None:
            raise KeyError(key)
        return field

    @property
    def keys(self) -> frozenset[str]:
        return frozenset(self._index)
