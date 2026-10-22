import { useMemo } from "react";
import { useChecked } from "../useChecked";
import { useSelection } from "../useSelection";
import type { ObjRef } from "../types";
import SelectionBar from "./SelectionBar";

const KIND: Record<string, string> = {
  frame: "Bară", wall: "Perete", area: "Arie", joint: "Nod", chain: "Lanț", material: "Material",
  loadpattern: "Tipar încărcare", loadcase: "Caz încărcare", pier: "Pier", diaphragm: "Diafragmă", spring: "Arc", section: "Secțiune", function: "Funcție", masssource: "Sursă de masă", mesh: "Mesh",
};
const keyOf = (o: ObjRef) => `${o.type}:${o.name}`;

/** Lista obiectelor unei probleme. Clic pe rand = selectie doar a acelui obiect; casetele permit selectie multipla. */
export default function ObjectTable({ objects }: { objects: ObjRef[] }) {
  const { select } = useSelection();
  const keys = useMemo(() => objects.map(keyOf), [objects]);
  const { checked, toggle, setAll, allChecked, count } = useChecked(keys);

  const selectChecked = () => {
    const picked = objects.filter((o) => checked.has(keyOf(o)));
    void select(picked, `${picked.length} obiecte bifate`);
  };

  return (
    <>
      <SelectionBar checked={count} total={objects.length} noun="obiecte" onAll={setAll} onSelect={selectChecked} />
      <table className="objects">
        <thead>
          <tr>
            <th className="check">
              <input type="checkbox" aria-label="Bifează toate" checked={allChecked} onChange={(e) => setAll(e.target.checked)} />
            </th>
            <th>Tip</th>
            <th>Etichetă</th>
            <th>Nume unic</th>
            <th>Etaj</th>
            <th>Secțiune</th>
          </tr>
        </thead>
        <tbody>
          {objects.map((o, i) => (
            <tr
              key={keyOf(o)}
              tabIndex={0}
              className={checked.has(keyOf(o)) ? "checked" : ""}
              onClick={() => select([o], `${KIND[o.type] ?? o.type} ${o.label || o.name}`)}
              onKeyDown={(e) => (e.key === "Enter" ? select([o], o.label || o.name) : undefined)}
            >
              <td className="check" onClick={(e) => e.stopPropagation()}>
                <input
                  type="checkbox"
                  aria-label={`Bifează ${o.label || o.name}`}
                  checked={checked.has(keyOf(o))}
                  onChange={() => undefined}
                  onClick={(e) => toggle(i, e.shiftKey)}
                />
              </td>
              <td>
                {KIND[o.type] ?? o.type}
                {o.role === "belt" ? " (centură)" : ""}
              </td>
              <td className="mono">{o.label ?? ""}</td>
              <td className="mono">{o.name}</td>
              <td>{o.story ?? ""}</td>
              <td>{o.section ?? (o.thickness ? `t = ${o.thickness} m` : "")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
