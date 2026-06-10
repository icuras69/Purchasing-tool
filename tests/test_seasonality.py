from datetime import date, datetime

from app.models.product import Product
from app.models.product_historical_link import ProductHistoricalLink
from app.models.product_seasonality_profile import ProductSeasonalityProfile
from app.models.supplier import Supplier
from app.models.usage_history import UsageHistory
from app.services.historical_product_reconciliation import (
    apply_safe_historical_links,
    build_reconciliation_plan,
    normalize_barcode,
)
from app.services.forecasting import build_forecast
from app.services.seasonality import (
    apply_seasonality_profiles,
    build_seasonality_plan,
    calculate_product_profile,
    calculate_quantity_transform_metrics,
    interpret_current_seasonality,
)


def make_product(db_session, name: str = "Seasonal Product", **overrides) -> Product:
    defaults = {"current_stock": 10, "min_order_qty": 1, "source_system": "orderpro"}
    defaults.update(overrides)
    product = Product(name=name, **defaults)
    db_session.add(product)
    db_session.flush()
    return product


def add_monthly_usage(
    db_session,
    product: Product,
    *,
    years=(2023, 2024),
    base: float = 10,
    peaks: dict[int, float] | None = None,
    months: list[int] | None = None,
) -> None:
    peaks = peaks or {}
    months = months or list(range(1, 13))
    for year in years:
        for month in months:
            quantity = peaks.get(month, base)
            db_session.add(
                UsageHistory(
                    product_id=product.id,
                    date=date(year, month, 15),
                    qty_used=max(quantity, 0),
                    qty_returned=abs(quantity) if quantity < 0 else 0,
                    net_qty=quantity,
                    gross_revenue=quantity * 10,
                    source_system="historical_sales_excel",
                )
            )
    db_session.flush()


def test_multi_year_summer_peak_produces_summer_classification(db_session):
    product = make_product(db_session)
    add_monthly_usage(db_session, product, peaks={6: 40, 7: 45, 8: 42})

    profile = calculate_product_profile(product, list(product.usage_history))

    assert profile["seasonality_tag"] == "summer"
    assert profile["primary_season"] == "summer"
    assert 7 in profile["peak_months"]
    assert profile["confidence_label"] in {"medium", "high"}


def test_multi_year_winter_peak_produces_winter_classification(db_session):
    product = make_product(db_session)
    add_monthly_usage(db_session, product, peaks={12: 50, 1: 48, 2: 44})

    profile = calculate_product_profile(product, list(product.usage_history))

    assert profile["seasonality_tag"] == "winter"
    assert profile["primary_season"] == "winter"


def test_stable_monthly_demand_produces_year_round(db_session):
    product = make_product(db_session)
    add_monthly_usage(db_session, product, base=12)

    profile = calculate_product_profile(product, list(product.usage_history))

    assert profile["seasonality_tag"] == "year_round"
    assert profile["coefficient_of_variation"] == 0


def test_two_distinct_peaks_produce_multi_peak(db_session):
    product = make_product(db_session)
    add_monthly_usage(db_session, product, peaks={1: 40, 7: 42})

    profile = calculate_product_profile(product, list(product.usage_history))

    assert profile["seasonality_tag"] == "multi_peak"
    assert 1 in profile["peak_months"]
    assert 7 in profile["peak_months"]


def test_sparse_history_produces_insufficient_data(db_session):
    product = make_product(db_session)
    add_monthly_usage(db_session, product, years=(2024,), months=[6, 7], peaks={6: 50, 7: 60})

    profile = calculate_product_profile(product, list(product.usage_history))

    assert profile["seasonality_tag"] == "insufficient_data"
    assert profile["confidence_label"] == "insufficient"


def test_one_extreme_order_does_not_create_high_confidence_season(db_session):
    product = make_product(db_session)
    add_monthly_usage(db_session, product, base=1, peaks={12: 1000})

    profile = calculate_product_profile(product, list(product.usage_history))

    assert profile["seasonality_tag"] in {"winter", "multi_peak"}
    assert profile["confidence_label"] != "high"


def test_missing_months_and_negative_quantities_are_handled_explicitly(db_session):
    product = make_product(db_session)
    add_monthly_usage(db_session, product, years=(2023, 2024), months=[1, 2, 3, 4], base=8)
    db_session.add(
        UsageHistory(
            product_id=product.id,
            date=date(2024, 5, 15),
            qty_used=0,
            qty_returned=5,
            net_qty=-5,
            gross_revenue=-50,
            source_system="historical_sales_excel",
        )
    )
    db_session.flush()

    profile = calculate_product_profile(product, list(product.usage_history), minimum_history_months=24)

    assert profile["monthly_units"]["5"] == 0
    assert profile["seasonality_tag"] == "insufficient_data"
    assert any("negative/return" in warning for warning in profile["warnings"])


