// URS as a requirements matrix: one table per section, each row the document's own clause
// number, one or two requirement sentences and the criticality. No key ids are printed.
// All text, labels included, comes from render.py in the document language. Rows never
// break across pages; each requirement sentence records its page.

#import "common.typ": place
#let d = json(bytes(sys.inputs.data))
#let l = d.labels

#set document(title: d.doc_id + " rev " + str(d.rev), author: d.signatures.at(0).name)
#set text(lang: d.lang, size: 10pt, hyphenate: false)
#set par(justify: false)
#set page(
  paper: "a4",
  margin: (x: 2cm, top: 2.8cm, bottom: 2cm),
  header: grid(
    columns: (1fr, auto),
    [#l.title],
    context [#d.doc_id · Rev. #d.rev · #l.page #counter(page).get().first() #l.of #counter(page).final().first()],
  ),
)
#set table(stroke: 0.5pt, inset: 5pt)
#set table.cell(breakable: false)
#show heading: set block(above: 1.2em, below: 0.6em)
#show heading: set text(size: 11pt)

#align(center, text(size: 14pt, weight: "bold")[#l.title])
#v(0.5em)

#table(
  columns: (4cm, 1fr),
  [#l.doc_no], [#d.doc_id],
  [#l.revision], [#d.rev],
  [#l.issued], [#d.issued_on],
  [#l.equipment], [#d.equipment],
)

#heading(numbering: none)[#l.purpose]
#d.purpose

#for s in d.sections [
  #heading(numbering: none)[#s.title]
  #table(
    columns: (1.6cm, 1fr, 1.6cm),
    table.header([*#l.clause*], [*#l.requirement*], [*#l.critical*]),
    ..s.rows.map(r => (
      [#r.clause],
      [#r.sentences.map(x => [#x.text#place(x.key)]).join([ ])],
      [#r.critical],
    )).flatten(),
  )
]

#heading(numbering: none)[#l.history]
#table(
  columns: (1.4cm, 2.6cm, 1fr),
  table.header([*Rev.*], [*#l.date*], [*#l.note*]),
  ..d.history.map(h => ([#h.rev], [#h.date], [#h.note])).flatten(),
)

#heading(numbering: none)[#l.approval]
#table(
  columns: (3.2cm, 1fr, 1fr, 2.6cm),
  table.header([*#l.role*], [*#l.name*], [*#l.signature*], [*#l.date*]),
  ..d.signatures.map(s => ([#s.role], [#s.name], [#emph[#s.signature]], [#s.date])).flatten(),
)
