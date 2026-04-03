export function WorkflowHeader() {
  return (
    <header className="page-header">
      <div className="brand-row">
        <span className="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" role="img">
            <path
              d="M12 2.5 20 7v10l-8 4.5L4 17V7l8-4.5Zm0 3.1L6.7 8.6v6.8l5.3 3 5.3-3V8.6L12 5.6Zm-3 7.1h5.2a1.8 1.8 0 1 0 0-3.6H9v1.8h5.1a.5.5 0 0 1 0 1H9v1.8Z"
              fill="currentColor"
            />
          </svg>
        </span>
        <h1>RespondAI</h1>
      </div>
      <p className="page-tagline">Draft, review, and approve investor-grade RFP/DDQ responses with evidence grounding.</p>
    </header>
  );
}