def test_quantity_transform_metrics_label_raw_positive_and_clamped_values(db_session):
    legacy_positive = make_product(db_session, name="Legacy Positive", source_system="local")
    legacy_negative = make_product(db_session, name="Legacy Negative", source_system="local")
    rows = [
        UsageHistory(
            product_id=legacy_positive.id,
            date=date(2024, 1, 15),
            qty_used=50,
            qty_returned=0,
            net_qty=50,
            gross_revenue=500,
            source_system="historical_sales_excel",
        ),
        UsageHistory(
            product_id=legacy_negative.id,
            date=date(2024, 1, 16),
            qty_used=0,
            qty_returned=20,
            net_qty=-20,
            gross_revenue=-200,
            source_system="historical_sales_excel",
        ),
        UsageHistory(
            product_id=legacy_negative.id,
            date=date(2024, 2, 16),
            qty_used=0,
            qty_returned=10,
            net_qty=-10,
            gross_revenue=-100,
            source_system="historical_sales_excel",
        ),
    ]
    db_session.add_all(rows)
    db_session.flush()

    metrics = calculate_quantity_transform_metrics(
        rows,
        linked_product_ids={legacy_positive.id, legacy_negative.id},
    )

    assert metrics["raw_linked_net_quantity"] == 20
    assert metrics["positive_linked_quantity"] == 50
    assert metrics["negative_linked_quantity"] == -30
    assert metrics["negative_linked_row_count"] == 2
    assert metrics["monthly_raw_net_quantity"] == 20
    assert metrics["linked_product_month_clamped_quantity"] == 50
    assert metrics["target_product_month_clamped_quantity"] == 30
    assert metrics["quantity_used_for_seasonality"] == 30
    assert metrics["quantity_removed_by_target_month_clamp"] == -10
    assert metrics["total_quantity_removed"] == 10
    assert metrics["total_negative_quantity_discarded_or_clamped"] == 10
    assert metrics["total_negative_quantity_retained"] == -20
    assert metrics["total_negative_quantity_retained_abs"] == 20
    assert sum(row["quantity_actually_included"] for row in metrics["target_product_month_breakdown"]) == 30
    assert metrics["quantity_transform_breakdown"][0]["calendar_month"] == "2024-02"
    assert metrics["quantity_transform_breakdown"][0]["quantity_actually_included"] == 0


def test_dry_run_performs_no_writes_and_apply_is_idempotent(db_session):
    product = make_product(db_session)
    add_monthly_usage(db_session, product, peaks={6: 40, 7: 45, 8: 42})

    dry_run = build_seasonality_plan(db_session)

    assert dry_run.profiles_to_create == 1
    assert product.seasonality_profile is None

    apply_seasonality_profiles(db_session)
    db_session.refresh(product)
    first_profile_id = product.seasonality_profile.id

    assert product.seasonality_tag == "summer"

    second_plan = apply_seasonality_profiles(db_session)
    db_session.refresh(product)

    assert product.seasonality_profile.id == first_profile_id
    assert second_plan.profiles_to_update == 1


def test_current_month_and_approaching_status_across_year_boundary(db_session):
    product = make_product(db_session)
    add_monthly_usage(db_session, product, peaks={12: 50, 1: 48, 2: 44})
    apply_seasonality_profiles(db_session)
    db_session.refresh(product)

    in_season = interpret_current_seasonality(product.seasonality_profile, month=12)
    approaching = interpret_current_seasonality(product.seasonality_profile, month=11)

    assert in_season["current_status"] == "in_season"
    assert approaching["current_status"] == "approaching_season"


