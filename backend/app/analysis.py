"""Explorative metric/profit associations; chronological validation uses training boundaries."""
from math import isfinite, sqrt
from statistics import mean
from .strategies import backtest


def correlation(pairs):
    if len(pairs) < 3:
        return None
    xs, ys = zip(*pairs)
    mx, my = mean(xs), mean(ys)
    xx = sum((x-mx)**2 for x in xs)
    yy = sum((y-my)**2 for y in ys)
    if xx == 0 or yy == 0:
        return None
    return sum((x-mx)*(y-my) for x,y in pairs) / sqrt(xx*yy)


def stats(bets, stake):
    n = len(bets)
    profit = sum(b["profit"] for b in bets)
    return {"bets": n, "profit": profit, "roi": profit/(n*stake) if n else None,
            "avg_odds": mean(b["odds"] for b in bets) if n else None}


def analyze(strategy, rows, labels, fixed_odds=None):
    if fixed_odds is not None:
        rows = [{**r, "features": {**r["features"], f"odds_{strategy.market}": fixed_odds}} for r in rows]
    rows = sorted(rows, key=lambda r: (r["game"].start_moscow, r["game"].id))
    result = backtest(strategy, rows)
    bets, stake = result["details"], result["stake"]
    # Keep games on the same date in one partition.
    dates = sorted({b["row"]["game"].start_moscow.date() for b in bets})
    cutoff = dates[min(int(len(dates)*.7), len(dates)-1)] if len(dates) >= 2 else None
    train = [b for b in bets if cutoff is None or b["row"]["game"].start_moscow.date() < cutoff]
    test = [b for b in bets if cutoff is not None and b["row"]["game"].start_moscow.date() >= cutoff]
    metrics = []
    for key, label in labels.items():
        def valid(b):
            v = b["row"]["features"].get(key)
            return isinstance(v, (int,float)) and isfinite(v)
        known = [b for b in train if valid(b)]
        values = sorted(b["row"]["features"][key] for b in known)
        if not values:
            continue
        # Quantile bins, merging ties. Training values alone define the boundaries.
        cuts = sorted({values[min(len(values)-1, len(values)*i//5)] for i in range(1,5)})
        cuts = [v for v in cuts if values[0] < v <= values[-1]]
        bounds = [None, *cuts, None]
        bins = []
        for lo, hi in zip(bounds, bounds[1:]):
            def inside(b):
                if not valid(b):
                    return False
                v = b["row"]["features"][key]
                return (lo is None or v >= lo) and (hi is None or v < hi)
            bins.append({"lower":lo, "upper":hi, "train":stats([b for b in train if inside(b)],stake),
                         "test":stats([b for b in test if inside(b)],stake)})
        corr = correlation([(b["row"]["features"][key], b["profit"]/stake) for b in known])
        metrics.append({"key":key, "label":label, "correlation":corr, "coverage":len(known),
                        "missing":len(train)-len(known), "bins":bins})
    metrics.sort(key=lambda m: m["correlation"] if m["correlation"] is not None else float("-inf"), reverse=True)
    return {"market":strategy.market, "stake":stake, "overall":stats(bets,stake),
            "train":stats(train,stake), "test":stats(test,stake),
            "cutoff":cutoff.isoformat() if cutoff else None, "metrics":metrics}
