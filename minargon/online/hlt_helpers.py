"""HLT2/HLT4 gate count helpers.

Public API:
    get_hlt_p_values() -> {hlt_id: p or None}      (introduction page)
    get_hlt_images()   -> {hlt_id: base64 JPEG}    (hlt_gate_count page)
"""
from __future__ import absolute_import

import base64
import io
import time

import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as plt
import numpy as np

from minargon.metrics import online_metrics

HLT_STREAMS = {
    2: 'HLT_ID:2:HLT_gate_count:nozero',
    4: 'HLT_ID:4:HLT_gate_count:nozero',
}
HLT_WINDOW_S = {2: 24 * 3600, 4: 2 * 24 * 3600}   # time window used for each HLT
HLT_MIN_N = 30                                    # minimum number of gates to trust the MLE
HLT_N_DATA = 1000                                 # entries read from Redis per stream


# ----------------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------------
def _fetch_values():
    """Read both streams from Redis. Returns {hlt_id: array of gate counts > 0 inside the time window}."""
    from minargon.metrics import redis_api
    r = online_metrics.r_databases["online"]
    data = redis_api.get_streams(r, list(HLT_STREAMS.values()), n_data=HLT_N_DATA)

    out = {}
    for hlt_id, key in HLT_STREAMS.items():
        stream = data.get(key)
        if not stream:
            out[hlt_id] = np.array([])
            continue
        t, v = (np.array(a, dtype=float) for a in zip(*stream))
        mask = (v > 0) & (time.time() - t / 1000.0 < HLT_WINDOW_S[hlt_id])
        out[hlt_id] = v[mask]
    return out


def _mle(values):
    """MLE of p and its error for P(X=k) = p(1-p)^(k-1). Returns (None, None) if empty."""
    if len(values) == 0:
        return None, None
    p = 1.0 / np.mean(values)
    err = p * np.sqrt((1 - p) / len(values))
    return float(p), float(err)


def _plot(values, hlt_id):
    """Histogram + geometric fit as a base64 JPEG string."""
    max_val = max(100, np.max(values)) if len(values) > 0 else 100
    bins = np.arange(-0.5, max_val + 1.5, 1)
    bin_centers = bins[:-1] + 0.5

    n_days = HLT_WINDOW_S[hlt_id] / (3600 * 24)
    title = ("HLT%d | last %.0f days" % (hlt_id, n_days)) if n_days > 1 else ("HLT%d | last day" % hlt_id)

    fig, ax = plt.subplots(figsize=(8, 4))
    try:
        p, err = _mle(values)
        if p is not None:
            pk = p * (1 - p) ** (bin_centers - 1)
            label = rf'$p(1-p)^{{k-1}}$ | p=${p:.3f} \pm {err:.3f}$'
            ax.plot(bin_centers, pk, lw=1, color='red', label=label)
            ax.hist(values, bins=bins, density=True, label='Data (N=%d)' % len(values))
            ax.legend()
        else:
            ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)

        ax.set_title(title)
        ax.set_xlabel("Gate Count")
        ax.set_ylabel("Density")
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="JPEG", dpi=150)
    finally:
        plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode('utf-8')


# ----------------------------------------------------------------------------
# Main functions
# ----------------------------------------------------------------------------
def get_hlt_p_values():
    """Return {hlt_id: p} for each stream; p is None if there is no data, too few gates (< HLT_MIN_N) or Redis fails."""
    try:
        values = _fetch_values()
    except Exception:
        return {hlt_id: None for hlt_id in HLT_STREAMS}

    out = {}
    for hlt_id in HLT_STREAMS:
        p = None
        if len(values[hlt_id]) >= HLT_MIN_N:
            p, _ = _mle(values[hlt_id])
        out[hlt_id] = p
    return out


def get_hlt_images():
    """Return {hlt_id: base64 JPEG} with the histogram and fit of each stream."""
    values = _fetch_values()
    return {hlt_id: _plot(values[hlt_id], hlt_id) for hlt_id in HLT_STREAMS}