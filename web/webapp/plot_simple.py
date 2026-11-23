"""The single-panel m(T) figure — a faithful port of SimpleWindow._plot/_style_axes/
_set_grid/_layout_figure/_param_panels so the web figure and the saved PNG look the
same as in the desktop app.  Uses the same matplotlib version, so exports match.
"""
from __future__ import annotations

import os

import numpy as np
from matplotlib.figure import Figure
from matplotlib.ticker import AutoMinorLocator, MultipleLocator

from .context import COLORS
from . import context as ctx
from . import runner


# ------------------------------------------------------------------ style ----
def style_axes(ax, pal, show_grid):
    ax.set_facecolor(pal["BG_INPUT"])
    for sp in ax.spines.values():
        sp.set_visible(True); sp.set_linewidth(0.9); sp.set_color(pal["FG"])
    ax.tick_params(which="both", colors=pal["FG"], direction="in", top=True, right=True)
    ax.tick_params(which="major", length=4, width=0.8)
    ax.tick_params(which="minor", length=2, width=0.6)
    ax.xaxis.set_minor_locator(AutoMinorLocator(2))
    ax.yaxis.set_major_locator(MultipleLocator(0.2))
    ax.yaxis.set_minor_locator(AutoMinorLocator(2))
    ax.set_xlabel(r"Temperature, $T$ (K)", color=pal["FG"])
    ax.set_ylabel(r"Reduced magnetisation, $m_z$", color=pal["FG"])
    ax.set_axisbelow(True)
    set_grid(ax, pal, show_grid)


def set_grid(ax, pal, show_grid):
    if show_grid:
        ax.grid(axis="y", which="major", color=pal["BORDER"], lw=0.65, alpha=0.9)
        ax.grid(axis="y", which="minor", color=pal["BORDER"], lw=0.45, alpha=0.45)
    else:
        ax.grid(False)


def param_panels(s, results, session, pal):
    """[(title, accent, [(label, value), ...])] — same content as SimpleWindow."""
    rates = ", ".join(f"{r[0]:g}" for r in results) or "\u2014"
    damp = f"{s['damp']:g}" + ("" if s["damp_use"] == 0 else " (\u03b1/(1+\u03b1\u00b2))")
    panels = [
        ("ME", pal["BLUE"], [("Rate", f"{rates} K/ns"),
                             ("Diameter", f"{s['d_nm']:g} nm"),
                             ("T range", f"{s['t0']:g}\u2192{s['t1']:g} K (\u0394{s['dT']:g})")]),
        ("Physics", pal["GREEN"], [("Field B", f"{s['b_T']:g} T"),
                                   ("Damping \u03bb", damp),
                                   ("P\u2080", f"{s['p0']:g}")]),
        ("Material", pal["FG_DIM"], [("Atoms", f"{s['atoms']}"),
                                     ("Cell a / c", f"{s['a_A']:g} / {s['c_A']:g} \u00c5"),
                                     ("\u03bc / \u03b3rel", f"{s['mu_mub']:g} \u03bcB / {s['gamma_rel']:g}")]),
    ]
    sm = f"SG {s['sg_win']:g} K, order {s['sg_poly']}" if s["sg_on"] else "off"
    vs = runner.vampire_stats(session, s)     # the seeds the plotted band is built from
    if vs is not None:
        name = os.path.basename(session.run_dir)
        name = name if len(name) <= 18 else name[:17] + "\u2026"
        panels.append(("VAMPIRE", pal["AMBER"], [("Run", name),
                                                 ("Seeds", f"{vs.n} @ {session.rate_deck:g} K/ns"),
                                                 ("Smoothing", sm)]))
    else:
        panels.append(("VAMPIRE", pal["AMBER"], [("Run", "none loaded"), ("Seeds", "\u2014"),
                                                 ("Smoothing", sm)]))
    return panels


def layout_figure(fig, s, results, session, pal, params_on):
    """tight_layout + the parameter card drawn at the bottom of the figure."""
    from matplotlib.patches import FancyBboxPatch, Rectangle
    if not params_on:
        fig.tight_layout()
        return
    W, H = fig.get_figwidth(), fig.get_figheight()
    row, head, pad = 0.175, 0.24, 0.10               # inches
    card_h = pad + head + 3 * row + pad
    fh = card_h / H
    y0, x0, cw = 0.012, 0.015, 0.97
    fig.tight_layout(rect=[0, y0 + fh + 0.01, 1, 1])
    fig.add_artist(FancyBboxPatch((x0, y0), cw, fh, transform=fig.transFigure,
                                  boxstyle="round,pad=0,rounding_size=0.012",
                                  mutation_aspect=W / H, fc=pal["BG_PANEL2"],
                                  ec=pal["BORDER"], lw=1.0, zorder=0))
    panels = param_panels(s, results, session, pal)
    n = len(panels)
    gap = 0.012
    pw = (cw - gap * (n + 1)) / n
    for i, (title, acc, rows) in enumerate(panels):
        px = x0 + gap + i * (pw + gap)
        fig.add_artist(Rectangle((px, y0 + pad / H), 0.05 / W, fh - 2 * pad / H,
                                 transform=fig.transFigure, fc=acc, ec="none", zorder=1))
        tx = px + 0.11 / W
        ytop = y0 + fh - pad / H
        fig.text(tx, ytop, title, ha="left", va="top", fontsize=8.5,
                 fontweight="bold", color=acc, zorder=2)
        for j, (lab, val) in enumerate(rows):
            yy = ytop - (head + j * row) / H
            fig.text(tx, yy, lab, ha="left", va="top", fontsize=7.5,
                     color=pal["FG_DIM"], zorder=2)
            fig.text(px + pw - 0.04 / W, yy, val, ha="right", va="top",
                     fontsize=7.5, color=pal["FG"], zorder=2)


