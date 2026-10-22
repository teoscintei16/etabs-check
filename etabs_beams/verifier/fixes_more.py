"""Reparatii cu un click (grupele 1 si 2): Ritz, greutate proprie, grade de libertate, tip tipare, zone rigide, diafragme,
noduri parazite, mesh standard, etichete Pier pe corp, grinzi secundare. Contractul e cel din `fixes.py`.

Previzualizarea poate cere intrari scalare (`inputs`: se trimit inapoi in args sub aceeasi cheie) sau randuri editabile
(`rows`: lista de randuri; clientul trimite inapoi doar randurile bifate, cu valorile editate)."""
from __future__ import annotations

from ..connection import EtabsError, ok
from .fixes import _LOCK_WARNING, _unlock, fix
from .tableedit import edit_table, read_table


def _summary(names, n=6) -> str:
    names = [str(x) for x in names]
    return ", ".join(names[:n]) + (f" … (+{len(names) - n})" if len(names) > n else "")


def _lock_warning(sap) -> tuple[list[str], bool]:
    locked = bool(sap.GetModelIsLocked())
    return ([_LOCK_WARNING] if locked else []), locked


# ---------------------------------------------------------------- Ritz: accelerații de pornire lipsă
_ACCEL = {"X": "UX", "Y": "UY", "Z": "UZ"}


@fix("ritz_add_accel", "Adaugă accelerațiile lipsă ca vectori de pornire Ritz")
class RitzAddAccel:
    """args: {"cases": [{"name": "Ritz", "missing": ["X", "Y"]}]}."""

    @staticmethod
    def preview(session, args):
        changes = [{"what": f"Caz Ritz „{c['name']}”: vectori de încărcare de pornire", "before": "lipsesc " + ", ".join(c["missing"]),
                    "after": "adăugat " + ", ".join(f"Accel {_ACCEL[a]}" for a in c["missing"])} for c in args["cases"]]
        w, locked = _lock_warning(session.model)
        return {"changes": changes, "warnings": w + ["Vectorii noi se adaugă la cei existenți (cicluri 0, ținta 99 %)."], "unlocks": locked}

    @staticmethod
    def apply(session, args):
        sap = session.model
        undo = {"cases": [], "was_locked": _unlock(sap)}
        for c in args["cases"]:
            r = ok(sap.LoadCases.ModalRitz.GetLoads(c["name"]))
            types, names, cyc, tgt = list(r[1]), list(r[2]), list(r[3]), list(r[4])
            undo["cases"].append({"name": c["name"], "types": types[:], "names": names[:], "cyc": cyc[:], "tgt": tgt[:]})
            for a in c["missing"]:
                types.append("Accel")
                names.append(_ACCEL[a])
                cyc.append(0)
                tgt.append(99.0)
            ok(sap.LoadCases.ModalRitz.SetLoads(c["name"], len(types), types, names, cyc, tgt))
        return undo

    @staticmethod
    def undo(session, undo):
        sap = session.model
        _unlock(sap)
        for c in undo["cases"]:
            ok(sap.LoadCases.ModalRitz.SetLoads(c["name"], len(c["types"]), c["types"], c["names"], c["cyc"], c["tgt"]))


# ---------------------------------------------------------------- multiplicatorul greutății proprii
@fix("set_selfwt", "Corectează multiplicatorul greutății proprii")
class SetSelfWt:
    """args: {"set": {"Dead": 1.0, "Perm": 0.0}}."""

    @staticmethod
    def preview(session, args):
        sap = session.model
        changes = [{"what": f"Tipar „{n}”: multiplicator greutate proprie", "before": ok(sap.LoadPatterns.GetSelfWTMultiplier(n))[0], "after": v}
                   for n, v in args["set"].items()]
        w, locked = _lock_warning(sap)
        return {"changes": changes, "warnings": w, "unlocks": locked}

    @staticmethod
    def apply(session, args):
        sap = session.model
        undo = {"old": {}, "was_locked": _unlock(sap)}
        for n, v in args["set"].items():
            undo["old"][n] = ok(sap.LoadPatterns.GetSelfWTMultiplier(n))[0]
            ok(sap.LoadPatterns.SetSelfWTMultiplier(n, float(v)))
        return undo

    @staticmethod
    def undo(session, undo):
        sap = session.model
        _unlock(sap)
        for n, v in undo["old"].items():
            ok(sap.LoadPatterns.SetSelfWTMultiplier(n, v))


