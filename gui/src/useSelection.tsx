import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { selectInEtabs } from "./api";
import type { ObjRef } from "./types";

interface SelectionCtx {
  message: string;
  busy: boolean;
  /** true: selectia noua se adauga la cea existenta din ETABS (nu o inlocuieste) */
  additive: boolean;
  setAdditive: (v: boolean) => void;
  select: (objects: ObjRef[], title: string) => Promise<void>;
}

const Ctx = createContext<SelectionCtx | null>(null);

/** Transforma obiectele (inclusiv lanturile) in bare/pereti selectabili, fara dubluri. */
export function flatten(objects: ObjRef[]): ObjRef[] {
  const out = new Map<string, ObjRef>();
  for (const o of objects) {
    const items = o.type === "chain" && o.frames ? o.frames : [o];
    for (const it of items) out.set(`${it.type}:${it.name}`, it);
  }
  return [...out.values()];
}

export function SelectionProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [additive, setAdditive] = useState(false);

  const select = useCallback(
    async (objects: ObjRef[], title: string) => {
      const items = flatten(objects);
      if (items.length === 0) {
        setMessage("Nimic de selectat.");
        return;
      }
      setBusy(true);
      try {
        const r = await selectInEtabs(items, !additive);
        setMessage(
          `${additive ? "Adăugat la selecție" : "Selectat"} în ETABS: ${r.selected} obiecte — ${title}` +
            (r.failed.length ? ` (neselectate: ${r.failed.slice(0, 5).join(", ")})` : ""),
        );
      } catch (e) {
        setMessage(`Selecția în ETABS a eșuat: ${(e as Error).message}`);
      } finally {
        setBusy(false);
      }
    },
    [additive],
  );

  return <Ctx.Provider value={{ message, busy, additive, setAdditive, select }}>{children}</Ctx.Provider>;
}

export function useSelection(): SelectionCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("SelectionProvider lipsa");
  return c;
}
