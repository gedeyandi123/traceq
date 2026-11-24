import { render, screen } from "@testing-library/react";

import {
  AlertCircleIcon,
  AlertTriangleIcon,
  CheckCircleIcon,
  ChevronRightIcon,
  ExternalLinkIcon,
  FileTextIcon,
  InfoIcon,
  ShieldCheckIcon,
} from "./icons";
import { Alert, Button, Disclosure, ProgressBar, StatusBadge } from "./ui";

describe("new Phase A ui primitives", () => {
  it("renders Button danger variant as a button", () => {
    render(<Button variant="danger">Hapus</Button>);
    expect(screen.getByRole("button", { name: "Hapus" })).toBeDefined();
  });

  it("renders StatusBadge with its label", () => {
    render(<StatusBadge tone="pass">Disetujui</StatusBadge>);
    expect(screen.getByText("Disetujui")).toBeDefined();
  });

  it("renders Alert with role, title, and body", () => {
    render(
      <Alert tone="fail" role="alert" title="Gagal">
        Permintaan ditolak.
      </Alert>,
    );
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("Gagal");
    expect(alert.textContent).toContain("Permintaan ditolak.");
  });

  it("renders ProgressBar with clamped aria attributes", () => {
    render(<ProgressBar value={15} max={20} label="Progres keputusan" />);
    const bar = screen.getByRole("progressbar", { name: "Progres keputusan" });
    expect(bar.getAttribute("aria-valuenow")).toBe("15");
    expect(bar.getAttribute("aria-valuemin")).toBe("0");
    expect(bar.getAttribute("aria-valuemax")).toBe("20");
  });

  it("renders Disclosure keeping content in the DOM", () => {
    render(<Disclosure summary="Detail">Isi tersembunyi</Disclosure>);
    expect(screen.getByText("Detail")).toBeDefined();
    expect(screen.getByText("Isi tersembunyi")).toBeDefined();
  });

  it("renders all inline SVG icons as aria-hidden", () => {
    const { container } = render(
      <div>
        <CheckCircleIcon />
        <AlertTriangleIcon />
        <AlertCircleIcon />
        <InfoIcon />
        <ChevronRightIcon />
        <ExternalLinkIcon />
        <FileTextIcon />
        <ShieldCheckIcon />
      </div>,
    );
    const svgs = container.querySelectorAll("svg");
    expect(svgs.length).toBe(8);
    for (const svg of svgs) {
      expect(svg.getAttribute("aria-hidden")).toBe("true");
    }
  });
});
