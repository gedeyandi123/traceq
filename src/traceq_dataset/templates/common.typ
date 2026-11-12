// Shared helpers for all document templates.

// Records the page of a string the answer key relies on; render.py queries <placed>.
#let place(key) = context [#metadata((key: key, page: here().page()))<placed>]

// A table whose rows are arrays of cells.
#let rows-table(columns, header, rows) = table(
  columns: columns,
  table.header(..header.map(h => strong(h))),
  ..rows.flatten(),
)
