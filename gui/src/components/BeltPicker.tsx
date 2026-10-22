import type { SectionCount } from "../types";

interface Props {
  sections: SectionCount[];
  hasBelts: boolean | null;
  selected: string[];
  onHasBelts: (v: boolean) => void;
  onSelected: (v: string[]) => void;
}

/** Intrebarea: exista grinzi care simuleaza centurile peretilor? Care sunt sectiunile lor? */
export default function BeltPicker({ sections, hasBelts, selected, onHasBelts, onSelected }: Props) {
  const toggle = (name: string) =>
    onSelected(selected.includes(name) ? selected.filter((s) => s !== name) : [...selected, name]);

  return (
    <section className="card">
      <h2>Centuri de perete</h2>
      <p className="muted">
        Există în model grinzi care simulează centurile pereților (de exemplu secțiuni „dummy”)? Ele sunt tratate separat
        de grinzi, iar verificarea se asigură că sunt peste pereți.
      </p>
      <div className="row" role="radiogroup" aria-label="Există centuri">
        <label className="radio">
          <input type="radio" name="belts" checked={hasBelts === true} onChange={() => onHasBelts(true)} /> Da, există
        </label>
        <label className="radio">
          <input type="radio" name="belts" checked={hasBelts === false} onChange={() => onHasBelts(false)} /> Nu există
        </label>
      </div>
      {hasBelts && (
        <>
          <p className="muted">Alege secțiunile de centură:</p>
          <div className="chips">
            {sections.map((s) => (
              <label key={s.name} className={`chip ${selected.includes(s.name) ? "on" : ""}`}>
                <input type="checkbox" checked={selected.includes(s.name)} onChange={() => toggle(s.name)} />
                {s.name} <span className="muted">({s.count})</span>
              </label>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
