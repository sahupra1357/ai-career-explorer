interface Props {
  value: number; // 1-5
  label: string;
}

const COLORS: Record<number, string> = {
  1: 'bg-blue-200',
  2: 'bg-blue-300',
  3: 'bg-amber-400',
  4: 'bg-orange-400',
  5: 'bg-red-500',
};

export default function IntensityBar({ value, label }: Props) {
  return (
    <div className="flex items-center gap-2">
      <div className="flex gap-0.5">
        {[1, 2, 3, 4, 5].map((i) => (
          <div
            key={i}
            className={`h-2 w-4 rounded-sm ${i <= value ? COLORS[value] : 'bg-slate-200'}`}
          />
        ))}
      </div>
      <span className="text-xs text-slate-500">{label}</span>
    </div>
  );
}
