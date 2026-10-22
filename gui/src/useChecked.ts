import { useCallback, useRef, useState } from "react";

/** Bifare multipla: clic = comuta, Shift+clic = interval fata de ultima bifare. */
export function useChecked(keys: string[]) {
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const last = useRef<number | null>(null);

  const toggle = useCallback(
    (index: number, shift: boolean) => {
      const anchor = last.current;      // capturat acum: updater-ul ruleaza mai tarziu, dupa ce last.current se schimba
      setChecked((prev) => {
        const next = new Set(prev);
        const key = keys[index];
        const turnOn = !prev.has(key);
        if (shift && anchor !== null) {
          const [a, b] = [Math.min(anchor, index), Math.max(anchor, index)];
          for (let i = a; i <= b; i++) (turnOn ? next.add(keys[i]) : next.delete(keys[i]));
        } else if (turnOn) {
          next.add(key);
        } else {
          next.delete(key);
        }
        return next;
      });
      last.current = index;
    },
    [keys],
  );

  const setAll = useCallback(
    (on: boolean) => {
      setChecked(on ? new Set(keys) : new Set());
      last.current = null;
    },
    [keys],
  );

  const allChecked = keys.length > 0 && keys.every((k) => checked.has(k));
  const count = keys.filter((k) => checked.has(k)).length;
  return { checked, toggle, setAll, allChecked, count };
}
