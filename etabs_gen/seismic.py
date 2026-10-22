"""Calcule pure (fara ETABS) pentru actiunea seismica P100-1 si combinatiile de incarcari: spectrul de proiectare,
coeficientul seismic si lista combinatiilor ULS / SLS / seismice."""
from __future__ import annotations

from dataclasses import dataclass

G = 9.81
BETA_LIM = 0.2                      # Sd(T) >= 0.2·ag·γI (P100-1)


@dataclass
class SeismicParams:
    ag: float = 0.20                # acceleratia de proiectare, in multipli de g
    gamma_I: float = 1.0
    beta0: float = 2.5
    Tb: float = 0.07
    Tc: float = 0.7
    Td: float = 3.0
    q: float = 3.5
    lam: float = 0.85               # λ, factorul de corectie al fortei taietoare de baza
    ecc: float = 0.05               # excentricitatea accidentala (fractiune din latura)
    damping: float = 0.05
    psi2: float = 0.3               # coeficientul cvasi-permanent al incarcarii utile (si multiplicatorul de masa)
    orth: float = 0.3               # componenta ortogonala


def shape(T: float, p: SeismicParams) -> float:
    """Sd(T)/(ag·γI·g) pentru factorul de comportare q."""
    b = p.beta0 / p.q
    if T <= p.Tb:
        return 1.0 + (b - 1.0) * T / p.Tb if p.Tb > 0 else b
    if T <= p.Tc:
        return b
    if T <= p.Td:
        return b * p.Tc / T
    return b * p.Tc * p.Td / T ** 2


def sd(T: float, p: SeismicParams) -> float:
    """Spectrul de proiectare Sd(T) in m/s² (γI inclus, cu minimul 0.2)."""
    return p.ag * G * p.gamma_I * max(shape(T, p), BETA_LIM)


def spectrum_points(p: SeismicParams) -> list[tuple[float, float]]:
    """Punctele functiei spectrale user-defined: (T [s], Sd [m/s²]). Include colturile TB, TC, TD si coada pana la 6 s."""
    ts = sorted({0.0, p.Tb, p.Tc, p.Td, *[round(0.1 * k, 2) for k in range(2, 10)], 1.0, 1.25, 1.5, 2.0, 2.5, 3.5, 4.0, 5.0, 6.0})
    return [(t, round(sd(t, p), 5)) for t in ts]


def seismic_coefficient(p: SeismicParams) -> float:
    """Coeficientul seismic C al fortelor statice echivalente: λ·γI·ag·β0/q (valoarea de platou)."""
    return round(p.lam * p.gamma_I * p.ag * p.beta0 / p.q, 5)


def coefficient_for_period(T: float, p: SeismicParams) -> float:
    """C = λ·Sd(T1)/g: coeficientul fortelor statice pentru perioada fundamentala T1 (cum il calculeaza si verificatorul)."""
    return round(p.lam * sd(T, p) / G, 5)


# ---------------------------------------------------------------- combinatii
def combos(has_perm: bool, static: list[str], rs: list[str], p: SeismicParams, gamma_g: float = 1.35, gamma_q: float = 1.5,
           extra_perm: list[str] | tuple[str, ...] = ()) -> list[tuple[str, list[tuple[str, float]]]]:
    """[(nume, [(tipar_sau_caz, factor)])]. `static` = tiparele statice (EXP, EXN, EYP, EYN), `rs` = cazurile de spectru (SPECX, SPECY).
    Partea gravitationala a combinatiilor seismice = G + ψ2·Q, aceeasi cu multiplicatorii sursei de masa."""
    perm = [("Permanenta", 1.0)] if has_perm else []
    permu = [("Permanenta", gamma_g)] if has_perm else []
    ep = list(extra_perm)         # tipare permanente suplimentare (ex. impingerea pamantului): in ULS si SLS, nu in combinatiile seismice
    out = [("ULS", [("Dead", gamma_g), *permu, ("Live", gamma_q), *[(e, gamma_g) for e in ep]]),
           ("SLS_CAR", [("Dead", 1.0), *perm, ("Live", 1.0), *[(e, 1.0) for e in ep]]),
           ("SLS_QP", [("Dead", 1.0), *perm, ("Live", p.psi2), *[(e, 1.0) for e in ep]])]
    grav = [("Dead", 1.0), *perm, ("Live", p.psi2)]
    axis = {n: ("X" if n[1] == "X" else "Y") for n in static}
    for a in static:
        for sa in (1, -1):
            out.append((f"S_{'+' if sa > 0 else '-'}{a}", grav + [(a, float(sa))]))
            for b in static:
                if axis[b] == axis[a]:
                    continue
                for sb in (1, -1):
                    out.append((f"S_{'+' if sa > 0 else '-'}{a}_{'+' if sb > 0 else '-'}{p.orth:g}{b}", grav + [(a, float(sa)), (b, sb * p.orth)]))
    for r in rs:
        for s in (1, -1):
            out.append((f"S_{'+' if s > 0 else '-'}{r}", grav + [(r, float(s))]))
    return out
