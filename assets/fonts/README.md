# Vendored webfonts

Latin subsets used only by the Instagram card renderer
(`tools/instagram_card_templates/card.css`). They are committed rather than
fetched so `tools/render-instagram-cards.py` produces the same cards offline and
on any machine.

| File | Family | Source | License |
| --- | --- | --- | --- |
| `instrument-serif-latin.woff2` | Instrument Serif, 400 | Google Fonts `css2` latin subset | SIL Open Font License 1.1 |
| `inter-latin.woff2` | Inter, variable 100–900 | Google Fonts `css2` latin subset | SIL Open Font License 1.1 |

Both faces are already named in `tokens.css` (`--font-display`, `--font-body`),
so a card and the guide it links to are set in the same type.

To refresh, request the `css2` API with a browser user agent, keep the `latin`
`@font-face` blocks, and download the `.woff2` each one points at. Inter ships a
single variable file covering every weight.
