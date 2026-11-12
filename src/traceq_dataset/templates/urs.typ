// URS / SKP layout. All text and formatting come from render.py via sys.inputs.data;
// this file only lays it out. Each requirement row records its page (place()).

#import "common.typ": place, rows-table
#let d = json(bytes(sys.inputs.data))

#set document(title: d.doc_id + " rev " + str(d.rev), author: d.signatures.at(0).name)
#set text(lang: "id", size: 10pt, hyphenate: false)
#set par(justify: false)
#set page(
  paper: "a4",
  margin: (x: 2cm, top: 2.8cm, bottom: 2cm),
  header: grid(
    columns: (1fr, auto),
    [#d.title_short],
    context [#d.doc_id · Rev. #d.rev · Halaman #counter(page).get().first() dari #counter(page).final().first()],
  ),
)
#set table(stroke: 0.5pt, inset: 5pt)
#show heading: set block(above: 1.2em, below: 0.6em)
#show heading: set text(size: 11pt)

#align(center, text(size: 14pt, weight: "bold")[#d.title])
#v(0.5em)

#table(
  columns: (4cm, 1fr),
  [Nomor dokumen], [#d.doc_id],
  [Revisi], [#d.rev],
  [Tanggal berlaku], [#d.issued_on],
  [Peralatan], [#d.equipment],
)

#heading(numbering: none)[Tujuan]
#d.purpose

#for s in d.sections [
  #heading(numbering: none)[#s.title]
  #table(
    columns: (3cm, 1.4cm, 1fr),
    table.header([*No.*], [*Kritis*], [*Persyaratan*]),
    ..s.requirements.map(r => (
      [#r.id#place(r.id)],
      [#r.critical],
      [#r.text],
    )).flatten(),
  )
]

#heading(numbering: none)[Riwayat revisi]
#table(
  columns: (1.4cm, 2.6cm, 1fr),
  table.header([*Rev.*], [*Tanggal*], [*Keterangan*]),
  ..d.history.map(h => ([#h.rev], [#h.date], [#h.note])).flatten(),
)

#heading(numbering: none)[Pengesahan]
#table(
  columns: (3.2cm, 1fr, 1fr, 2.6cm),
  table.header([*Peran*], [*Nama*], [*Tanda tangan*], [*Tanggal*]),
  ..d.signatures.map(s => ([#s.role], [#s.name], [#emph[#s.signature]], [#s.date])).flatten(),
)
