# Bedside English: Talk & Train — Landing Page

![Talk to an AI patient. In English. Out loud.](assets/social/og-cover.png)

Source for the public landing page at **https://boyskier.github.io/bedside-english/**.

A single static `index.html` (no build step) presenting both platforms of the product:

- [BedsideEnglish-Desktop](https://github.com/boyskier/BedsideEnglish-Desktop) — Windows/macOS/Linux, available now.
- [BedsideEnglish-Android](https://github.com/boyskier/BedsideEnglish-Android) — pre-launch, build from source.

Served via GitHub Pages from the `main` branch root. Edit `index.html` and push to update the live site.

`android.html` is a copy of `index.html` and differs only in its `canonical`/`og:url` and the brand link.
Keep the two in sync when you edit either.

## Assets

| Path | What it is |
| --- | --- |
| `assets/android/*.webp` | Real Android screenshots, 780px wide, Android status bar and gesture strip trimmed off. Used by the hero, the scroll tour and the screenshot rail. |
| `assets/android/detail/*.webp` | Close-up crops of the same captures, all at a 760×422 aspect, used inside the feature cards. |
| `assets/social/og-cover.png` | 1200×630 Open Graph / Twitter card. Referenced by `og:image` on both pages. |
| `assets/social/feature-graphic.png` | 1024×500 — the exact size Google Play requires for a store listing feature graphic. |
| `assets/social/share-square.png` | 1200×1200 square, for KakaoTalk / Instagram and anywhere a wide card is cropped. |
| `assets/app-*.png` | Older desktop-app screenshots, used only by `desktop/index.html`. |

The three files in `assets/social/` are one composition at three crops. Regenerate them all with:

```sh
python3 tools/build-social.py   # needs Pillow
```

Edit the copy or swap which screenshots appear in the stack at the top of that script — do not
retouch the PNGs by hand, or the three sizes will drift apart.