# -------------------------------------------------------------------- draw ----
def draw(s, results, session, pal):
    """Builds a fresh figure for this run and returns (fig, text_lines).

    A new Figure object per run (rather than reusing one canvas) is how Streamlit
    expects figures to be handled; nothing about the content changes."""
    fig = Figure(figsize=(ctx.PLOT_FIG_W, ctx.PLOT_FIG_H), dpi=ctx.PLOT_DPI,
                 facecolor=pal["BG_PANEL"])
    ax = fig.add_subplot(111)
    style_axes(ax, pal, s["grid"])

    lines: list[str] = []
    vs = runner.vampire_stats(session, s)
    vrate = session.rate_deck if vs is not None else None
    Ts: list[float] = []

    if vs is not None:
        vcol = COLORS[0]
        rq = (runner.qc_for(session, s["seed_target"]) if s["seed_auto"] else None)
        reduced = rq is not None and len(rq.selected) < len(rq.valid)
        sub = (f"{vs.n} selected of {len(rq.valid)} valid seeds" if reduced
               else f"{vs.n} seeds")
        vm = runner.smooth(s, vs.T, vs.mean)
        # one seed -> sem is NaN (ddof=1); show no error band instead of crashing the plot
        vsem = runner.smooth(s, vs.T, np.nan_to_num(np.asarray(vs.sem, float), nan=0.0))
        if s["traces_all"]:
            vall = runner.vampire_stats(session)          # every valid seed, no reduction
            for row in vall.mz_per_seed:
                ax.plot(vall.T, row, color=pal["FG_DIM"], lw=0.6, alpha=0.18, zorder=1)
            if reduced:                                   # the seeds the analysis uses
                for row in vs.mz_per_seed:
                    ax.plot(vs.T, row, color=vcol, lw=0.8, alpha=0.32, zorder=2)
        if s["sem_band"]:
            ax.fill_between(vs.T, vm - 2 * vsem, vm + 2 * vsem, color=vcol, alpha=0.25, lw=0)
        ax.plot(vs.T, vm, color=vcol, lw=2.2,
                label=f"VAMPIRE {vrate:g} K/ns (n={sub}, \u00b12 s.e.m.)")
        Ts += [float(vs.T.max()), float(vs.T.min())]
        lines.append(f"VAMPIRE {vrate:g} K/ns: {sub}"
                     + (f"; {runner.vampire_stats(session).n} valid trajectories shown (grey)"
                        if s["traces_all"] else ""))

    for i, (rate, T, m, P, ms, Tc) in enumerate(results):
        col = COLORS[(i + (vs is not None)) % len(COLORS)]
        m_s = runner.smooth(s, T, m)
        if m_s is not m:
            ax.plot(T, m, color=col, lw=0.85, alpha=0.24, zorder=2)
        ax.plot(T, m_s, "--" if vs is not None else "-", color=col, lw=2.2, zorder=3,
                label=f"ME {rate:g} K/ns")
        txt = (f"ME {rate:g} K/ns: m(end)={m[-1]:.3f}, P_rev={1 - P[-1]:.3f}, "
               f"Tc\u2248{Tc:.0f} K")
        lab = f"m({T[-1]:g} K)/ms({T[-1]:g} K)"
        txt += f", {lab}: ME={m[-1] / ms[-1]:.4f}"
        if vs is not None:
            v_r, _, _, why = runner.vampire_final(vs, T[-1])
            if vrate is not None and abs(vrate - rate) > 1e-6 * max(1.0, rate):
                txt += (f" | VAMPIRE: not compared (VAMPIRE run is {vrate:g} K/ns, "
                        f"ME is {rate:g} K/ns)")
            else:
                txt += (f" | VAMPIRE(median of {vs.n} seeds)={v_r:.4f}" if v_r is not None
                        else f" | VAMPIRE: not compared ({why})")
        if vs is not None and abs(rate - vrate) <= 1e-9 * max(1.0, rate):
            txt += f", rmse vs VAMPIRE={vs.rmse_me(T, m):.4f}"
        lines.append(txt)
        Ts += [float(T.max()), float(T.min())]

    if not Ts:
        layout_figure(fig, s, results, session, pal, s["params_on"])
        return fig, lines

    lo, hi = min(Ts), max(Ts)
    ax.set_xlim((hi, lo) if s["invert_x"] else (lo, hi))
    ax.set_ylim(0.0, 1.04)
    ax.margins(x=0.01)
    if hi - lo >= 300:
        ax.xaxis.set_major_locator(MultipleLocator(100))
    if results:
        Tc = results[0][5]
        ax.axvline(Tc, color=pal["FG_DIM"], lw=1.1, ls=(0, (4, 3)), zorder=1)
        ax.annotate(rf"$T_{{\mathrm{{C}}}} = {Tc:.0f}\,\mathrm{{K}}$",
                    xy=(Tc, 0.97), xycoords=("data", "axes fraction"),
                    xytext=(7, -2), textcoords="offset points", ha="left", va="top",
                    fontsize=9, color=pal["FG"],
                    bbox=dict(boxstyle="round,pad=0.22", fc=pal["BG_INPUT"],
                              ec="none", alpha=0.88))
    ax.legend(loc="lower right", facecolor=pal["BG_INPUT"], edgecolor="none",
              framealpha=0.92, labelcolor=pal["FG"], fontsize=9)
    ax.set_title(f"D = {s['d_nm']:g} nm", color=pal["FG"])
    layout_figure(fig, s, results, session, pal, s["params_on"])
    return fig, lines
