"""Markdown report with figures (SPEC 8): same input, same report.

The report text is in Spanish, like the rest of the documentation. It carries no generation
time, and the PNG files are written without variable metadata, so two runs on the same results
give identical files.
"""

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from astropy.visualization import ZScaleInterval
from matplotlib.figure import Figure
from numpy.typing import NDArray

from gtc_iq.analysis import (
    AIRMASS_EXPONENT,
    CONDITIONS,
    FILTER_WAVELENGTH_NM,
    Correlation,
    FrameRecord,
    SlopeFit,
    WavelengthCheck,
    correlations,
    fit_airmass,
    usable,
    wavelength_check,
    zenith_fwhm,
)
from gtc_iq.config import QCConfig

COLOURS = {"Sloan_i": "tab:orange", "Sloan_z": "tab:red"}
MARKERS = ["o", "s", "^", "D", "v", "P"]


@dataclass(frozen=True)
class QCRow:
    product_id: int
    passed: bool
    flags: str
    reasons: str


@dataclass(frozen=True)
class Unmeasured:
    product_id: int
    status: str
    reason: str


def _float(value: str) -> float | None:
    return float(value) if value else None


def read_qc(path: Path) -> dict[int, QCRow]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            int(row["product_id"]): QCRow(
                int(row["product_id"]), row["passed"] == "True", row["flags"], row["reasons"]
            )
            for row in csv.DictReader(handle)
        }


def read_records(
    frames_csv: Path, qc: dict[int, QCRow]
) -> tuple[list[FrameRecord], list[Unmeasured]]:
    """Measured frames with their QC verdict, and the frames that could not be measured."""
    records: list[FrameRecord] = []
    unmeasured: list[Unmeasured] = []
    with frames_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            product_id = int(row["product_id"])
            fwhm, airmass = _float(row["fwhm_arcsec"]), _float(row["airmass"])
            if row["status"] != "ok" or fwhm is None or airmass is None:
                reason = row["reason"] or row["status"]
                unmeasured.append(Unmeasured(product_id, row["status"], reason))
                continue
            verdict = qc.get(product_id)
            records.append(
                FrameRecord(
                    product_id=product_id,
                    filter=row["filter"],
                    date_obs=datetime.fromisoformat(row["date_obs"]),
                    airmass=airmass,
                    fwhm_arcsec=fwhm,
                    ellipticity=_float(row["ellipticity"]),
                    conditions={key: _float(row[key]) for key in CONDITIONS},
                    passed=verdict.passed if verdict is not None else True,
                )
            )
    return records, unmeasured


def _save(fig: Figure, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=110, metadata={"Software": None})
    plt.close(fig)


def _night_markers(frames: Sequence[FrameRecord]) -> dict[object, str]:
    nights = sorted({f.night for f in frames})
    return {night: MARKERS[i % len(MARKERS)] for i, night in enumerate(nights)}


def plot_airmass(frames: Sequence[FrameRecord], fits: Sequence[SlopeFit], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 4.5))
    markers = _night_markers(frames)
    for f in frames:
        ax.scatter(
            f.airmass,
            f.fwhm_arcsec,
            color=COLOURS.get(f.filter, "tab:blue"),
            marker=markers[f.night],
            s=22,
            alpha=0.8,
            edgecolors="none" if f.passed else "black",
        )
    for fit in fits:
        if fit.method != "pooled":
            continue
        members = [f for f in usable(frames) if f.filter == fit.filter]
        am = np.linspace(fit.airmass_min, fit.airmass_max, 50)
        log_am = np.log([f.airmass for f in members])
        log_fwhm = np.log([f.fwhm_arcsec for f in members])
        intercept = log_fwhm.mean() - fit.slope * log_am.mean()
        colour = COLOURS.get(fit.filter, "tab:blue")
        ax.plot(am, np.exp(intercept) * am**fit.slope, color=colour, lw=1.5)
        theory = np.exp(log_fwhm.mean() - AIRMASS_EXPONENT * log_am.mean())
        ax.plot(am, theory * am**AIRMASS_EXPONENT, color=colour, lw=1, ls="--")
    for name, colour in COLOURS.items():
        ax.plot([], [], color=colour, marker="o", ls="-", label=f"{name}: ajuste")
    ax.plot([], [], color="grey", ls="--", label="pendiente teórica 0,6")
    ax.scatter(
        [], [], facecolors="none", edgecolors="black", label="marcado por QC (fuera del ajuste)"
    )
    for night, marker in markers.items():
        ax.scatter([], [], color="grey", marker=marker, label=f"noche del {night}")
    ax.set_xlabel("Masa de aire")
    ax.set_ylabel("FWHM medida (″)")
    ax.legend(fontsize=7, loc="best")
    ax.grid(alpha=0.3)
    _save(fig, path)


