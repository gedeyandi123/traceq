// Site OQ Protocol Draft of a Review Package (Indonesian). All text comes from
// review_package.py via sys.inputs.data; this file only lays it out. It imports nothing the
// Equipment templates define, so they stay untouched.

#let d = json(bytes(sys.inputs.data))

// Records the page and vertical position (pt from the top) of a string the answer key relies
// on, so the validator can check it sits in the page body, not in the running header or footer.
#let place(key) = context [#metadata((key: key, page: here().page(), y: here().position().y.pt()))<placed>]

#set document(title: d.doc_id + " rev " + str(d.rev), author: d.prepared_by)
#set text(lang: "id", size: 9.5pt, hyphenate: false)
#set par(justify: false)
#set page(
  paper: "a4",
  margin: (x: 2cm, top: d.margin.top * 1cm, bottom: d.margin.bottom * 1cm),
  header: grid(
    columns: (1fr, auto),
    [#d.title_short],
    context [#d.doc_id · Rev. #d.rev · Halaman #counter(page).get().first() dari #counter(page).final().first()],
  ),
  footer: align(center, text(size: 8pt)[#d.footer]),
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
  [Status], [#d.status],
  [Tanggal], [#d.issued_on],
  [Peralatan], [#d.equipment],
  [Nomor seri], [#d.serial],
  [Acuan], [#d.urs],
)

#heading(numbering: none)[1. Tujuan]
#d.purpose

#heading(numbering: none)[2. Ruang lingkup]
#d.scope

#heading(numbering: none)[3. Ketentuan umum]
#for line in d.general [- #line
]

#heading(numbering: none)[4. Langkah uji]
#for s in d.steps [
  #block(breakable: false, below: 1.1em)[
    #table(
      columns: (3.6cm, 1fr),
      [*Langkah uji*], [*#s.id*#place(s.id + ".id")],
      [Judul], [#s.title],
      [Persyaratan SKP], [#s.requirement#place(s.id + ".requirement")],
      [Metode], [#s.method],
      [Kriteria penerimaan], [#s.acceptance#place(s.id + ".acceptance")],
      [Hasil], [],
      [Lulus/Gagal], [],
      [Keterangan], [#s.remarks#if s.remarks_key != none { place(s.remarks_key) }],
    )
    #if s.small_print != none [
      #v(-0.4em)
      #text(size: 7pt)[#s.small_print#place(s.small_print_key)]
    ]
  ]
]

#heading(numbering: none)[5. Matriks ketertelusuran]
#table(
  columns: (3.2cm, 1fr, 2.6cm),
  table.header([*No. SKP*], [*Uraian*], [*Langkah uji*]),
  ..d.trace.map(r => (
    [#r.requirement#place("trace." + r.requirement + ".requirement")],
    [#r.title],
    [#r.steps#place("trace." + r.requirement + ".steps")],
  )).flatten(),
)

#heading(numbering: none)[6. Pengesahan]
#table(
  columns: (3.2cm, 1fr, 1fr, 2.6cm),
  table.header([*Peran*], [*Nama*], [*Tanda tangan*], [*Tanggal*]),
  ..d.signatures.map(s => ([#s.role], [#s.name], [], [])).flatten(),
)
