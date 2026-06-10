from datetime import date

from app.models.product import Product
from app.models.supplier import Supplier
from app.models.usage_history import UsageHistory
from app.services.forecasting import build_forecast
from app.services.seasonality import (
    apply_seasonality_profiles,
    build_seasonality_plan,
    calculate_product_profile,
    interpret_current_seasonality,
)


def make_product(db_session, name: str = "Seasonal Product", **overrides) -> Product:
    defaults = {"current_stock": 10, "min_order_qty": 1}
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
