import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { stepFrom } from "@/protocol/form";
import { AcShapeFields } from "./AcShapeFields";

const SHAPES = [
  { value: "range", label: "Rentang" },
  { value: "exclusive_range", label: "Rentang eksklusif" },
  { value: "tolerance", label: "Toleransi" },
  { value: "number", label: "Angka" },
  { value: "one_of", label: "Salah satu" },
  { value: "present", label: "Harus ada" },
];

const LABELS = {
  legend: "Kriteria penerimaan",
  shape: "Bentuk",
  chooseShape: "Pilih bentuk",
  min: "Batas bawah",
  max: "Batas atas",
  minExclusive: "Eksklusif (>)",
  maxExclusive: "Eksklusif (<)",
  nominal: "Nilai nominal",
  tolerance: "Toleransi (±)",
  toleranceUnit: "Satuan toleransi (% atau sama dengan satuan)",
  value: "Nilai",
  unit: "Satuan",
  allowed: "Nilai yang diizinkan",
  hint: "Isi sesuai bentuk terpilih.",
};

test("shows only the inputs matching the selected AC shape", () => {
  render(
    <AcShapeFields
      id="test"
      initialShape=""
      initialMin=""
      initialMax=""
      initialValue=""
      initialUnit=""
      initialAllowed=""
      shapes={SHAPES}
      labels={LABELS}
    />,
  );
  const select = screen.getByRole("combobox", { name: "Bentuk" }) as HTMLSelectElement;
  expect(screen.queryByRole("textbox", { name: "Batas bawah" })).toBeNull();
  expect(screen.queryByRole("textbox", { name: "Nilai" })).toBeNull();
  expect(screen.queryByRole("textbox", { name: "Nilai yang diizinkan" })).toBeNull();

  fireEvent.change(select, { target: { value: "range" } });
  expect(screen.getByRole("textbox", { name: "Batas bawah" })).toBeDefined();
  expect(screen.getByRole("textbox", { name: "Batas atas" })).toBeDefined();
  expect(screen.getByRole("textbox", { name: "Satuan" })).toBeDefined();
  expect(screen.queryByRole("checkbox", { name: "Eksklusif (>)" })).toBeNull();
  expect(screen.queryByRole("textbox", { name: "Nilai" })).toBeNull();

  fireEvent.change(select, { target: { value: "exclusive_range" } });
  expect(screen.getByRole("textbox", { name: "Batas bawah" })).toBeDefined();
  expect(screen.getByRole("checkbox", { name: "Eksklusif (>)" })).toBeDefined();
  expect(screen.getByRole("textbox", { name: "Batas atas" })).toBeDefined();
  expect(screen.getByRole("checkbox", { name: "Eksklusif (<)" })).toBeDefined();
  expect(screen.getByRole("textbox", { name: "Satuan" })).toBeDefined();

  fireEvent.change(select, { target: { value: "tolerance" } });
  expect(screen.getByRole("textbox", { name: "Nilai nominal" })).toBeDefined();
  expect(screen.getByRole("textbox", { name: "Toleransi (±)" })).toBeDefined();
  expect(
    screen.getByRole("textbox", { name: "Satuan toleransi (% atau sama dengan satuan)" }),
  ).toBeDefined();
  expect(screen.getByRole("textbox", { name: "Satuan" })).toBeDefined();
  expect(screen.queryByRole("textbox", { name: "Batas bawah" })).toBeNull();

  fireEvent.change(select, { target: { value: "number" } });
  expect(screen.getByRole("textbox", { name: "Nilai" })).toBeDefined();
  expect(screen.getByRole("textbox", { name: "Satuan" })).toBeDefined();
  expect(screen.queryByRole("textbox", { name: "Batas bawah" })).toBeNull();

  fireEvent.change(select, { target: { value: "one_of" } });
  expect(screen.getByRole("textbox", { name: "Nilai yang diizinkan" })).toBeDefined();
  expect(screen.queryByRole("textbox", { name: "Satuan" })).toBeNull();

  fireEvent.change(select, { target: { value: "present" } });
  expect(screen.queryByRole("textbox")).toBeNull();
});

test("round-trips exclusive_range (< 0,8 µm) exactly through form submission and stepFrom", async () => {
  const user = userEvent.setup();
  const { container } = render(
    <form>
      <input name="description" defaultValue="Ukur kekasaran permukaan." />
      <input name="method" defaultValue="Ukur dengan roughness tester." />
      <AcShapeFields
        id="ex-roundtrip"
        initialShape="exclusive_range"
        initialMin=""
        initialMax={0.8}
        initialMinExclusive={false}
        initialMaxExclusive={true}
        initialValue=""
        initialUnit="µm"
        initialAllowed=""
        shapes={SHAPES}
        labels={LABELS}
      />
    </form>,
  );

  const form = container.querySelector("form")!;
  expect(stepFrom(new FormData(form))?.acceptance).toEqual({
    type: "exclusive_range",
    min: null,
    max: 0.8,
    min_exclusive: false,
    max_exclusive: true,
    unit: "µm",
  });

  // Also test entering < 0,8 µm from blank state via user interaction
  const maxInput = screen.getByRole("textbox", { name: "Batas atas" });
  await user.clear(maxInput);
  await user.type(maxInput, "0,8");
  expect(stepFrom(new FormData(form))?.acceptance).toEqual({
    type: "exclusive_range",
    min: null,
    max: 0.8,
    min_exclusive: false,
    max_exclusive: true,
    unit: "µm",
  });
});

test("round-trips tolerance (380 V ± 10 %) exactly through form submission and stepFrom", async () => {
  const user = userEvent.setup();
  const { container } = render(
    <form>
      <input name="description" defaultValue="Ukur tegangan suplai." />
      <input name="method" defaultValue="Ukur dengan multimeter." />
      <AcShapeFields
        id="tol-roundtrip"
        initialShape="tolerance"
        initialMin=""
        initialMax=""
        initialNominal={380}
        initialTolerance={10}
        initialToleranceUnit="%"
        initialValue=""
        initialUnit="V"
        initialAllowed=""
        shapes={SHAPES}
        labels={LABELS}
      />
    </form>,
  );

  const form = container.querySelector("form")!;
  expect(stepFrom(new FormData(form))?.acceptance).toEqual({
    type: "tolerance",
    nominal: 380,
    tolerance: 10,
    tolerance_unit: "%",
    unit: "V",
  });

  // Switch tolerance to same unit (380 V ± 5 V)
  const tolInput = screen.getByRole("textbox", { name: "Toleransi (±)" });
  const tolUnitInput = screen.getByRole("textbox", {
    name: "Satuan toleransi (% atau sama dengan satuan)",
  });
  await user.clear(tolInput);
  await user.type(tolInput, "5");
  await user.clear(tolUnitInput);
  await user.type(tolUnitInput, "V");

  expect(stepFrom(new FormData(form))?.acceptance).toEqual({
    type: "tolerance",
    nominal: 380,
    tolerance: 5,
    tolerance_unit: "V",
    unit: "V",
  });
});
