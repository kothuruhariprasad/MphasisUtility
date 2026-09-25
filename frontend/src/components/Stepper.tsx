const labels = ["Import", "Connect LLM", "Select Intents", "Generate", "Download"];

export default function Stepper({ step }: { step: number }) {
  return (
    <div className="stepper">
      {labels.map((label, i) => {
        const idx = i + 1;
        const state = idx < step ? "done" : idx === step ? "active" : "upcoming";
        return (
          <div key={label} className={`stepper-item ${state}`}>
            <div className="stepper-circle">{idx < step ? "✓" : idx}</div>
            <div className="stepper-label">{label}</div>
          </div>
        );
      })}
    </div>
  );
}