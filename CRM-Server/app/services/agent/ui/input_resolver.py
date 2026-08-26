"""Resolve server-signed Agent UI interaction values into Workflow input."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from datetime import date, datetime

from pydantic import JsonValue, ValidationError

from app.services.agent.ui.schemas import InteractionField
from app.services.agent.workflow import WorkflowResumeInput


class AgentUIInputResolutionError(ValueError):
    """Submitted values do not match the server-signed interaction contract."""


class InteractionInputResolver:
    """Validate one signed interaction and produce canonical Workflow resume input."""

    def resolve_interaction_values(
        self,
        target: Mapping[str, JsonValue],
        values: Mapping[str, JsonValue],
    ) -> WorkflowResumeInput:
        metadata = self._interaction_context(target)
        interaction_type = target.get("interaction_type")
        if interaction_type == "choice":
            content, choice_metadata = self._resolve_choice(target, values)
            metadata.update(choice_metadata)
            return WorkflowResumeInput(
                kind="text",
                content=content,
                source="web",
                metadata=metadata,
            )
        if interaction_type == "confirmation":
            decision = self._resolve_confirmation(target, values)
            if decision == "confirm":
                return WorkflowResumeInput(
                    kind="confirm",
                    content="确认",
                    source="web",
                    metadata=metadata,
                )
            return WorkflowResumeInput(
                kind="reject",
                content="取消",
                source="web",
                metadata=metadata,
            )
        if interaction_type == "form":
            form_values = self._validated_form_values(target, values)
            metadata["form_values"] = form_values
            return WorkflowResumeInput(
                kind="text",
                content=json.dumps(form_values, ensure_ascii=False, sort_keys=True),
                source="web",
                metadata=metadata,
            )

        if interaction_type != "text_input":
            raise AgentUIInputResolutionError("interaction has an unsupported signed type")
        submitted_text = self._validated_text_value(target, values)
        return WorkflowResumeInput(
            kind="text",
            content=submitted_text,
            source="web",
            metadata=metadata,
        )

    @staticmethod
    def _interaction_context(target: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
        context: dict[str, JsonValue] = {}
        for key in (
            "business_action",
            "interaction_id",
            "task_id",
            "task_key",
            "payload",
            "action",
            "resume_action",
            "turn_relation",
            "selected_task_id",
        ):
            if key in target:
                context[key] = target[key]

        payload = target.get("payload")
        if isinstance(payload, Mapping):
            for key in (
                "case_public_id",
                "follow_up_confirmation_case_public_id",
                "review_case_id",
            ):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    context[key] = value
        return context

    @staticmethod
    def _resolve_confirmation(
        target: Mapping[str, JsonValue],
        values: Mapping[str, JsonValue],
    ) -> str:
        if target.get("selection_mode") != "single":
            raise AgentUIInputResolutionError("confirmation interaction must require one decision")
        raw_choices = target.get("choices")
        if not isinstance(raw_choices, list) or len(raw_choices) != 2:
            raise AgentUIInputResolutionError("confirmation interaction must sign confirm and cancel")
        choices_by_value: dict[str, Mapping[str, JsonValue]] = {}
        for raw_choice in raw_choices:
            if not isinstance(raw_choice, Mapping):
                raise AgentUIInputResolutionError("server confirmation choice is invalid")
            choice_value = raw_choice.get("value")
            if choice_value not in {"confirm", "cancel"} or not isinstance(choice_value, str):
                raise AgentUIInputResolutionError("server confirmation choice is invalid")
            if choice_value in choices_by_value:
                raise AgentUIInputResolutionError("server confirmation choices must be unique")
            choices_by_value[choice_value] = raw_choice
        if set(choices_by_value) != {"confirm", "cancel"}:
            raise AgentUIInputResolutionError("confirmation interaction must sign confirm and cancel")
        if "choices" in values:
            raise AgentUIInputResolutionError("confirmation submission requires one choice")
        submitted = values.get("choice")
        if not isinstance(submitted, str) or submitted not in choices_by_value:
            raise AgentUIInputResolutionError("submitted confirmation is not server-authorized")
        if choices_by_value[submitted].get("disabled") is True:
            raise AgentUIInputResolutionError("submitted confirmation is disabled")
        return submitted

    @staticmethod
    def _resolve_choice(
        target: Mapping[str, JsonValue],
        values: Mapping[str, JsonValue],
    ) -> tuple[str, dict[str, JsonValue]]:
        selection_mode = target.get("selection_mode")
        min_selections = target.get("min_selections")
        max_selections = target.get("max_selections")
        if selection_mode not in {"single", "multiple"}:
            raise AgentUIInputResolutionError("choice interaction has no signed selection mode")
        if type(min_selections) is not int or type(max_selections) is not int:
            raise AgentUIInputResolutionError("choice interaction has no signed selection bounds")
        if min_selections < 0 or max_selections < 1 or min_selections > max_selections:
            raise AgentUIInputResolutionError("choice interaction has invalid signed selection bounds")
        if selection_mode == "single" and (min_selections != 1 or max_selections != 1):
            raise AgentUIInputResolutionError("single choice interaction must require exactly one selection")

        raw_choices = target.get("choices")
        if not isinstance(raw_choices, list) or not raw_choices:
            raise AgentUIInputResolutionError("choice interaction is missing server choices")
        choices_by_value: dict[str, Mapping[str, JsonValue]] = {}
        for raw_choice in raw_choices:
            if not isinstance(raw_choice, Mapping):
                raise AgentUIInputResolutionError("server choice is invalid")
            choice_value = raw_choice.get("value")
            if not isinstance(choice_value, str) or not choice_value:
                raise AgentUIInputResolutionError("server choice value is invalid")
            if choice_value in choices_by_value:
                raise AgentUIInputResolutionError("server choice values must be unique")
            choices_by_value[choice_value] = raw_choice
        if max_selections > len(choices_by_value):
            raise AgentUIInputResolutionError("choice bounds exceed server choices")

        selected_values: list[str]
        if selection_mode == "single":
            if "choices" in values:
                raise AgentUIInputResolutionError("single choice submission must use choice")
            submitted = values.get("choice")
            if not isinstance(submitted, str) or not submitted:
                raise AgentUIInputResolutionError("single choice submission requires one choice")
            selected_values = [submitted]
        else:
            if "choice" in values:
                raise AgentUIInputResolutionError("multiple choice submission must use choices")
            submitted = values.get("choices")
            if not isinstance(submitted, list):
                raise AgentUIInputResolutionError("multiple choice submission requires a string array")
            selected_values = []
            for item in submitted:
                if not isinstance(item, str) or not item:
                    raise AgentUIInputResolutionError("multiple choice submission requires a string array")
                selected_values.append(item)
            if len(set(selected_values)) != len(selected_values):
                raise AgentUIInputResolutionError("multiple choice submission contains duplicates")

        selection_count = len(selected_values)
        if selection_count < min_selections or selection_count > max_selections:
            raise AgentUIInputResolutionError("submitted choice count is outside signed bounds")

        selected_choices: list[Mapping[str, JsonValue]] = []
        for selected_value in selected_values:
            selected = choices_by_value.get(selected_value)
            if selected is None or selected.get("disabled") is True:
                raise AgentUIInputResolutionError("submitted choice is not server-authorized")
            selected_choices.append(selected)

        if selection_mode == "single":
            raw_metadata = selected_choices[0].get("metadata")
            choice_metadata: dict[str, JsonValue] = (
                {str(key): value for key, value in raw_metadata.items()} if isinstance(raw_metadata, Mapping) else {}
            )
            return selected_values[0], choice_metadata

        selected_choice_metadata: list[dict[str, JsonValue]] = []
        for selected_value, selected in zip(selected_values, selected_choices, strict=True):
            raw_metadata = selected.get("metadata")
            selected_choice_metadata.append(
                {
                    "value": selected_value,
                    "metadata": (
                        {str(key): value for key, value in raw_metadata.items()}
                        if isinstance(raw_metadata, Mapping)
                        else {}
                    ),
                }
            )
        return "、".join(selected_values), {
            "selected_values": selected_values,
            "selected_choices": selected_choice_metadata,
        }

    @classmethod
    def _validated_form_values(
        cls,
        target: Mapping[str, JsonValue],
        values: Mapping[str, JsonValue],
    ) -> dict[str, JsonValue]:
        fields = cls._signed_fields(target, interaction_type="form")
        signed_keys = {field.key for field in fields}
        unknown_keys = set(values) - signed_keys
        if unknown_keys:
            raise AgentUIInputResolutionError("form submission contains unsigned fields")
        form_values: dict[str, JsonValue] = {}
        for field in fields:
            if field.key not in values:
                if field.required:
                    raise AgentUIInputResolutionError(f"required form field is missing: {field.key}")
                continue
            value = values[field.key]
            cls._validate_field_value(field, value)
            form_values[field.key] = value
        if not form_values and values:
            raise AgentUIInputResolutionError("form submission contains no server-authorized fields")
        return form_values

    @classmethod
    def _validated_text_value(
        cls,
        target: Mapping[str, JsonValue],
        values: Mapping[str, JsonValue],
    ) -> str:
        allow_blank = target.get("allow_blank")
        if not isinstance(allow_blank, bool):
            raise AgentUIInputResolutionError("text interaction is missing signed blank-input policy")
        fields = cls._signed_fields(target, interaction_type="text")
        if len(fields) != 1 or fields[0].key != "text":
            raise AgentUIInputResolutionError("text interaction must sign exactly one text field")
        field = fields[0]
        if field.field_type not in {"text", "textarea"}:
            raise AgentUIInputResolutionError("text interaction has an invalid signed field type")
        submitted_text = values.get("text")
        if not isinstance(submitted_text, str):
            raise AgentUIInputResolutionError("text interaction requires a text value")
        if not allow_blank and not submitted_text.strip():
            raise AgentUIInputResolutionError("text interaction does not allow blank input")
        cls._validate_field_value(field, submitted_text, allow_blank=allow_blank)
        return submitted_text

    @staticmethod
    def _signed_fields(
        target: Mapping[str, JsonValue],
        *,
        interaction_type: str,
    ) -> list[InteractionField]:
        raw_fields = target.get("fields")
        if not isinstance(raw_fields, list) or not raw_fields:
            raise AgentUIInputResolutionError(f"{interaction_type} interaction is missing server fields")
        fields: list[InteractionField] = []
        try:
            for raw_field in raw_fields:
                if not isinstance(raw_field, Mapping):
                    raise AgentUIInputResolutionError(
                        f"{interaction_type} interaction contains an invalid server field"
                    )
                fields.append(InteractionField.model_validate(dict(raw_field)))
        except ValidationError as exc:
            raise AgentUIInputResolutionError(
                f"{interaction_type} interaction contains invalid signed field constraints"
            ) from exc
        if len({field.key for field in fields}) != len(fields):
            raise AgentUIInputResolutionError(f"{interaction_type} interaction field keys must be unique")
        return fields

    @staticmethod
    def _validate_field_value(
        field: InteractionField,
        value: JsonValue,
        *,
        allow_blank: bool = False,
    ) -> None:
        if value is None:
            if field.required:
                raise AgentUIInputResolutionError(f"required field is missing: {field.key}")
            return

        if field.field_type in {"text", "textarea"}:
            if not isinstance(value, str):
                raise AgentUIInputResolutionError(f"field {field.key} requires a string value")
            if not value.strip():
                if field.required and not allow_blank:
                    raise AgentUIInputResolutionError(f"required field is blank: {field.key}")
                return
            if field.min_length is None or field.max_length is None:
                raise AgentUIInputResolutionError(f"text field has incomplete signed bounds: {field.key}")
            if len(value) < field.min_length or len(value) > field.max_length:
                raise AgentUIInputResolutionError(f"text field is outside signed bounds: {field.key}")
            return

        if field.field_type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise AgentUIInputResolutionError(f"field {field.key} requires a numeric value")
            if not math.isfinite(value):
                raise AgentUIInputResolutionError(f"field {field.key} requires a finite numeric value")
            if field.minimum is None or field.maximum is None:
                raise AgentUIInputResolutionError(f"number field has incomplete signed bounds: {field.key}")
            if value < field.minimum or value > field.maximum:
                raise AgentUIInputResolutionError(f"number field is outside signed bounds: {field.key}")
            return

        if field.field_type in {"select", "multi_select"}:
            options_by_value = {option.value: option for option in field.options}
            selected_values: list[str]
            if field.field_type == "select":
                if value == "" and not field.required:
                    return
                if not isinstance(value, str) or not value:
                    raise AgentUIInputResolutionError(f"field {field.key} requires one selected value")
                selected_values = [value]
            else:
                if not isinstance(value, list):
                    raise AgentUIInputResolutionError(f"field {field.key} requires a string array")
                if any(not isinstance(item, str) or not item for item in value):
                    raise AgentUIInputResolutionError(f"field {field.key} requires a string array")
                selected_values = value
                if len(set(selected_values)) != len(selected_values):
                    raise AgentUIInputResolutionError(f"field {field.key} contains duplicate selections")
                if field.required and not selected_values:
                    raise AgentUIInputResolutionError(f"required field has no selection: {field.key}")
            for selected_value in selected_values:
                option = options_by_value.get(selected_value)
                if option is None or option.disabled:
                    raise AgentUIInputResolutionError(f"field {field.key} contains an unauthorized selection")
            return

        if field.field_type == "boolean":
            if not isinstance(value, bool):
                raise AgentUIInputResolutionError(f"field {field.key} requires a boolean value")
            if field.required and value is not True:
                raise AgentUIInputResolutionError(f"required boolean field must be confirmed: {field.key}")
            return

        if not isinstance(value, str):
            raise AgentUIInputResolutionError(f"field {field.key} requires an ISO date value")
        if not value.strip():
            if field.required:
                raise AgentUIInputResolutionError(f"required field is blank: {field.key}")
            return
        try:
            if field.field_type == "date":
                date.fromisoformat(value)
            elif field.field_type == "datetime":
                datetime.fromisoformat(value)
            else:
                raise AgentUIInputResolutionError(f"field {field.key} has an unsupported signed field type")
        except ValueError as exc:
            raise AgentUIInputResolutionError(f"field {field.key} requires an ISO date value") from exc
