"""Plotting engine.

create_figure() reproduces the validated four-panel figure *exactly* (same
code path as plot_<rate>Kns_standalone.py) for the default settings, which is
the regression baseline.  Options (panel toggles, ranges, multi-rate overlay,
export formats) are additive and do not alter the default output.
"""
from __future__ import annotations

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

VCOL = {200: "#009e73", 500: "#0072b2", 1000: "#7b1fa2", 6000: "#cc79a7"}


def create_figure(res, rate: float, *, panels="abcd",
                  show_mean=True, show_sem=True, show_me=True,
                  xlim=(300, 800), ylim=(-0.1, 1.0)):
    s = res.stats
    T, mean, sem = s.T, s.mean, s.sem
    T_me, mA, PA, ms = res.T_me, res.m_me, res.P_me, res.ms_me
    n = s.n
    TAG = f"{rate:g}"
    VCOLR = VCOL.get(int(rate), "#7b1fa2")
    w = (T >= 300) & (T < 310)

    fig, ax = plt.subplots(2, 2, figsize=(13, 9), dpi=150)
    axA, axB, axC, axD = ax[0, 0], ax[0, 1], ax[1, 0], ax[1, 1]

    a = axA
    for i in range(n):
        a.plot(T, s.mz_per_seed[i], lw=0.5, color=VCOLR, alpha=0.3)
    if show_sem:
        a.fill_between(T, mean - 2*sem, mean + 2*sem, color=VCOLR, alpha=0.25, lw=0)
    if show_mean:
        a.plot(T, mean, lw=2.4, color=VCOLR,
               label=f"VAMPIRE mean of {n} seeds (band $\\pm$2 s.e.m.)")
    if show_me:
        a.plot(T_me, mA, "--", lw=2.2, color="k",
               label="ME (Roy): $\\omega_1(T)=\\gamma/\\chi_\\perp(T)$, field-lowered barrier")
    a.axhline(0, color="gray", lw=0.6)
    a.set_xlim(*xlim); a.set_ylim(*ylim)
    a.set_xlabel("Temperature (K)   $\\leftarrow$ cooling"); a.set_ylabel("$M_z$")
    a.grid(alpha=0.3); a.legend(fontsize=8, loc="upper left")
    a.set_title(f"{TAG} K/ns, 4 nm, damping 0.05: $M_z$(T), VAMPIRE vs ME (Roy)")

    a = axB
    a.hist(s.fin, bins=np.linspace(-1.05, 1.05, 42), color=VCOLR, alpha=0.85)
    a.axvline(0, color="gray", lw=0.8)
    a.axvline(np.interp(300, T_me[::-1], mA[::-1]), color="k", ls="--",
              label=f"ME (Roy) m(300 K), $P_{{rev}}$ = {1-PA[-1]:.3f}")
    a.set_xlabel("final $M_z$ per seed (300-309 K)"); a.set_ylabel("seeds")
    a.legend(fontsize=8); a.grid(alpha=0.3)
    a.set_title(f"final state: {s.up} up / {s.down} reversed / "
                f"{s.partial} partly ordered (of {n})")

    a = axC
    for i in range(n):
        a.plot(T, s.transverse[i], lw=0.5, color="#d55e00", alpha=0.3)
    a.plot(T, s.transverse.mean(axis=0), lw=2.2, color="#d55e00",
           label="mean $\\sqrt{M_x^2+M_y^2}$")
    a.plot(T, s.mlen.mean(axis=0), lw=2, color="k", ls="--", label="mean $|m|$")
    a.plot(T_me, ms, lw=1.8, color="#0072b2", ls=":", label="ME $m_s(T)$ (RF)")
    a.set_xlim(*xlim); a.set_ylim(0, 1.0)
    a.set_xlabel("Temperature (K)"); a.set_ylabel("transverse magnetisation / $|m|$")
    a.grid(alpha=0.3); a.legend(fontsize=8)
    a.set_title("transverse part, $|m|$, and ME $m_s(T)$")

    a = axD
    a.scatter(s.fin, s.transverse_share, s=28, color=VCOLR)
    a.set_xlabel("final $M_z$ per seed")
    a.set_ylabel("transverse share $(M_x^2+M_y^2)/|m|^2$ at 300 K")
    a.grid(alpha=0.3)
    a.set_title("per-seed final Mz vs transverse share")

    for lab_, ax_ in zip("abcd", ax.flat):
        ax_.set_title(f"({lab_}) " + ax_.get_title())
    for lab_, ax_ in zip("abcd", (axA, axB, axC, axD)):
        if lab_ not in panels:
            ax_.set_visible(False)
    fig.tight_layout()
    return fig


def overlay_figure(runs: list[tuple[float, "ComparisonResult"]],
                   fname_suffix="") -> "plt.Figure":
    """Multi-rate overlay: mean +- 2 SEM and ME curves for each rate."""
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 5.5), dpi=150)
    for rate, r in runs:
        c = VCOL.get(int(rate), "#7b1fa2")
        s = r.stats
        a1.fill_between(s.T, s.mean - 2*s.sem, s.mean + 2*s.sem, color=c, alpha=0.15, lw=0)
        a1.plot(s.T, s.mean, lw=2, color=c, label=f"{rate:g} K/ns VAMPIRE")
        a1.plot(r.T_me, r.m_me, "--", lw=1.6, color=c, label=f"{rate:g} ME")
        a2.hist(s.fin, bins=np.linspace(-1.05, 1.05, 42), color=c, alpha=0.45,
                label=f"{rate:g} K/ns finals")
    for ax_, xl, yl, t in ((a1, "Temperature (K)", "$M_z$", "M_z(T): multi-rate overlay"),
                           (a2, "final $M_z$", "seeds", "final-state distributions")):
        ax_.set_xlim(300, 800); ax_.grid(alpha=0.3); ax_.legend(fontsize=7)
        ax_.set_xlabel(xl); ax_.set_ylabel(yl); ax_.set_title(t)
    a1.set_ylim(-0.1, 1.0)
    fig.tight_layout()
    return fig


def style_dark(fig):
    """On-screen dark styling (additive; never applied to saved baselines)."""
    fig.patch.set_facecolor("#1a2130")
    for ax in fig.axes:
        ax.set_facecolor("#161d2b")
        for lab in ([ax.title, ax.xaxis.label, ax.yaxis.label]):
            lab.set_color("#dfe6f2")
        ax.tick_params(colors="#8b98ad")
        for sp in ax.spines.values():
            sp.set_color("#2c3850")
        ax.grid(color="#2c3850", alpha=0.6)
        leg = ax.get_legend()
        if leg:
            leg.get_frame().set_facecolor("#202a3d")
            leg.get_frame().set_edgecolor("#2c3850")
            for t in leg.get_texts():
                t.set_color("#dfe6f2")


def save(fig, path: str, dpi: int = 150):
    ext = path.lower().rsplit(".", 1)[-1]
    fig.savefig(path, dpi=dpi if ext == "png" else None)


def arrays_csv(path: str, res) -> None:
    """Numeric arrays: T, VAMPIRE mean, 2*SEM, ME M, ME P, ME Gamma interpolated."""
    s = res.stats
    gam = np.interp(s.T, res.T_me[::-1], res.Gam_me[::-1])
    me_m = np.interp(s.T, res.T_me[::-1], res.m_me[::-1])
    header = "T_K,vampire_mean,sem,me_mz,me_gamma_at_T"
    data = np.column_stack([s.T, s.mean, s.sem, me_m, gam])
    np.savetxt(path, data, delimiter=",", header=header, comments="")
