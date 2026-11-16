// The shared UI primitives of spec #135: what a person sees and can do with each.
import { render, screen, within } from "@testing-library/react";

import { Button, CoveragePill, DataTable, EmptyState, Panel, SectionHeading, StatChip } from "./ui";

test("a Coverage pill reads as its label, with its shape hidden from screen readers", () => {
  render(<CoveragePill cls="conflict" label="Konflik" help="Desain tidak memenuhi URS." />);
  const pill = screen.getByText("Konflik", { exact: false });
  expect(pill.textContent).not.toBe("Konflik"); // the shape is there for the eye
  expect(pill.title).toBe("Desain tidak memenuhi URS.");
  const shape = pill.querySelector("[aria-hidden=true]");
  expect(shape?.textContent).not.toBe("");
  expect(pill.textContent).toBe(`${shape?.textContent}Konflik`);
});

test("each Coverage class has its own shape, so colour is never the only sign", () => {
  const classes = ["covered_by_vendor", "partial", "site_only", "gap", "conflict", "none"] as const;
  const { container } = render(
    <>
      {classes.map((c) => (
        <CoveragePill key={c} cls={c} label={c} />
      ))}
    </>,
  );
  const shapes = [...container.querySelectorAll("[aria-hidden=true]")].map((s) => s.textContent);
  expect(new Set(shapes).size).toBe(classes.length);
});

test("a button keeps its name and type whatever its variant", () => {
  render(
    <form>
      <Button variant="primary">Masuk</Button>
      <Button variant="soft" name="decision" value="accepted">
        Terima
      </Button>
      <Button variant="quiet" type="button">
        Batal
      </Button>
    </form>,
  );
  expect((screen.getByRole("button", { name: "Masuk" }) as HTMLButtonElement).type).toBe("submit");
  const accept = screen.getByRole("button", { name: "Terima" });
  expect(accept.getAttribute("name")).toBe("decision");
  expect(accept.getAttribute("value")).toBe("accepted");
  expect(screen.getByRole("button", { name: "Batal" }).getAttribute("type")).toBe("button");
});

test("a section heading is a level-2 heading with its count and note", () => {
  render(<SectionHeading id="ai" title="Temuan AI (saran)" count={3} note="Perlu keputusan manusia." />);
  const heading = screen.getByRole("heading", { level: 2, name: "Temuan AI (saran)" });
  expect(heading.id).toBe("ai");
  expect(screen.getByText("3")).toBeDefined();
  expect(screen.getByText("Perlu keputusan manusia.")).toBeDefined();
});

test("a panel shows its title and content", () => {
  render(
    <Panel title="Gerbang dan biaya">
      <p>Biaya run: 0.42 USD</p>
    </Panel>,
  );
  expect(screen.getByRole("heading", { name: "Gerbang dan biaya" })).toBeDefined();
  expect(screen.getByText("Biaya run: 0.42 USD")).toBeDefined();
});

test("a stat chip shows a count with its label", () => {
  render(<StatChip value={4} label="Celah" />);
  expect(screen.getByText("4")).toBeDefined();
  expect(screen.getByText("Celah")).toBeDefined();
});

test("an empty state says what is missing and why", () => {
  render(<EmptyState title="Belum ada run">Jalankan traceq run lalu traceq serve.</EmptyState>);
  expect(screen.getByText("Belum ada run")).toBeDefined();
  expect(screen.getByText("Jalankan traceq run lalu traceq serve.")).toBeDefined();
});

test("a data table is a table with its accessible name and rows", () => {
  render(
    <DataTable aria-label="Run analisis">
      <thead>
        <tr>
          <th>Peralatan</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>TP-201</td>
        </tr>
      </tbody>
    </DataTable>,
  );
  const table = screen.getByRole("table", { name: "Run analisis" });
  expect(within(table).getAllByRole("row")).toHaveLength(2);
});