# ---------------------------------------------------------------- grade de libertate active
@fix("set_dof_all", "Activează toate cele 6 grade de libertate")
class SetDofAll:
    @staticmethod
    def preview(session, args):
        sap = session.model
        old = ok(sap.Analyze.GetActiveDOF())[0]
        names = ("UX", "UY", "UZ", "RX", "RY", "RZ")
        w, locked = _lock_warning(sap)
        return {"changes": [{"what": f"Grad de libertate {n}", "before": "dezactivat", "after": "activ"} for n, o in zip(names, old) if not o],
                "warnings": w, "unlocks": locked}

    @staticmethod
    def apply(session, args):
        sap = session.model
        undo = {"old": [bool(x) for x in ok(sap.Analyze.GetActiveDOF())[0]], "was_locked": _unlock(sap)}
        ok(sap.Analyze.SetActiveDOF([True] * 6))
        return undo

    @staticmethod
    def undo(session, undo):
        sap = session.model
        _unlock(sap)
        ok(sap.Analyze.SetActiveDOF(undo["old"]))


# ---------------------------------------------------------------- tipul tiparelor de încărcare
LOAD_TYPES = {"Dead": 1, "SuperDead": 2, "Live": 3, "ReduceLive": 4, "Quake": 5, "Wind": 6, "Snow": 7, "Other": 8,
              "Temperature": 10, "RoofLive": 11, "Notional": 12, "PatternLive": 13}
_LT_BY_VALUE = {v: k for k, v in LOAD_TYPES.items()}


@fix("set_load_types", "Corectează tipul tiparelor de încărcare")
class SetLoadTypes:
    """args: {"rows": [{"name": "utila A", "type": "Live"}]}  (randurile editabile folosesc cheia `type`)."""

    @staticmethod
    def preview(session, args):
        sap = session.model
        items = []
        for r in args["rows"]:
            cur = _LT_BY_VALUE.get(int(ok(sap.LoadPatterns.GetLoadType(r["name"]))[0]), "?")
            items.append({"name": r["name"], "current": cur, "type": r["type"], "include": True})
        w, locked = _lock_warning(sap)
        return {"changes": [], "unlocks": locked,
                "warnings": w + ["Tipul unui tipar influențează combinațiile generate automat și sursa de masă."],
                "rows": {"key": "rows", "title": "Tipare de încărcare", "columns": [
                    {"key": "name", "label": "Tipar"}, {"key": "current", "label": "Tip actual"},
                    {"key": "type", "label": "Tip nou", "edit": "select", "options": list(LOAD_TYPES)}], "items": items}}

    @staticmethod
    def apply(session, args):
        sap = session.model
        undo = {"old": {}, "was_locked": _unlock(sap)}
        for r in args["rows"]:
            if r["type"] not in LOAD_TYPES:
                raise EtabsError(f"Tip de tipar necunoscut: {r['type']}")
            undo["old"][r["name"]] = int(ok(sap.LoadPatterns.GetLoadType(r["name"]))[0])
            ok(sap.LoadPatterns.SetLoadType(r["name"], LOAD_TYPES[r["type"]]))
        return undo

    @staticmethod
    def undo(session, undo):
        sap = session.model
        _unlock(sap)
        for n, v in undo["old"].items():
            ok(sap.LoadPatterns.SetLoadType(n, v))


# ---------------------------------------------------------------- zone rigide
_OFFSETS = "Frame Assignments - End Length Offsets"


