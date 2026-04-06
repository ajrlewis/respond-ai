import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "@/components/workflow/status-badge";

describe("StatusBadge", () => {
  it("shows idle when no status is available", () => {
    render(<StatusBadge status={null} />);

    expect(screen.getByText("Idle")).toBeInTheDocument();
  });

  it("renders mapped status labels", () => {
    render(<StatusBadge status="awaiting_finalization" />);

    expect(screen.getByText("Finalization In Progress")).toBeInTheDocument();
  });
});