def plot_time(frames: Sequence[FrameRecord], path: Path) -> None:
    nights = sorted({f.night for f in frames})
    fig, axes = plt.subplots(1, len(nights), figsize=(3.2 * len(nights), 3.6), squeeze=False)
    for ax, night in zip(axes[0], nights, strict=True):
        members = sorted((f for f in frames if f.night == night), key=lambda f: f.date_obs)
        twin = ax.twinx()
        twin.plot([f.date_obs for f in members], [f.airmass for f in members], color="grey", lw=1)
        for name, colour in COLOURS.items():
            subset = [f for f in members if f.filter == name]
            ax.plot(
                [f.date_obs for f in subset],
                [f.fwhm_arcsec for f in subset],
                "o",
                color=colour,
                ms=3,
                label=name,
            )
        ax.set_title(f"Noche del {night}", fontsize=9)
        ax.set_ylabel("FWHM medida (″)")
        twin.set_ylabel("Masa de aire (gris)", color="grey")
        ax.tick_params(axis="x", labelrotation=45, labelsize=7)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))  # type: ignore[no-untyped-call]
    axes[0][0].legend(fontsize=7)
    _save(fig, path)


def plot_conditions(frames: Sequence[FrameRecord], path: Path) -> None:
    variables = list(CONDITIONS)
    fig, axes = plt.subplots(1, len(variables), figsize=(3 * len(variables), 3.2), sharey=True)
    markers = _night_markers(frames)
    for ax, variable in zip(axes, variables, strict=True):
        for f in usable(frames):
            value = f.conditions.get(variable)
            if value is not None:
                ax.scatter(
                    value,
                    zenith_fwhm(f),
                    color=COLOURS.get(f.filter, "tab:blue"),
                    marker=markers[f.night],
                    s=12,
                    alpha=0.7,
                )
        ax.set_xlabel(CONDITIONS[variable], fontsize=8)
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("FWHM corregida al cénit (″)")
    _save(fig, path)


def plot_ellipticity(frames: Sequence[FrameRecord], threshold: float, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(5, 3.2))
    values = [f.ellipticity for f in frames if f.ellipticity is not None]
    bins = np.linspace(0, max([threshold * 1.2, *values]), 30).tolist()
    for name, colour in COLOURS.items():
        subset = [f.ellipticity for f in frames if f.filter == name and f.ellipticity is not None]
        if subset:
            ax.hist(subset, bins=bins, color=colour, alpha=0.6, label=name)
    ax.axvline(threshold, color="black", ls="--", lw=1, label=f"umbral {threshold:g}")
    ax.set_xlabel("Elipticidad mediana del fotograma")
    ax.set_ylabel("Fotogramas")
    ax.legend(fontsize=8)
    _save(fig, path)