@fix("set_rigid_factor", "Setează factorul zonei rigide la capetele barelor")
class SetRigidFactor:
    """args: {"frames": [nume_unice], "factor": 0.75}."""

    @staticmethod
    def preview(session, args):
        sap = session.model
        _v, _f, rows = read_table(sap, _OFFSETS)
        cur = {r["UniqueName"]: r["RigidFact"] for r in rows}
        before = sorted({str(cur.get(n, "?")) for n in args["frames"]})
        w, locked = _lock_warning(sap)
        f = float(args.get("factor", 0.75))
        return {"changes": [{"what": f"{len(args['frames'])} bare ({_summary(args['frames'], 4)}): factor de zonă rigidă",
                             "before": ", ".join(before), "after": f}],
                "warnings": w + ["Rigiditatea structurii crește: deschiderile grinzilor se reduc la fața stâlpului/peretelui."], "unlocks": locked,
                "inputs": [{"key": "factor", "label": "Factor de zonă rigidă (0–1)", "value": f, "unit": ""}]}

    @staticmethod
    def apply(session, args):
        sap = session.model
        f = float(args.get("factor", 0.75))
        if not 0 <= f <= 1:
            raise EtabsError("Factorul de zonă rigidă trebuie să fie între 0 și 1.")
        undo = {"was_locked": _unlock(sap)}
        undo["old"] = edit_table(sap, _OFFSETS, "UniqueName", {n: {"RigidFact": f"{f:g}"} for n in args["frames"]})
        return undo

    @staticmethod
    def undo(session, undo):
        sap = session.model
        _unlock(sap)
        edit_table(sap, _OFFSETS, "UniqueName", undo["old"])


# ---------------------------------------------------------------- diafragme pe plăci
@fix("assign_diaphragm", "Asignează diafragma plăcilor fără diafragmă")
class AssignDiaphragm:
    """args: {"assign": [{"name": nume_unic, "diaphragm": "D1"}]}."""

    @staticmethod
    def preview(session, args):
        count: dict[str, int] = {}
        for a in args["assign"]:
            count[a["diaphragm"]] = count.get(a["diaphragm"], 0) + 1
        w, locked = _lock_warning(session.model)
        return {"changes": [{"what": f"Plăci asignate diafragmei „{d}”", "before": "fără diafragmă", "after": f"{n} plăci"} for d, n in count.items()],
                "warnings": w + ["Diafragma se alege din plăcile învecinate de la același nivel (și turn); verifică la turnurile independente."],
                "unlocks": locked}

    @staticmethod
    def apply(session, args):
        sap = session.model
        undo = {"old": {}, "was_locked": _unlock(sap)}
        for a in args["assign"]:
            undo["old"][a["name"]] = ok(sap.AreaObj.GetDiaphragm(a["name"]))[0]
            ok(sap.AreaObj.SetDiaphragm(a["name"], a["diaphragm"]))
        return undo

    @staticmethod
    def undo(session, undo):
        sap = session.model
        _unlock(sap)
        for n, d in undo["old"].items():
            ok(sap.AreaObj.SetDiaphragm(n, d or "None"))


# ---------------------------------------------------------------- noduri: coordonate parazite
_POINTS = "Point Object Connectivity"


def _fmt(v: float) -> str:
    return f"{float(v):.6f}".rstrip("0").rstrip(".") or "0"


@fix("move_nodes", "Corectează coordonatele nodurilor cu zecimale parazite")
class MoveNodes:
    """args: {"rows": [{"name", "label", "story", "axis": "X", "current": 3.00004, "value": 3.0}]}."""

    @staticmethod
    def preview(session, args):
        w, locked = _lock_warning(session.model)
        items = [{**r, "kind": "→ 0 exact" if abs(float(r["value"])) < 1e-12 else "rotunjit la 1 mm", "include": True} for r in args["rows"]]
        return {"changes": [], "unlocks": locked, "warnings": w + [
            "Valorile aproape de 0 devin 0 exact; celelalte se rotunjesc la 1 mm. Poți edita valoarea nouă a fiecărui nod."],
                "rows": {"key": "rows", "title": "Noduri de corectat", "columns": [
                    {"key": "name", "label": "Nod (nume unic)"}, {"key": "label", "label": "Etichetă"}, {"key": "story", "label": "Etaj"},
                    {"key": "axis", "label": "Axa"}, {"key": "current", "label": "Valoare actuală (m)"}, {"key": "kind", "label": "Propunere"},
                    {"key": "value", "label": "Valoare nouă (m)", "edit": "number"}], "items": items}}

    @staticmethod
    def apply(session, args):
        sap = session.model
        changes: dict[str, dict] = {}
        for r in args["rows"]:
            changes.setdefault(str(r["name"]), {})[r["axis"]] = _fmt(r["value"])
        undo = {"was_locked": _unlock(sap)}
        undo["old"] = edit_table(sap, _POINTS, "UniqueName", changes)
        return undo

    @staticmethod
    def undo(session, undo):
        sap = session.model
        _unlock(sap)
        edit_table(sap, _POINTS, "UniqueName", undo["old"])


