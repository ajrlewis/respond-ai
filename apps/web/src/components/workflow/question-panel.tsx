import { type Tone } from "@/lib/api";

type QuestionPanelProps = {
  question: string;
  tone: Tone;
  canSubmit: boolean;
  isGeneratingDraft: boolean;
  loading: boolean;
  generationProgress: string | null;
  sampleQuestions: string[];
  onQuestionChange: (question: string) => void;
  onToneChange: (tone: Tone) => void;
  onSubmit: () => void;
};

export function QuestionPanel({
  question,
  tone,
  canSubmit,
  isGeneratingDraft,
  loading,
  generationProgress,
  sampleQuestions,
  onQuestionChange,
  onToneChange,
  onSubmit,
}: QuestionPanelProps) {
  return (
    <article className="glass-panel left-panel">
      <h2>Question Intake</h2>
      <p className="panel-subtitle">Capture the RFP prompt and desired response style.</p>

      <label className="field-label" htmlFor="question">
        RFP Question
      </label>
      <textarea
        id="question"
        value={question}
        onChange={(event) => onQuestionChange(event.target.value)}
        rows={8}
        placeholder="Enter an investor due diligence question..."
      />

      <label className="field-label" htmlFor="tone">
        Tone
      </label>
      <select id="tone" value={tone} onChange={(event) => onToneChange(event.target.value as Tone)}>
        <option value="formal">Formal investor tone</option>
        <option value="concise">Concise</option>
        <option value="detailed">Detailed</option>
      </select>

      <div className="actions-row">
        <button onClick={onSubmit} disabled={!canSubmit}>
          {isGeneratingDraft && loading ? "Running workflow..." : "Generate Draft"}
        </button>
        {isGeneratingDraft && loading && (
          <span className="inline-progress" aria-live="polite">
            {generationProgress || "Initializing workflow..."}
          </span>
        )}
      </div>

      <div className="sample-prompts">
        <p>Sample prompts</p>
        {sampleQuestions.map((sample) => (
          <button key={sample} type="button" className="sample-pill" onClick={() => onQuestionChange(sample)}>
            {sample}
          </button>
        ))}
      </div>
    </article>
  );
}
