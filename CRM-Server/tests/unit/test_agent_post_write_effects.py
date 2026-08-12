"""Tests for checkpoint-safe Agent post-write effect normalization."""
from app.services.agent.post_write_effects import merge_post_write_effects, normalize_post_write_effects


def test_normalize_post_write_effects_preserves_canonical_checkpoint_shape():
    assert normalize_post_write_effects({
        "follow_up_confirmation_case_public_ids": ["fuc_1", "fuc_2"],
    }) == {
        "follow_up_confirmation_case_public_ids": ["fuc_1", "fuc_2"],
    }


def test_merge_post_write_effects_extracts_nested_tool_results_and_deduplicates():
    assert merge_post_write_effects(
        {
            "data": {
                "post_commit": {
                    "confirmation_case_public_ids": ["fuc_1", "fuc_2"],
                },
            },
        },
        [
            {"follow_up_confirmation_case_public_ids": ["fuc_2", "fuc_3"]},
            {"confirmation_case_public_ids": ["fuc_1"]},
        ],
    ) == {
        "follow_up_confirmation_case_public_ids": ["fuc_1", "fuc_2", "fuc_3"],
    }