# ---------------------------------------------------------------- mesh standard
_FLOOR_G = "Analysis Options - Automatic Mesh Settings for Floors"
_WALL_G = "Analysis Options - Automatic Rectangular Mesh Options for Walls"
_FLOOR_A = "Area Assignments - Floor Auto Mesh Options"
_WALL_A = "Area Assignments - Wall Auto Mesh Options"
_SCOPES = {"floor_global": ("setările globale ale plăcilor", _FLOOR_G, None),
           "wall_global": ("setările globale ale pereților", _WALL_G, None),
           "floor_areas": ("opțiunile de mesh ale plăcilor", _FLOOR_A, "UniqueName"),
           "wall_areas": ("opțiunile de mesh ale pereților", _WALL_A, "UniqueName")}
_MESH_WANT = {"floor_global": {"MeshOpt": "Rectangular", "Localized": "Yes", "MergeJoints": "Yes"}, "wall_global": {},
              "floor_areas": {"MeshOption": "Default", "Restraints": "Yes"}, "wall_areas": {"MeshOption": "Auto Rectangular", "Restraints": "Yes"}}


def _mesh_changes(sap, scope: str, size: float) -> dict:
    """{cheie: {camp: valoare}} doar pentru ce difera de standard."""
    _t, key, kf = _SCOPES[scope]
    _v, _f, rows = read_table(sap, key)
    out = {}
    for r in rows:
        diff = {f: v for f, v in _MESH_WANT[scope].items() if str(r.get(f, "")).strip().lower() != v.lower()}
        if scope.endswith("global"):
            try:
                if abs(float(r["MaxMeshSize"]) - size) > 1e-9:
                    diff["MaxMeshSize"] = _fmt(size)
            except (KeyError, ValueError):
                diff["MaxMeshSize"] = _fmt(size)
        if diff:
            out[r[kf] if kf else None] = diff
    return out


@fix("apply_mesh_standard", "Aplică setările standard de mesh")
class ApplyMeshStandard:
    """args: {"scope": "floor_global"|"wall_global"|"floor_areas"|"wall_areas", "mesh_max": 0.5}."""

    @staticmethod
    def preview(session, args):
        sap = session.model
        size = float(args.get("mesh_max", 0.5))
        what, _key, _kf = _SCOPES[args["scope"]]
        ch = _mesh_changes(sap, args["scope"], size)
        lines = []
        for f in sorted({f for c in ch.values() for f in c}):
            vals = sorted({v[f] for v in ch.values() if f in v})
            n = sum(1 for v in ch.values() if f in v)
            lines.append({"what": f"{n} rânduri: {f}", "before": "diferit de standard", "after": ", ".join(vals)})
        w, locked = _lock_warning(sap)
        return {"changes": lines or [{"what": what, "before": "conform standardului", "after": "—"}],
                "warnings": w + ["Meshul se regenerează la următoarea analiză; poate modifica numărul de elemente."], "unlocks": locked,
                "inputs": ([{"key": "mesh_max", "label": "Dimensiunea maximă aproximativă a elementelor", "value": size, "unit": "m"}]
                           if args["scope"].endswith("global") else [])}

    @staticmethod
    def apply(session, args):
        sap = session.model
        size = float(args.get("mesh_max", 0.5))
        if size <= 0:
            raise EtabsError("Dimensiunea maximă a meshului trebuie să fie pozitivă.")
        _what, key, kf = _SCOPES[args["scope"]]
        undo = {"was_locked": _unlock(sap), "table": key, "keyfield": kf}
        undo["old"] = edit_table(sap, key, kf, _mesh_changes(sap, args["scope"], size))
        return undo

    @staticmethod
    def undo(session, undo):
        sap = session.model
        _unlock(sap)
        edit_table(sap, undo["table"], undo["keyfield"], undo["old"])