def test_summary_and_seasonal_products_endpoints_filter_by_status_and_supplier(client, db_session):
    supplier = Supplier(name="Seasonal Supplier", normalized_name="SEASONAL SUPPLIER")
    db_session.add(supplier)
    db_session.flush()
    summer_product = make_product(db_session, name="Summer Product", supplier_record=supplier, is_active=True)
    winter_product = make_product(db_session, name="Winter Product", supplier_record=supplier, is_active=True)
    add_monthly_usage(db_session, summer_product, peaks={6: 40, 7: 45, 8: 42})
    add_monthly_usage(db_session, winter_product, peaks={12: 50, 1: 48, 2: 44})
    apply_seasonality_profiles(db_session)

    summary = client.get("/seasonality/summary", params={"month": 7})
    seasonal = client.get(
        "/products/seasonal",
        params={"month": 7, "status": "in_season", "supplier_id": supplier.id},
    )

    assert summary.status_code == 200
    assert summary.json()["classification_counts"]["summer"] == 1
    assert seasonal.status_code == 200
    assert [row["name"] for row in seasonal.json()] == ["Summer Product"]


def test_product_seasonality_detail_returns_monthly_indices(client, db_session):
    product = make_product(db_session)
    add_monthly_usage(db_session, product, peaks={6: 40, 7: 45, 8: 42})
    apply_seasonality_profiles(db_session)

    response = client.get(f"/products/{product.id}/seasonality", params={"month": 7})

    assert response.status_code == 200
    body = response.json()
    assert body["seasonality_tag"] == "summer"
    assert "7" in body["monthly_indices"]
    assert body["current_interpretation"]["current_status"] == "in_season"


def test_forecast_exposes_advisory_seasonality_without_changing_recommended_qty(db_session):
    supplier = Supplier(name="Forecast Supplier", normalized_name="FORECAST SUPPLIER", lead_time_days=2)
    db_session.add(supplier)
    db_session.flush()
    product = make_product(
        db_session,
        supplier_record=supplier,
        current_stock=100,
        safety_stock=0,
        lead_time_days=2,
    )
    add_monthly_usage(db_session, product, peaks={6: 40, 7: 45, 8: 42})
    apply_seasonality_profiles(db_session)

    forecast = build_forecast(db_session, product)

    assert forecast["recommended_qty"] == 0.0
    assert forecast["seasonality_context"]["seasonality_tag"] == "summer"
    assert forecast["seasonality_context"]["confidence_label"] in {"medium", "high"}


def test_barcode_normalization_ignores_blank_and_placeholder_values():
    assert normalize_barcode(" 123 456.0 ") == "123456"
    assert normalize_barcode("") is None
    assert normalize_barcode("000000000000") is None
    assert normalize_barcode("N/A") is None


def test_unique_exact_barcode_auto_links_historical_product_to_orderpro(db_session):
    orderpro_product = make_product(db_session, name="Current Product", barcode="ABC-123")
    historical_product = make_product(
        db_session,
        name="Legacy Product",
        barcode=" abc123 ",
        source_system="local",
    )
    add_monthly_usage(db_session, historical_product)

    plan = build_reconciliation_plan(db_session)

    assert plan.summary["unique_barcode_matches"] == 1
    assert plan.safe_matches[0]["orderpro_product_id"] == orderpro_product.id
    assert plan.safe_matches[0]["historical_product_id"] == historical_product.id
    assert plan.summary["historical_usage_rows_covered_by_safe_matches"] == 24


def test_blank_barcode_does_not_match(db_session):
    make_product(db_session, name="Current Product", barcode="")
    historical_product = make_product(
        db_session,
        name="Legacy Product",
        barcode="",
        source_system="local",
    )
    add_monthly_usage(db_session, historical_product)

    plan = build_reconciliation_plan(db_session)

    assert plan.summary["unique_barcode_matches"] == 0
    assert plan.summary["blank_invalid_placeholder_legacy_barcodes"] == 1


def test_duplicate_orderpro_barcode_is_ambiguous_not_auto_confirmed(db_session):
    make_product(db_session, name="Current Product A", barcode="DUP")
    make_product(db_session, name="Current Product B", barcode="DUP")
    historical_product = make_product(
        db_session,
        name="Legacy Product",
        barcode="DUP",
        source_system="local",
    )
    add_monthly_usage(db_session, historical_product)

    plan = build_reconciliation_plan(db_session)

    assert plan.summary["unique_barcode_matches"] == 0
    assert plan.summary["duplicate_orderpro_barcode_groups"] == 1
    assert plan.ambiguous_matches[0]["reason"] == "duplicate_orderpro_barcode"


