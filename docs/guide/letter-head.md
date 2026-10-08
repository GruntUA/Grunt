# Letterheads and QR codes in print

A **Letter Head** is the organisation's letterhead: logo, name and details at
the top, an optional footer at the bottom. Set it up once and every printed
document and PDF gets it. You don't have to copy it into each print format.

## Setting up

Desk → **Letter Head** → new:

- **Logo**: an uploaded image. Templates use it as `{{ letter_head.logo }}`. It is
  embedded as a `data:` URI, so it shows in the PDF as well.
- **Header HTML / Footer HTML**: Jinja templates. They have access to `doc` (the
  printed document), `letter_head.logo`, `site_url` and `now`, plus every print
  filter (`date_format`, `decline_name`, `qr`, …).
- **Default**: used by every print format that doesn't pick its own. Only one
  letterhead can be the default; marking a new one clears the old flag.

On a **Print Format**:

- **Letter Head**: pick a specific letterhead. Leave it empty to use the default.
- **Without letter head**: the format already draws its own header, or must
  print bare.

## Placement

The header goes right after `<body>` and the footer right before `</body>`.

To place it yourself, for example inside a table or beside a registration
stamp, use the variable in the template. When a template mentions
`letter_head`, nothing is inserted automatically:

```html
<body>
  <table><tr>
    <td>{{ letter_head.header }}</td>
    <td>{{ doc.reg_number }}<br>{{ doc.reg_date | date_format }}</td>
  </tr></table>
  …
  {{ letter_head.footer }}
</body>
```

`letter_head` is `None` when the format opts out or no letterhead is
configured. Guard with `{% if letter_head %}` when the template is shared.

## QR codes

The `qr` filter renders any text or link as an embedded SVG image:

```html
{{ doc.reg_number | qr }}                       {# 30 mm square #}
{{ (site_url ~ "/some/page?id=" ~ doc.name) | qr("20mm") }}  {# any URL you serve #}
```

## From code

`render_print_html(doctype, doc, print_format=None)` in `grunt.print.renderer`
returns exactly what the print button shows: the format, or the standard
template, with its letterhead. Use it for app-level PDFs (`html_to_pdf`) so
an emailed copy looks the same as the printed one.
