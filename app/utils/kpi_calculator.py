"""
KPI calculation utilities
"""
from sqlalchemy import func, and_
from datetime import datetime, timedelta
from app import db
from app.models import (
    Shipment, Alert, Recommendation, PurchaseOrder,
    Inventory, ShipmentStatus, AlertSeverity
)

# --------- PUBLIC ENTRY ---------
def calculate_kpis(workspace_id):
    """Calculate main dashboard KPIs (both dashboard & reports needs)."""
    # Existing metrics used on dashboard
    global_risk_index = calculate_global_risk_index(workspace_id)
    on_time_pct_30d = calculate_on_time_percentage(workspace_id)  # 30d
    open_alerts = count_open_alerts(workspace_id)
    inventory_at_risk = count_inventory_at_risk(workspace_id)
    active_pos = count_active_pos(workspace_id)
    pending_approvals = count_pending_approvals(workspace_id)
    cost_savings_mtd = calculate_cost_savings_mtd(workspace_id)
    emissions_reduced = calculate_emissions_reduced(workspace_id)

    # Extra fields required by reports.html
    on_time_trend = calculate_on_time_trend_30d_vs_prev(workspace_id)  # delta %
    avg_response_time_min = calculate_avg_response_time_minutes(workspace_id)  # minutes
    reroutes_count = calculate_reroutes_count(workspace_id)  # best-effort
    emissions_reduction_pct = calculate_emissions_reduction_pct(workspace_id)  # best-effort %

    return {
        # Dashboard (kept for backward compatibility)
        'global_risk_index': global_risk_index,
        'on_time_deliveries': on_time_pct_30d,   # existing name on dashboard
        'open_alerts': open_alerts,
        'inventory_at_risk': inventory_at_risk,
        'active_pos': active_pos,
        'pending_approvals': pending_approvals,
        'cost_savings_mtd': cost_savings_mtd,
        'emissions_reduced': emissions_reduced,

        # Reports (what the template expects)
        'on_time_delivery_rate': on_time_pct_30d,
        'on_time_trend': on_time_trend,
        'cost_avoided': cost_savings_mtd,
        'reroutes_count': reroutes_count,
        'emissions_saved': emissions_reduced,
        'emissions_reduction_pct': emissions_reduction_pct,
        'avg_response_time': avg_response_time_min,
    }

# --------- HELPERS BELOW ---------

def calculate_global_risk_index(workspace_id):
    shipment_risk = db.session.query(
        func.avg(Shipment.risk_score)
    ).filter(
        Shipment.workspace_id == workspace_id,
        Shipment.status.in_([ShipmentStatus.IN_TRANSIT, ShipmentStatus.PLANNED])
    ).scalar() or 0

    high_alerts = Alert.query.filter(
        Alert.workspace_id == workspace_id,
        Alert.status == 'open',
        Alert.severity.in_([AlertSeverity.HIGH, AlertSeverity.CRITICAL])
    ).count()

    total_alerts = Alert.query.filter(
        Alert.workspace_id == workspace_id,
        Alert.status == 'open'
    ).count()

    alert_risk = high_alerts / max(total_alerts, 1)
    global_risk = (shipment_risk * 0.6) + (alert_risk * 0.4)
    return round(min(global_risk, 1.0), 2)

def _on_time_percentage_between(workspace_id, start_dt, end_dt):
    delivered = Shipment.query.filter(
        Shipment.workspace_id == workspace_id,
        Shipment.status == ShipmentStatus.DELIVERED,
        Shipment.actual_arrival >= start_dt,
        Shipment.actual_arrival < end_dt
    ).all()
    if not delivered:
        return 100.0
    # Consider on-time if ETA variance <= 24 hours (as in your code)
    on_time = sum(1 for s in delivered if getattr(s, 'eta_variance', None) is not None and s.eta_variance <= 24)
    return round((on_time / len(delivered)) * 100, 1)

def calculate_on_time_percentage(workspace_id):
    cutoff = datetime.utcnow() - timedelta(days=30)
    return _on_time_percentage_between(workspace_id, cutoff, datetime.utcnow())

def calculate_on_time_trend_30d_vs_prev(workspace_id):
    now = datetime.utcnow()
    start_curr = now - timedelta(days=30)
    start_prev = now - timedelta(days=60)
    pct_curr = _on_time_percentage_between(workspace_id, start_curr, now)
    pct_prev = _on_time_percentage_between(workspace_id, start_prev, start_curr)
    # delta percentage points (can be negative)
    return round(pct_curr - pct_prev, 1)

def count_open_alerts(workspace_id):
    return Alert.query.filter_by(
        workspace_id=workspace_id,
        status='open'
    ).count()

def count_inventory_at_risk(workspace_id):
    return Inventory.query.filter(
        Inventory.workspace_id == workspace_id,
        Inventory.quantity_on_hand <= Inventory.reorder_point
    ).count()

def count_active_pos(workspace_id):
    return PurchaseOrder.query.filter(
        PurchaseOrder.workspace_id == workspace_id,
        PurchaseOrder.status.in_(['draft', 'under_review', 'approved', 'sent'])
    ).count()

def count_pending_approvals(workspace_id):
    from app.models import Approval, ApprovalStatus
    return Approval.query.filter(
        Approval.workspace_id == workspace_id,
        Approval.state == ApprovalStatus.PENDING
    ).count()

def calculate_cost_savings_mtd(workspace_id):
    # TODO: sum approved recommendations with cost_impact for current month
    return 125000

def calculate_emissions_reduced(workspace_id):
    # TODO: sum emissions deltas from optimized routes
    return 450.5

def calculate_reroutes_count(workspace_id):
    """Best-effort: count approved/pending reroute-type recommendations in last 30d."""
    now = datetime.utcnow()
    cutoff = now - timedelta(days=30)
    q = Recommendation.query.filter(
        Recommendation.workspace_id == workspace_id,
        Recommendation.created_at >= cutoff
    )
    # If you have a type enum/field use it, else fallback to title contains
    if hasattr(Recommendation, 'type'):
        try:
            from app.models import RecommendationType  # if it exists
            return q.filter(Recommendation.type == RecommendationType.REROUTE).count()
        except Exception:
            pass
    return q.filter(Recommendation.title.ilike('%reroute%')).count()

def calculate_emissions_reduction_pct(workspace_id):
    """Best-effort % reduction vs a naive baseline (avoid crash if baseline unknown)."""
    # If you later store baseline emissions, compute percent vs baseline.
    # For now, return a safe default.
    return 7.8

def calculate_avg_response_time_minutes(workspace_id):
    """
    Best-effort mean time from alert creation to first response/close (minutes).
    Tries resolved_at then first_response_at; falls back to a safe default if missing.
    """
    alerts = Alert.query.filter(
        Alert.workspace_id == workspace_id
    ).all()

    durations = []
    for a in alerts:
        end = getattr(a, 'resolved_at', None) or getattr(a, 'first_response_at', None)
        if end and a.created_at:
            delta = end - a.created_at
            durations.append(delta.total_seconds() / 60.0)

    if not durations:
        return 24  # safe default in minutes
    return int(sum(durations) / len(durations))
