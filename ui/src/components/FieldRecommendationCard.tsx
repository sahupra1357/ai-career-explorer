import type { RecommendedField } from '../types';

interface FieldRecommendationCardProps {
  field: RecommendedField;
  onDeepDive: (fieldId: string) => void;
}

export default function FieldRecommendationCard({ field, onDeepDive }: FieldRecommendationCardProps) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-slate-900 text-sm">{field.name}</h3>
          {field.score !== null && (
            <div className="mt-1 flex items-center gap-1.5">
              <div className="h-1.5 rounded-full bg-slate-100 flex-1 max-w-[80px]">
                <div
                  className="h-1.5 rounded-full bg-indigo-500"
                  style={{ width: `${Math.round(field.score * 100)}%` }}
                />
              </div>
              <span className="text-xs text-slate-400">{Math.round(field.score * 100)}% match</span>
            </div>
          )}
        </div>
        <button
          onClick={() => onDeepDive(field.field_id)}
          className="shrink-0 text-xs font-medium text-indigo-600 hover:text-indigo-800 hover:underline"
        >
          Deep dive →
        </button>
      </div>
    </div>
  );
}
