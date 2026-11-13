// URS written as prose and unnumbered tables (TP-202 layout). No requirement numbers:
// each section has an opening sentence, a paragraph of requirement sentences, and an
// optional table. All text comes from render.py; each requirement span records its page.

#import "common.typ": place
#let d = json(bytes(sys.inputs.data))

#set document(title: d.doc_id + " rev " + str(d.rev), author: d.signatures.at(0).name)
#set text(lang: "id", size: 10.5pt, hyphenate: false)
#set par(justify: false, leading: 0.7em, spacing: 1.1em)
#set page(
  paper: "a4",
  margin: (x: 2.4cm, top: 3cm, bottom: 2.2cm),
  header: [
    #set text(size: 8.5pt)
    #d.doc_id #h(1fr) Revisi #d.rev #h(1fr) #context [#counter(page).get().first() / #counter(page).final().first()]
    #line(length: 100%, stroke: 0.4pt)
  ],
)
#set table(stroke: (x, y) => if y == 0 { (bottom: 0.8pt) } else { (bottom: 0.3pt) }, inset: 6pt)
#show heading: set block(above: 1.4em, below: 0.7em)
#show heading: set text(size: 11.5pt)
#set heading(numbering: "1.")

#text(size: 15pt, weight: "bold")[#d.title]
#v(0.2em)
#text(size: 11pt)[#d.equipment]
#v(0.6em)
Nomor dokumen #d.doc_id, revisi #d.rev, berlaku sejak #d.issued_on.

#heading(numbering: none)[Pendahuluan]
#d.purpose

#for s in d.sections [
  #heading[#s.title]
  #if s.intro != "" [#s.intro ]#for r in s.prose [#r.text#place(r.key) ]
  #if s.rows.len() > 0 {
    table(
      columns: (4.2cm, 1fr, 1.4cm),
      table.header([*Aspek*], [*Kebutuhan*], [*Kritis*]),
      ..s.rows.map(r => ([#r.label], [#r.text#place(r.key)], [#r.critical])).flatten(),
    )
  }
]

#heading(numbering: none)[Riwayat dokumen]
Revisi #d.rev, #d.issued_on: #d.note

#heading(numbering: none)[Persetujuan]
#table(
  columns: (3.2cm, 1fr, 1fr, 2.6cm),
  table.header([*Peran*], [*Nama*], [*Tanda tangan*], [*Tanggal*]),
  ..d.signatures.map(s => ([#s.role], [#s.name], [#emph[#s.signature]], [#s.date])).flatten(),
)
