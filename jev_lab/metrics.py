"""Statistiques pures (aucune dépendance) : précision, F1, AUC, calibration, bootstrap, McNemar, percentiles..."""
import math, random


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def percentile(xs, q):
    """Percentile q (0..100) par interpolation linéaire."""
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * q / 100
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def accuracy(correct):
    return mean(1.0 if c else 0.0 for c in correct)


def macro_f1(preds, golds):
    labs = sorted({g for g in golds}, key=str)
    f = []
    for l in labs:
        tp = sum(1 for p, g in zip(preds, golds) if p == l and g == l)
        fp = sum(1 for p, g in zip(preds, golds) if p == l and g != l)
        fn = sum(1 for p, g in zip(preds, golds) if p != l and g == l)
        f.append(0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
    return mean(f)


def auc(scores, labels):
    """AUROC binaire (probabilité qu'un positif ait un score plus haut qu'un négatif ; ex aequo = 1/2)."""
    pos = [s for s, y in zip(scores, labels) if y]
    neg = [s for s, y in zip(scores, labels) if not y]
    if not pos or not neg:
        return float("nan")
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks, i = [0.0] * len(scores), 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    rp = sum(r for r, y in zip(ranks, labels) if y)
    return (rp - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def brier(p, y):
    return mean((a - (1.0 if b else 0.0)) ** 2 for a, b in zip(p, y))


def calibration(conf, correct, bins=10):
    """-> (ECE, [{lo, hi, n, conf, acc}]) ; conf = confiance déclarée dans la classe prédite."""
    pairs = [(c, 1.0 if k else 0.0) for c, k in zip(conf, correct) if c is not None]
    rows, ece, n = [], 0.0, len(pairs)
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        sel = [(c, k) for c, k in pairs if (lo <= c < hi) or (b == bins - 1 and c == 1.0)]
        if not sel:
            continue
        mc, ma = mean(c for c, _ in sel), mean(k for _, k in sel)
        ece += len(sel) / n * abs(mc - ma)
        rows.append({"lo": lo, "hi": hi, "n": len(sel), "conf": mc, "acc": ma})
    return (ece if n else float("nan")), rows


def risk_coverage(conf, correct, covs=(1.0, 0.9, 0.8, 0.5)):
    """Précision si l'on ne garde que la part `cov` d'exemples la plus confiante (abstention sur le reste)."""
    pairs = sorted(((c, 1.0 if k else 0.0) for c, k in zip(conf, correct) if c is not None), key=lambda x: -x[0])
    out = {}
    for cv in covs:
        m = max(1, int(round(len(pairs) * cv)))
        out[cv] = mean(k for _, k in pairs[:m]) if pairs else float("nan")
    return out


def bootstrap_ci(values, stat=mean, b=2000, seed=1, alpha=0.05):
    values = list(values)
    if not values:
        return (float("nan"), float("nan"))
    rnd = random.Random(seed)
    n = len(values)
    est = sorted(stat([values[rnd.randrange(n)] for _ in range(n)]) for _ in range(b))
    return est[int(alpha / 2 * b)], est[int((1 - alpha / 2) * b) - 1]


def mcnemar_exact(b, c):
    """p-value exacte bilatérale : b = A juste & B faux, c = A faux & B juste."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n * 2
    return min(1.0, p)


def holm(pvals):
    """Correction de Holm (contrôle de l'erreur sur l'ensemble des comparaisons)."""
    idx = sorted(range(len(pvals)), key=lambda i: pvals[i])
    out, run = [1.0] * len(pvals), 0.0
    for r, i in enumerate(idx):
        run = max(run, min(1.0, (len(pvals) - r) * pvals[i]))
        out[i] = run
    return out


def spearman(a, b):
    def rk(v):
        o = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(o):
            j = i
            while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]:
                j += 1
            for k in range(i, j + 1):
                r[o[k]] = (i + j) / 2
            i = j + 1
        return r
    ra, rb = rk(a), rk(b)
    ma, mb = mean(ra), mean(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va, vb = sum((x - ma) ** 2 for x in ra), sum((y - mb) ** 2 for y in rb)
    return cov / math.sqrt(va * vb) if va and vb else float("nan")


def threshold_two_fold(p, y, seed=1):
    """Seuil choisi sur une moitié, évalué sur l'autre (et inversement) : évite d'optimiser sur les données du test.
    Renvoie la précision équilibrée moyenne et les seuils retenus."""
    idx = list(range(len(p)))
    random.Random(seed).shuffle(idx)
    halves = [idx[: len(idx) // 2], idx[len(idx) // 2:]]

    def bal(sel, t):
        tp = sum(1 for i in sel if p[i] >= t and y[i]); pos = sum(1 for i in sel if y[i])
        tn = sum(1 for i in sel if p[i] < t and not y[i]); neg = sum(1 for i in sel if not y[i])
        return (tp / pos if pos else 0.5) / 2 + (tn / neg if neg else 0.5) / 2

    res, ts = [], []
    for a, b in ((0, 1), (1, 0)):
        cand = sorted({p[i] for i in halves[a]} | {.5})
        best = max(cand, key=lambda t: bal(halves[a], t))
        ts.append(best)
        res.append(bal(halves[b], best))
    return mean(res), ts


def ece_ci(conf, correct, b=300, seed=1):
    """Intervalle de confiance bootstrap de l'ECE (resélection des couples confiance/réussite)."""
    pairs = [(c, k) for c, k in zip(conf, correct) if c is not None]
    if len(pairs) < 30:
        return (float("nan"), float("nan"))
    rnd = random.Random(seed)
    est = sorted(calibration([p[0] for p in s], [p[1] for p in s])[0] for s in ([pairs[rnd.randrange(len(pairs))] for _ in pairs] for _ in range(b)))
    return est[int(.025 * b)], est[int(.975 * b) - 1]
