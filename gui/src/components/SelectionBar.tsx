interface Props {
  checked: number;
  total: number;
  /** text suplimentar, ex. "12 obiecte" */
  detail?: string;
  noun: string;
  onAll: (on: boolean) => void;
  onSelect: () => void;
}

/** Bara pentru selectie multipla: bifeaza toate / nimic si trimite bifatele catre ETABS. */
export default function SelectionBar({ checked, total, detail, noun, onAll, onSelect }: Props) {
  return (
    <div className="selbar">
      <button onClick={() => onAll(true)} disabled={total === 0}>
        Bifează toate ({total})
      </button>
      <button onClick={() => onAll(false)} disabled={checked === 0}>
        Debifează
      </button>
      <button className="primary" onClick={onSelect} disabled={checked === 0}>
        Selectează în ETABS ({checked} {noun}
        {detail ? ` · ${detail}` : ""})
      </button>
      <span className="hint">Shift + clic pe o casetă bifează un interval.</span>
    </div>
  );
}
