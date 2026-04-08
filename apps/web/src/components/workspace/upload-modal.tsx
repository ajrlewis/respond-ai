import { useState } from "react";

import styles from "./upload-modal.module.css";

type ReviewV2UploadModalProps = {
  isOpen: boolean;
  onClose: () => void;
  onUseExamples: () => void;
  onUploadFile: (file: File) => Promise<void>;
  helperText?: string | null;
  errorText?: string | null;
};

export function ReviewV2UploadModal({
  isOpen,
  onClose,
  onUseExamples,
  onUploadFile,
  helperText,
  errorText,
}: ReviewV2UploadModalProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isOpen) return null;

  async function handleUpload() {
    if (!selectedFile || isSubmitting) return;
    setIsSubmitting(true);
    try {
      await onUploadFile(selectedFile);
      setSelectedFile(null);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className={styles.overlay} role="dialog" aria-modal="true" aria-label="Upload document">
      <div className={styles.modal}>
        <div className={styles.header}>
          <h2>Upload document</h2>
          <button type="button" className={styles.ghostButton} onClick={onClose}>
            Close
          </button>
        </div>

        <p className={styles.helper}>Upload a source file or load default example questions.</p>

        <label className={styles.fieldLabel} htmlFor="upload-document-input">
          Source file
        </label>
        <input
          id="upload-document-input"
          type="file"
          accept=".pdf,.md,.markdown,.txt"
          onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
        />

        {selectedFile ? <p className={styles.helper}>Selected: {selectedFile.name}</p> : null}
        {helperText ? <p className={styles.helper}>{helperText}</p> : null}
        {errorText ? <p className={styles.error}>{errorText}</p> : null}

        <div className={styles.actions}>
          <button
            type="button"
            onClick={handleUpload}
            disabled={!selectedFile || isSubmitting}
          >
            {isSubmitting ? "Loading..." : "Use uploaded file"}
          </button>
          <button type="button" className={styles.secondaryButton} onClick={onUseExamples}>
            Use example questions
          </button>
        </div>
      </div>
    </div>
  );
}
