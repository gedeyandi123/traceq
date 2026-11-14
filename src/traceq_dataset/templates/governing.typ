// Governing site documents (Indonesian, born-digital): the Validation Master Plan and the
// qualification SOP. All text comes from render.py; this file only lays it out. A section
// has paragraphs (a string, or key + text to record its page) and an optional table whose
// rows may carry a key, placed in the row's first cell.

#import "common.typ": place, rows-table
#let d = json(bytes(sys.inputs.data))

#set document(title: d.doc_id + " rev " + str(d.rev), author: d.site)
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
#set heading(numbering: "1.")

#align(center, text(size: 14pt, weight: "bold")[#d.title])
#v(0.5em)
#table(
  columns: (4cm, 1fr),
  [Nomor dokumen], [#d.doc_id],
  [Revisi], [#d.rev],
  [Tanggal berlaku], [#d.issued_on],
  [Lokasi], [#d.site],
)

#for s in d.sections [
  = #s.title
  #for p in s.at("paragraphs", default: ()) [
    #if type(p) == str [#p] else [#p.text#place(p.key)]

  ]
  #if "table" in s {
    let t = s.table
    rows-table(
      t.columns.map(c => c * 1fr),
      t.header.map(h => [#h]),
      t.rows.map(r => r.cells.enumerate().map(((i, c)) => if i == 0 and "key" in r [#c#place(r.key)] else [#c])),
    )
  }
]

#heading(numbering: none)[Riwayat revisi]
#rows-table(
  (1.4cm, 2.6cm, 1fr),
  ([Rev.], [Tanggal], [Keterangan]),
  d.history.map(h => ([#h.rev], [#h.date], [#h.note])),
)

#heading(numbering: none)[Pengesahan]
#rows-table(
  (3.2cm, 1fr, 1fr, 2.6cm),
  ([Peran], [Nama], [Tanda tangan], [Tanggal]),
  d.signatures.map(s => ([#s.role], [#s.name], [#emph[#s.signature]], [#s.date])),
)
