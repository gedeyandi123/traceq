// The shared UI primitives of spec #135: what a person sees and can do with each.
import { render, screen, within } from "@testing-library/react";

import { Button, DataTable, EmptyState, ModeBadge, SectionHeading } from "./ui";

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
  render(
    <SectionHeading id="ai" title="Temuan AI (saran)" count={3} note="Perlu keputusan manusia." />,
  );
  const heading = screen.getByRole("heading", { level: 2, name: "Temuan AI (saran)" });
  expect(heading.id).toBe("ai");
  expect(screen.getByText("3")).toBeDefined();
  expect(screen.getByText("Perlu keputusan manusia.")).toBeDefined();
});

test("a mode badge shows the run's mode", () => {
  render(<ModeBadge>Putar ulang</ModeBadge>);
  expect(screen.getByText("Putar ulang")).toBeDefined();
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