# ---------------------------------------------------------------- etichete Pier unice pe corp
@fix("rename_piers", "Redenumește etichetele Pier repetate între corpuri")
class RenamePiers:
    """args: {"renames": [{"name": nume_unic_arie, "pier": "T2_P08"}]}."""

    @staticmethod
    def preview(session, args):
        sap = session.model
        per: dict[tuple, int] = {}
        for r in args["renames"]:
            old = ok(sap.AreaObj.GetPier(r["name"]))[0]
            per[(old, r["pier"])] = per.get((old, r["pier"]), 0) + 1
        w, locked = _lock_warning(sap)
        return {"changes": [{"what": f"Etichetă Pier ({n} arii)", "before": o, "after": nw} for (o, nw), n in sorted(per.items())],
                "warnings": w + ["Etichetele noi se creează automat; cele vechi rămân definite, dar fără arii."], "unlocks": locked}

    @staticmethod
    def apply(session, args):
        sap = session.model
        undo = {"old": {}, "was_locked": _unlock(sap)}
        for pier in sorted({r["pier"] for r in args["renames"]}):
            sap.PierLabel.SetPier(pier)                  # daca exista deja, ETABS intoarce eroare: se ignora
        for r in args["renames"]:
            undo["old"][r["name"]] = ok(sap.AreaObj.GetPier(r["name"]))[0]
            ok(sap.AreaObj.SetPier(r["name"], r["pier"]))
        return undo

    @staticmethod
    def undo(session, undo):
        sap = session.model
        _unlock(sap)
        for n, p in undo["old"].items():
            ok(sap.AreaObj.SetPier(n, p))


# ---------------------------------------------------------------- grinzi secundare: partial fixity
@fix("release_secondary", "Eliberează momentul M3 la capătul grinzii secundare")
class ReleaseSecondary:
    """args: {"ends": [{"name", "end": "I"|"J"}], "k": 0.0}  (k = rigiditate partial fixity, kN·m/rad; 0 = articulatie)."""

    @staticmethod
    def preview(session, args):
        w, locked = _lock_warning(session.model)
        k = float(args.get("k", 0))
        names = [e["name"] for e in args["ends"]]
        return {"changes": [{"what": f"{len(args['ends'])} capete de grinzi ({_summary(names, 4)}): M3", "before": "încastrat",
                             "after": "articulație" if k == 0 else f"partial fixity {k:g} kN·m/rad"}],
                "warnings": w + ["Eliberarea M3 mărește momentul din câmp al grinzii secundare; verifică armarea după reanaliză."], "unlocks": locked,
                "inputs": [{"key": "k", "label": "Rigiditate partial fixity (0 = articulație)", "value": k, "unit": "kN·m/rad"}]}

    @staticmethod
    def apply(session, args):
        sap = session.model
        k = float(args.get("k", 0))
        if k < 0:
            raise EtabsError("Rigiditatea partial fixity nu poate fi negativă.")
        undo = {"old": {}, "was_locked": _unlock(sap)}
        by_beam: dict[str, list[str]] = {}
        for e in args["ends"]:
            by_beam.setdefault(e["name"], []).append(e["end"])
        for name, ends in by_beam.items():
            r = ok(sap.FrameObj.GetReleases(name))
            ii, jj, sv, ev = list(r[0]), list(r[1]), list(r[2]), list(r[3])
            undo["old"][name] = {"ii": ii[:], "jj": jj[:], "sv": sv[:], "ev": ev[:]}
            if "I" in ends:
                ii[5], sv[5] = True, k
            if "J" in ends:
                jj[5], ev[5] = True, k
            ok(sap.FrameObj.SetReleases(name, ii, jj, sv, ev))
        return undo

    @staticmethod
    def undo(session, undo):
        sap = session.model
        _unlock(sap)
        for name, o in undo["old"].items():
            ok(sap.FrameObj.SetReleases(name, o["ii"], o["jj"], o["sv"], o["ev"]))
