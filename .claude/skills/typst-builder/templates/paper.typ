// 논문 번역본 Typst 템플릿
// 사용: build_pdf.py가 본 파일을 임포트하여 body.typ을 주입한다.

#let paper(
  title: "",
  orig_title: "",
  authors: "",
  source: "",
  translation_date: "",
  body,
) = {
  // 페이지 설정
  set page(
    paper: "a4",
    margin: (x: 2.2cm, y: 2.5cm),
    header: context {
      if here().page() > 1 {
        align(right, text(size: 9pt, fill: gray)[#title])
      }
    },
    footer: context {
      align(center, text(size: 9pt, fill: gray)[
        #counter(page).display()
      ])
    },
  )

  // 폰트 설정 — Noto Sans KR 통일, 영문 폴백
  set text(
    font: ("Apple SD Gothic Neo", "Noto Sans KR", "Noto Sans", "Helvetica"),
    size: 10.5pt,
    lang: "ko",
  )
  set par(
    justify: true,
    leading: 0.75em,
    first-line-indent: 0pt,
  )

  // 제목 스타일
  show heading.where(level: 1): it => {
    set text(size: 18pt, weight: "bold")
    block(above: 1.5em, below: 0.8em, it.body)
  }
  show heading.where(level: 2): it => {
    set text(size: 14pt, weight: "bold")
    block(above: 1.2em, below: 0.6em, it.body)
  }
  show heading.where(level: 3): it => {
    set text(size: 12pt, weight: "bold")
    block(above: 1em, below: 0.5em, it.body)
  }

  // 코드/모노스페이스
  show raw: set text(font: ("JetBrains Mono", "Menlo", "Courier New"), size: 9.5pt)

  // 인용 (citation 텍스트) 스타일
  // 일반 텍스트로 두되, 메인 폰트의 영문 폴백 사용

  // 그림 캡션
  show figure: set block(breakable: true)
  show figure.caption: it => {
    set text(size: 9.5pt, style: "italic")
    it
  }

  // ===== 표지 =====
  page(
    margin: (x: 3cm, y: 4cm),
    header: none,
    footer: none,
  )[
    #v(3cm)
    #align(center)[
      #text(size: 22pt, weight: "bold")[#title]
      #v(0.8em)
      #if orig_title != "" {
        text(size: 13pt, style: "italic")[#orig_title]
      }
      #v(2em)
      #if authors != "" {
        text(size: 12pt)[#authors]
        v(0.5em)
      }
      #if source != "" {
        text(size: 11pt, fill: gray)[#source]
      }
    ]
    #v(1fr)
    #align(center, text(size: 10pt, fill: gray)[
      한국어 번역본 · #translation_date
    ])
  ]

  // ===== 목차 =====
  pagebreak()
  outline(
    title: [목차],
    indent: 1em,
    depth: 3,
  )

  // ===== 본문 =====
  pagebreak()
  body
}
