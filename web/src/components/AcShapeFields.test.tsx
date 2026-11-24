import { fireEvent, render, screen } from "@testing-library/react";

import { AcShapeFields } from "./AcShapeFields";

const SHAPES = [
  { value: "range", label: "Rentang" },
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
  expect(screen.queryByRole("textbox", { name: "Nilai" })).toBeNull();

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
