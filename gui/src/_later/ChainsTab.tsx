import { useMemo, useState } from "react";
import { useChecked } from "../useChecked";
import SelectionBar from "../components/SelectionBar";
import { runDetect } from "../api";
import { useSelection } from "../useSelection";
import type { Chain, DetectResult, Selector } from "../types";

interface Props {
  beltSections: string[];
}

const split = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
const f2 = (x: number) => x.toFixed(2);

export default function ChainsTab({ beltSections }: Props) {
  const [sections, setSections] = useState("");
  const [exclude, setExclude] = useState("");
  const [stories, setStories] = useState("");
  const [continuity, setContinuity] = useState<Selector["continuity"]>("any");
  const [match, setMatch] = useState<Selector["match"]>("any");
  const [minLength, setMinLength] = useState("");
  const [wallMin, setWallMin] = useState("0.80");
  const [result, setResult] = useState<DetectResult | null>(null);
  const [view, setView] = useState<"beams" | "belts">("beams");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const { select } = useSelection();

  const run = async () => {
    setLoading(true);
    setError("");
    try {
      const selector: Selector = {
        sections: split(sections),
        exclude_sections: split(exclude),
        stories: split(stories),
        min_length: minLength ? Number(minLength) : null,
        match,
        continuity,
      };
      setResult(await runDetect(beltSections, selector, Number(wallMin) || 0.8));
      setOpen(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const list: Chain[] = result ? (view === "beams" ? result.chains : result.belts) : [];
  const keys = useMemo(() => list.map((c) => c.id), [list]);
  const { checked, toggle, setAll, allChecked, count } = useChecked(keys);
  const picked = list.filter((c) => checked.has(c.id));
  const pickedFrames = picked.flatMap((c) => c.members.map((m) => ({ type: "frame", name: m.frame, label: m.label })));
  const selectChecked = () => void select(pickedFrames, `${picked.length} lanțuri bifate`);

  const clickChain = (c: Chain) => {
    setOpen(open === c.id ? null : c.id);
    void select(
      c.members.map((m) => ({ type: "frame", name: m.frame, label: m.label })),
      `${c.id} (${c.members.length} bare)`,
    );
  };

  return (
    <>
      <section className="card">
        <h2>Detecție grinzi continue</h2>
        <div className="grid">
          <label>
            Doar secțiuni (sabloane, separate prin virgulă)
            <input value={sections} onChange={(e) => setSections(e.target.value)} placeholder="ex. GR40*, B30x60" />
          </label>
          <label>
            Fără secțiuni
            <input value={exclude} onChange={(e) => setExclude(e.target.value)} placeholder="ex. GR30*" />
          </label>
          <label>
            Etaje
            <input value={stories} onChange={(e) => setStories(e.target.value)} placeholder="ex. S1, E1" />
          </label>
          <label>
            Tip
            <select value={continuity} onChange={(e) => setContinuity(e.target.value as Selector["continuity"])}>
              <option value="any">Toate</option>
              <option value="continuous">Continue (≥ 2 deschideri)</option>
              <option value="single_span">O singură deschidere</option>
            </select>
          </label>
          <label>
            Potrivire secțiuni
            <select value={match} onChange={(e) => setMatch(e.target.value as Selector["match"])}>
              <option value="any">Lanț cu cel puțin un membru potrivit</option>
              <option value="all">Lanț cu toți membrii potriviți</option>
            </select>
          </label>
          <label>
            Lungime minimă lanț [m]
            <input value={minLength} onChange={(e) => setMinLength(e.target.value)} inputMode="decimal" />
          </label>
          <label>
            Perete lung peste [m]
            <input value={wallMin} onChange={(e) => setWallMin(e.target.value)} inputMode="decimal" />
          </label>
        </div>
        <div className="actions">
          <button className="primary" onClick={run} disabled={loading}>
            {loading ? "Se detectează…" : "Detectează"}
          </button>
          <span className="muted">Centuri: {beltSections.length ? beltSections.join(", ") : "nedeclarate"}</span>
        </div>
      </section>

      {error && (
        <p className="banner error" role="alert">
          {error}
        </p>
      )}

      {result && (
        <section className="card">
          <div className="summary">
            <button className={`tab-pill ${view === "beams" ? "on" : ""}`} onClick={() => setView("beams")}>
              Grinzi ({result.chains_selected}/{result.chains_total})
            </button>
            <button className={`tab-pill ${view === "belts" ? "on" : ""}`} onClick={() => setView("belts")}>
              Centuri ({result.belts_selected}/{result.belts_total})
            </button>
            {result.on_wall.length > 0 && <span className="muted">{result.on_wall.length} porțiuni pe perete lung</span>}
          </div>
          <p className="hint">Clic pe un rând selectează barele lanțului în ETABS. Bifează mai multe lanțuri pentru a le selecta odată.</p>
          <SelectionBar
            checked={count}
            total={list.length}
            noun="lanțuri"
            detail={`${new Set(pickedFrames.map((f) => f.name)).size} bare`}
            onAll={setAll}
            onSelect={selectChecked}
          />
          <div className="scroll">
            <table className="objects chains">
              <thead>
                <tr>
                  <th className="check">
                    <input type="checkbox" aria-label="Bifează toate" checked={allChecked} onChange={(e) => setAll(e.target.checked)} />
                  </th>
                  <th title="Nume unice ETABS ale barelor lanțului, în ordine">Nume unic (lanț)</th>
                  <th>Etaj</th>
                  <th>Lungime [m]</th>
                  <th>Deschideri</th>
                  <th>Tip</th>
                  <th>Secțiuni</th>
                  <th>Bare (etichete)</th>
                </tr>
              </thead>
              <tbody>
                {list.map((c, i) => (
                  <ChainRow
                    key={c.id}
                    c={c}
                    open={open === c.id}
                    checked={checked.has(c.id)}
                    onCheck={(shift) => toggle(i, shift)}
                    onClick={() => clickChain(c)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}

function ChainRow({ c, open, checked, onCheck, onClick }: {
  c: Chain;
  open: boolean;
  checked: boolean;
  onCheck: (shift: boolean) => void;
  onClick: () => void;
}) {
  const secs = [...new Set(c.members.map((m) => m.section))].join(", ");
  return (
    <>
      <tr
        tabIndex={0}
        className={checked ? "checked" : ""}
        onClick={onClick}
        onKeyDown={(e) => (e.key === "Enter" ? onClick() : undefined)}
        aria-expanded={open}
      >
        <td className="check" onClick={(e) => e.stopPropagation()}>
          <input
            type="checkbox"
            aria-label={`Bifează ${c.id}`}
            checked={checked}
            onChange={() => undefined}
            onClick={(e) => onCheck(e.shiftKey)}
          />
        </td>
        <td className="mono id-cell" title={c.id}>{c.id}</td>
        <td>{c.story}</td>
        <td>{f2(c.length)}</td>
        <td>{c.spans.length}</td>
        <td>{c.continuity === "continuous" ? "continuă" : "o deschidere"}</td>
        <td>{secs}</td>
        <td className="mono">{c.members.map((m) => m.label || m.frame).join(", ")}</td>
      </tr>
      {open && (
        <tr className="detail">
          <td colSpan={8}>
            <div className="detail-grid">
              <div>
                <h3>Deschideri</h3>
                <table className="objects">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Axe [m]</th>
                      <th>Liberă [m]</th>
                      <th>Secțiuni</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {c.spans.map((s) => (
                      <tr key={s.index}>
                        <td>{s.index}</td>
                        <td>{f2(s.length)}</td>
                        <td>{f2(s.clear_length)}</td>
                        <td>{s.sections.join(", ")}</td>
                        <td>{s.cantilever ? "consolă" : ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div>
                <h3>Reazeme</h3>
                <table className="objects">
                  <thead>
                    <tr>
                      <th>Nod</th>
                      <th>Abscisă</th>
                      <th>Tip</th>
                      <th>Offset ←/→</th>
                    </tr>
                  </thead>
                  <tbody>
                    {c.supports.map((s) => (
                      <tr key={s.node}>
                        <td className="mono">{s.node}</td>
                        <td>{f2(s.station)}</td>
                        <td>
                          {s.kind}
                          {s.fixed_end ? " (încastrat)" : ""}
                        </td>
                        <td>
                          {f2(s.offset_before)} / {f2(s.offset_after)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            {c.warnings.length > 0 && (
              <ul className="muted">
                {c.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            )}
          </td>
        </tr>
      )}
    </>
  );
}