def test_multiple_legacy_products_may_link_to_one_unique_orderpro_product(db_session):
    orderpro_product = make_product(db_session, name="Current Product", barcode="SAFE")
    legacy_one = make_product(db_session, name="Legacy One", barcode="SAFE", source_system="local")
    legacy_two = make_product(db_session, name="Legacy Two", barcode="SAFE", source_system="local")
    add_monthly_usage(db_session, legacy_one)
    add_monthly_usage(db_session, legacy_two, base=5)

    plan = build_reconciliation_plan(db_session)

    assert plan.summary["unique_barcode_matches"] == 2
    assert plan.summary["safely_matched_orderpro_products"] == 1
    assert plan.summary["multiple_legacy_products_matching_one_orderpro_product"] == 1
    assert {match["orderpro_product_id"] for match in plan.safe_matches} == {orderpro_product.id}


def test_exact_name_suggestion_is_review_only(db_session):
    make_product(db_session, name="Same Name", barcode="111")
    historical_product = make_product(
        db_session,
        name="Same Name",
        barcode="222",
        source_system="local",
    )
    add_monthly_usage(db_session, historical_product)

    plan = build_reconciliation_plan(db_session, include_name_suggestions=True)

    assert plan.safe_matches == []
    assert plan.name_suggestions[0]["match_method"] == "name_exact"
    assert plan.name_suggestions[0]["status"] == "needs_review"


def test_dry_run_creates_no_links_and_apply_is_idempotent(db_session):
    orderpro_product = make_product(db_session, name="Current Product", barcode="LINK")
    historical_product = make_product(
        db_session,
        name="Legacy Product",
        barcode="LINK",
        source_system="local",
    )
    add_monthly_usage(db_session, historical_product)

    dry_run = build_reconciliation_plan(db_session)

    assert dry_run.summary["links_to_create"] == 1
    assert db_session.query(ProductHistoricalLink).count() == 0

    apply_safe_historical_links(db_session, confirm_safe_barcode_matches=True)
    apply_safe_historical_links(db_session, confirm_safe_barcode_matches=True)

    links = db_session.query(ProductHistoricalLink).all()
    assert len(links) == 1
    assert links[0].orderpro_product_id == orderpro_product.id
    assert links[0].historical_product_id == historical_product.id
    assert links[0].status == "auto_confirmed"


def test_rejected_and_needs_review_links_do_not_contribute_history(db_session):
    orderpro_product = make_product(db_session, name="Current Product")
    rejected_legacy = make_product(db_session, name="Rejected Legacy", source_system="local")
    review_legacy = make_product(db_session, name="Review Legacy", source_system="local")
    add_monthly_usage(db_session, rejected_legacy)
    add_monthly_usage(db_session, review_legacy, base=15)
    db_session.add_all(
        [
            ProductHistoricalLink(
                orderpro_product_id=orderpro_product.id,
                historical_product_id=rejected_legacy.id,
                match_method="barcode_exact",
                match_value="X",
                confidence_score=1.0,
                confidence_label="high",
                status="rejected",
                created_at=datetime(2024, 1, 1),
                updated_at=datetime(2024, 1, 1),
            ),
            ProductHistoricalLink(
                orderpro_product_id=orderpro_product.id,
                historical_product_id=review_legacy.id,
                match_method="name_exact",
                match_value="Y",
                confidence_score=0.5,
                confidence_label="low",
                status="needs_review",
                created_at=datetime(2024, 1, 1),
                updated_at=datetime(2024, 1, 1),
            ),
        ]
    )
    db_session.flush()

    plan = build_seasonality_plan(db_session)

    profile = next(profile for profile in plan.profiles if profile["product_id"] == orderpro_product.id)
    assert profile["linked_history_row_count"] == 0
    assert profile["seasonality_tag"] == "insufficient_data"


def test_confirmed_links_aggregate_multiple_historical_products_into_orderpro_profile(db_session):
    orderpro_product = make_product(db_session, name="Current Product", barcode="AGG")
    legacy_one = make_product(db_session, name="Legacy One", barcode="AGG", source_system="local")
    legacy_two = make_product(db_session, name="Legacy Two", barcode="AGG", source_system="local")
    add_monthly_usage(db_session, legacy_one, peaks={6: 40, 7: 45, 8: 42})
    add_monthly_usage(db_session, legacy_two, peaks={6: 20, 7: 22, 8: 21})
    apply_safe_historical_links(db_session, confirm_safe_barcode_matches=True)

    plan = apply_seasonality_profiles(db_session)
    db_session.refresh(orderpro_product)

    profile = next(profile for profile in plan.profiles if profile["product_id"] == orderpro_product.id)
    assert profile["linked_history_row_count"] == 48
    assert sorted(profile["contributing_historical_product_ids"]) == sorted([legacy_one.id, legacy_two.id])
    assert orderpro_product.seasonality_profile.product_id == orderpro_product.id
    assert orderpro_product.seasonality_tag == "summer"
    assert legacy_one.seasonality_tag is None
    assert legacy_two.seasonality_tag is None


