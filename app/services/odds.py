from app.db.session import session_scope
from app.db.models import Bet
from app.services import events as events_service

def compute_pools(event_id: int) -> tuple[dict[str, float], float, float]:
    event = events_service.get_event(event_id)
    if not event:
        return {}, 0.0, 0.0

    options = events_service.parse_options(event)
    seed_pool = events_service.parse_seed_pool(event)
    fee = float(event.fee_percent or 0.0)

    with session_scope() as s:
        rows = (
            s.query(Bet.option, Bet.amount)
            .filter(Bet.event_id == event_id, Bet.status == "pending")
            .all()
        )

    real_pool = {opt: 0.0 for opt in options}
    for opt, amt in rows:
        if opt in real_pool:
            real_pool[opt] += float(amt)

    pool_by_opt = {}
    for opt in options:
        pool_by_opt[opt] = float(seed_pool.get(opt, 0.0)) + real_pool.get(opt, 0.0)

    total_pool = sum(pool_by_opt.values())
    return pool_by_opt, total_pool, fee


def compute_coeffs_from_pools(pool_by_opt: dict[str, float], total_pool: float, fee: float) -> dict[str, float]:
    if total_pool <= 0:
        return {k: 1.0 for k in pool_by_opt.keys()}

    coeffs = {}
    for opt, pool in pool_by_opt.items():
        denom = max(float(pool), 1e-9)
        coeffs[opt] = (total_pool * (1.0 - fee)) / denom
    return coeffs
