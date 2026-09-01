from app.services.customer_profile_watermark_service import CustomerProfileWatermarkService


def test_numeric_and_timestamp_watermarks_detect_regression():
    service = CustomerProfileWatermarkService()
    result = service.compare(
        {"activity_id": 4, "latest_activity_at": "2026-08-28T10:00:00"},
        {"activity_id": 5, "latest_activity_at": "2026-08-28T11:00:00"},
    )

    assert result.is_behind is True
    assert result.regressed_keys == ("activity_id", "latest_activity_at")


def test_sparse_candidate_does_not_regress_known_watermark():
    service = CustomerProfileWatermarkService()

    result = service.compare({"activity_id": 5}, {"activity_id": 5, "occurred_at": "2026-08-28T11:00:00"})

    assert result.is_behind is False
    assert result.missing_keys == ("occurred_at",)


def test_event_metadata_is_not_ordered():
    service = CustomerProfileWatermarkService()

    result = service.compare(
        {"event_key": "newer-looking-key", "trigger_type": "customer_activity_updated"},
        {"event_key": "older-looking-key", "trigger_type": "customer_activity_created"},
    )

    assert result.is_behind is False
    assert result.regressed_keys == ()


def test_merge_preserves_max_numeric_and_latest_sparse_metadata():
    service = CustomerProfileWatermarkService()

    merged = service.merge(
        {"activity_id": 8, "event_key": "old", "customer_id": 101},
        {"activity_id": 7, "event_key": "new", "latest_activity_at": "2026-08-28T12:00:00"},
    )

    assert merged == {
        "activity_id": 8,
        "event_key": "new",
        "customer_id": 101,
        "latest_activity_at": "2026-08-28T12:00:00",
    }