def test_seasonality_plan_reports_quantity_metrics_without_mislabeling_net_quantity(db_session):
    orderpro_product = make_product(db_session, name="Current Product", barcode="QTY")
    legacy_positive = make_product(db_session, name="Legacy Positive", barcode="QTY", source_system="local")
    legacy_negative = make_product(db_session, name="Legacy Negative", barcode="QTY", source_system="local")
    db_session.add_all(
        [
            UsageHistory(
                product_id=legacy_positive.id,
                date=date(2024, 1, 15),
                qty_used=50,
                qty_returned=0,
                net_qty=50,
                gross_revenue=500,
                source_system="historical_sales_excel",
            ),
            UsageHistory(
                product_id=legacy_negative.id,
                date=date(2024, 1, 16),
                qty_used=0,
                qty_returned=20,
                net_qty=-20,
                gross_revenue=-200,
                source_system="historical_sales_excel",
            ),
            UsageHistory(
                product_id=legacy_negative.id,
                date=date(2024, 2, 16),
                qty_used=0,
                qty_returned=10,
                net_qty=-10,
                gross_revenue=-100,
                source_system="historical_sales_excel",
            ),
        ]
    )
    db_session.flush()
    apply_safe_historical_links(db_session, confirm_safe_barcode_matches=True)

    plan = build_seasonality_plan(db_session)
    coverage = plan.reconciliation_coverage

    assert coverage["raw_linked_net_quantity"] == 20
    assert coverage["positive_linked_quantity"] == 50
    assert coverage["negative_linked_quantity"] == -30
    assert coverage["negative_linked_row_count"] == 2
    assert coverage["monthly_raw_net_quantity"] == 20
    assert coverage["linked_product_month_clamped_quantity"] == 50
    assert coverage["target_product_month_clamped_quantity"] == 30
    assert coverage["quantity_used_for_seasonality"] == 30
    assert coverage["quantity_reconciliation_difference"] == 10
    assert coverage["quantity_used_minus_raw_linked_net_quantity"] == 10
    assert coverage["quantity_used_minus_monthly_raw_net_quantity"] == 10
    assert coverage["net_quantity_contributing_deprecated"] == coverage["quantity_used_for_seasonality"]
    profile = next(profile for profile in plan.profiles if profile["product_id"] == orderpro_product.id)
    assert sum(row["quantity_actually_included"] for row in profile["target_product_month_breakdown"]) == 30