def save_thumbnail(image: NDArray[np.float64], title: str, path: Path) -> None:
    step = max(1, max(image.shape) // 500)
    small = image[::step, ::step]
    low, high = ZScaleInterval().get_limits(small)
    fig, ax = plt.subplots(figsize=(4, 4))
    ax.imshow(small, origin="lower", cmap="gray", vmin=low, vmax=high)
    ax.set_title(title, fontsize=8)
    ax.set_axis_off()
    _save(fig, path)


def _num(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _airmass_section(fits: Sequence[SlopeFit]) -> list[str]:
    lines = [
        "| Filtro | Ajuste | Fotogramas | Noches | Masa de aire | Pendiente (IC 95 %) "
        "| ¿Incluye 0,6? | Cambio esperado |",
        "|---|---|---|---|---|---|---|---|",
    ]
    names = {"pooled": "todas juntas", "within_night": "dentro de cada noche"}
    for fit in fits:
        lines.append(
            f"| {fit.filter} | {names[fit.method]} | {fit.n_frames} | {fit.n_nights} "
            f"| {_num(fit.airmass_min)}-{_num(fit.airmass_max)} "
            f"| {_num(fit.slope)} ({_num(fit.ci_low)} a {_num(fit.ci_high)}) "
            f"| {'sí' if fit.contains_theory else 'no'} | {_num(100 * fit.expected_change, 0)} % |"
        )
    return lines


def _wavelength_section(check: WavelengthCheck | None) -> list[str]:
    if check is None:
        return [
            "No hay suficientes parejas de fotogramas de los dos filtros cercanas en el tiempo."
        ]
    short, long = check.short_filter, check.long_filter
    return [
        f"Parejas de fotogramas de {long} y {short} tomados con menos de 10 minutos de "
        f"diferencia, corregidos al cénit: {check.n_pairs}.",
        "",
        f"- Cociente observado FWHM({long}) / FWHM({short}): "
        f"{_num(check.observed_ratio, 3)} ± {_num(check.observed_error, 3)} (mediana y su error).",
        f"- Cociente esperado ({_num(FILTER_WAVELENGTH_NM[long], 1)} / "
        f"{_num(FILTER_WAVELENGTH_NM[short], 1)} nm)^−0,2: {_num(check.expected_ratio, 3)}.",
    ]


def _correlation_section(items: Sequence[Correlation]) -> list[str]:
    lines = [
        "| Filtro | Variable | Fotogramas | ρ con la FWHM al cénit | p | ρ con la hora |",
        "|---|---|---|---|---|---|",
    ]
    for c in items:
        rho = "—" if np.isnan(c.rho_fwhm) else _num(c.rho_fwhm)
        p = "—" if np.isnan(c.p_value) else _num(c.p_value, 3)
        rho_time = "—" if np.isnan(c.rho_time) else _num(c.rho_time)
        lines.append(
            f"| {c.filter} | {CONDITIONS[c.variable]} | {c.n_frames} | {rho} | {p} | {rho_time} |"
        )
    return lines


def write_report(
    out_dir: Path,
    frames: list[FrameRecord],
    unmeasured: list[Unmeasured],
    qc: dict[int, QCRow],
    config: QCConfig,
    config_text: str,
    manifest_sha256: str,
    version: str,
    thumbnails: dict[int, Path] | None = None,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    fits = fit_airmass(frames)
    check = wavelength_check(frames)
    corr = correlations(frames)
    plot_airmass(frames, fits, out_dir / "fwhm_airmass.png")
    plot_time(frames, out_dir / "fwhm_time.png")
    plot_conditions(frames, out_dir / "fwhm_conditions.png")
    plot_ellipticity(frames, config.max_ellipticity, out_dir / "ellipticity.png")

    flagged = [row for row in qc.values() if not row.passed]
    nights = sorted({f.night for f in frames})
    lines = [
        "# Informe de calidad de imagen de OSIRIS+",
        "",
        f"Versión de gtc-image-quality: {version}. SHA-256 del manifiesto: `{manifest_sha256}`.",
        "",
        "Se habla de FWHM medida en la imagen, no de seeing: incluye la turbulencia, el "
        "telescopio, el enfoque y el guiado.",
        "",
        "## Datos",
        "",
        f"- Fotogramas medidos: {len(frames)}; sin medir: {len(unmeasured)}; marcados por el "
        f"control de calidad: {len(flagged)}. Los marcados no entran en los ajustes.",
        f"- Noches: {', '.join(str(n) for n in nights)}.",
        "",
        "| Filtro | Noche | Fotogramas | Masa de aire | FWHM mediana (″) |",
        "|---|---|---|---|---|",
    ]
    for name in sorted({f.filter for f in frames}):
        for night in nights:
            members = [f for f in frames if f.filter == name and f.night == night]
            if members:
                am = [f.airmass for f in members]
                fwhm = float(np.median([f.fwhm_arcsec for f in members]))
                lines.append(
                    f"| {name} | {night} | {len(members)} | {_num(min(am))}-{_num(max(am))} "
                    f"| {_num(fwhm)} |"
                )
    lines += [
        "",
        "## FWHM frente a masa de aire (SPEC 5.5)",
        "",
        'Ajuste de log(FWHM) frente a log(masa de aire). "Todas juntas" mezcla las noches; '
        '"dentro de cada noche" da a cada noche su propio nivel y solo usa cómo cambia la FWHM '
        "con la masa de aire a lo largo de la noche. La teoría de la turbulencia predice 0,6. "
        "La última columna es el cambio de FWHM que predice la teoría en ese rango.",
        "",
        *_airmass_section(fits),
        "",
        "![FWHM frente a masa de aire](fwhm_airmass.png)",
        "",
        "![FWHM y masa de aire a lo largo de cada noche](fwhm_time.png)",
        "",
        "## Dependencia con la longitud de onda",
        "",
        *_wavelength_section(check),
        "",
        "## Condiciones de la cabecera (exploratorio)",
        "",
        "Correlación de Spearman de cada variable con la FWHM corregida al cénit, y de la misma "
        "variable con la hora. Si una variable cambia a lo largo de la noche (ρ con la hora "
        "alto), su correlación con la FWHM puede deberse a cualquier otra cosa que también "
        "cambie con la hora. Con pocas noches no se pueden separar causas.",
        "",
        *_correlation_section(corr),
        "",
        "![FWHM frente a las condiciones](fwhm_conditions.png)",
        "",
        "## Elipticidad",
        "",
        "![Histograma de elipticidad](ellipticity.png)",
        "",
        "## Control de calidad",
        "",
    ]
    if flagged:
        lines += ["| Producto | Reglas | Motivos |", "|---|---|---|"]
        for row in sorted(flagged, key=lambda r: r.product_id):
            lines.append(f"| {row.product_id} | {row.flags} | {row.reasons} |")
        for product_id, path in sorted((thumbnails or {}).items()):
            lines += ["", f"![Producto {product_id}]({path.name})"]
    else:
        lines.append("Ningún fotograma marcado.")
    if unmeasured:
        lines += ["", "Sin medir:", ""]
        lines += [
            f"- {u.product_id}: {u.reason}"
            if u.status == "ok"
            else f"- {u.product_id}: {u.status}, {u.reason}"
            for u in unmeasured
        ]
    lines += [
        "",
        "## Tabla por fotograma",
        "",
        "| Producto | Filtro | Hora (UT) | Masa de aire | FWHM (″) | FWHM al cénit (″) "
        "| Elipticidad | Viento (m/s) | Control |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for f in sorted(frames, key=lambda f: f.date_obs):
        ell = "—" if f.ellipticity is None else _num(f.ellipticity, 3)
        wind = f.conditions.get("wind_speed_ms")
        lines.append(
            f"| {f.product_id} | {f.filter} | {f.date_obs:%Y-%m-%d %H:%M} | {_num(f.airmass)} "
            f"| {_num(f.fwhm_arcsec)} | {_num(zenith_fwhm(f))} | {ell} "
            f"| {'—' if wind is None else _num(wind, 1)} | {'ok' if f.passed else 'marcado'} |"
        )
    lines += ["", "## Configuración usada", "", "```yaml", config_text.rstrip(), "```", ""]
    path = out_dir / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