def test_default_apply_refreshes_stale_orderpro_profiles_and_leaves_legacy_profiles_unchanged(db_session):
    orderpro_product = make_product(db_session, name="Current Product", barcode="STALE")
    legacy_product = make_product(
        db_session,
        name="Legacy Product",
        barcode="STALE",
        source_system="local",
        seasonality_tag="legacy_old",
    )
    add_monthly_usage(db_session, legacy_product, peaks={6: 40, 7: 45, 8: 42})
    now = datetime(2024, 1, 1)
    stale_profile = ProductSeasonalityProfile(
        product_id=orderpro_product.id,
        seasonality_tag="insufficient_data",
        confidence_label="insufficient",
        calculated_at=now,
        created_at=now,
        updated_at=now,
    )
    legacy_profile = ProductSeasonalityProfile(
        product_id=legacy_product.id,
        seasonality_tag="legacy_old",
        confidence_label="low",
        calculated_at=now,
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([stale_profile, legacy_profile])
    db_session.flush()
    apply_safe_historical_links(db_session, confirm_safe_barcode_matches=True)

    dry_run = build_seasonality_plan(db_session)

    assert dry_run.reconciliation_coverage["target_orderpro_products"] == 1
    assert dry_run.reconciliation_coverage["stale_orderpro_profiles_to_refresh"] == 1
    assert dry_run.reconciliation_coverage["orderpro_profiles_updated"] == 1
    assert dry_run.reconciliation_coverage["legacy_profiles_left_unchanged"] == 1

    apply_seasonality_profiles(db_session)
    db_session.refresh(orderpro_product)
    db_session.refresh(legacy_product)
    refreshed_profile_id = orderpro_product.seasonality_profile.id

    assert orderpro_product.seasonality_profile.id == stale_profile.id
    assert orderpro_product.seasonality_tag == "summer"
    assert legacy_product.seasonality_profile.id == legacy_profile.id
    assert legacy_product.seasonality_tag == "legacy_old"
    assert legacy_product.seasonality_profile.seasonality_tag == "legacy_old"

    second_plan = apply_seasonality_profiles(db_session)
    db_session.refresh(orderpro_product)

    assert orderpro_product.seasonality_profile.id == refreshed_profile_id
    assert second_plan.reconciliation_coverage["orderpro_profiles_updated"] == 1


def test_default_seasonality_run_targets_orderpro_products_only(db_session):
    orderpro_product = make_product(db_session, name="Current Product")
    legacy_product = make_product(db_session, name="Legacy Product", source_system="local")
    add_monthly_usage(db_session, legacy_product, peaks={6: 40, 7: 45, 8: 42})

    default_plan = build_seasonality_plan(db_session)
    legacy_plan = build_seasonality_plan(db_session, include_legacy_products=True)

    assert [profile["product_id"] for profile in default_plan.profiles] == [orderpro_product.id]
    assert {profile["product_id"] for profile in legacy_plan.profiles} == {
        orderpro_product.id,
        legacy_product.id,
    }


def test_summary_api_excludes_legacy_duplicates_and_seasonal_endpoint_returns_orderpro_products(
    client,
    db_session,
):
    orderpro_product = make_product(db_session, name="Current Product", barcode="API")
    legacy_product = make_product(db_session, name="Legacy Product", barcode="API", source_system="local")
    add_monthly_usage(db_session, legacy_product, peaks={6: 40, 7: 45, 8: 42})
    apply_safe_historical_links(db_session, confirm_safe_barcode_matches=True)
    apply_seasonality_profiles(db_session)

    summary = client.get("/seasonality/summary", params={"month": 7})
    seasonal = client.get("/products/seasonal", params={"month": 7})

    assert summary.status_code == 200
    assert summary.json()["product_count"] == 1
    assert seasonal.status_code == 200
    assert [row["product_id"] for row in seasonal.json()] == [orderpro_product.id]


def test_product_detail_reports_reconciliation_coverage(client, db_session):
    orderpro_product = make_product(db_session, name="Current Product", barcode="DETAIL")
    legacy_product = make_product(db_session, name="Legacy Product", barcode="DETAIL", source_system="local")
    add_monthly_usage(db_session, legacy_product, peaks={6: 40, 7: 45, 8: 42})
    apply_safe_historical_links(db_session, confirm_safe_barcode_matches=True)
    apply_seasonality_profiles(db_session)

    response = client.get(f"/products/{orderpro_product.id}/seasonality", params={"month": 7})

    assert response.status_code == 200
    body = response.json()
    assert body["linked_history_row_count"] == 24
    assert body["contributing_historical_product_ids"] == [legacy_product.id]
    assert body["reconciliation_methods"] == ["barcode_exact"]


def test_forecast_uses_orderpro_profile_and_missing_profile_is_explicit(db_session):
    supplier = Supplier(name="Forecast Supplier 2", normalized_name="FORECAST SUPPLIER 2", lead_time_days=2)
    db_session.add(supplier)
    db_session.flush()
    orderpro_product = make_product(
        db_session,
        name="Current Forecast Product",
        supplier_record=supplier,
        current_stock=100,
        safety_stock=0,
        lead_time_days=2,
        barcode="FORECAST",
    )
    legacy_product = make_product(
        db_session,
        name="Legacy Forecast Product",
        barcode="FORECAST",
        source_system="local",
    )
    add_monthly_usage(db_session, legacy_product, peaks={6: 40, 7: 45, 8: 42})
    apply_safe_historical_links(db_session, confirm_safe_barcode_matches=True)
    apply_seasonality_profiles(db_session)

    forecast = build_forecast(db_session, orderpro_product)

    assert forecast["recommended_qty"] == 0.0
    assert forecast["seasonality_context"]["seasonality_tag"] == "summer"

    missing_product = make_product(
        db_session,
        name="Missing Forecast Product",
        supplier_record=supplier,
        current_stock=100,
        safety_stock=0,
        lead_time_days=2,
    )
    missing_forecast = build_forecast(db_session, missing_product)

    assert missing_forecast["recommended_qty"] == 0.0
    assert missing_forecast["seasonality_context"]["seasonality_tag"] == "insufficient_data"
    assert "No reconciled" in missing_forecast["seasonality_context"]["advisory_message"]
