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
| `assets/android/*.webp` | Real Android screenshots, 780px wide, Android status bar and gesture strip trimmed off. Used by the practice-loop phone and the screenshot rail. |
| `assets/android/detail/*.webp` | Close-up crops of the same captures. `hero-checklist` and `correction-wide` are cut by `tools/build-crops.py`; the rest are older 760×422 crops. |
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

The hero's magnified checklist and the full-width correction band are straight crops of captures
already in the repo. Re-cut them after replacing either source capture:

```sh
python3 tools/build-crops.py    # needs Pillow
```

## Two switches at the top of the page script

Both live at the top of the `<script>` block in `android.html` (and its `index.html` copy):

| Constant | What it does while empty | What to paste in |
| --- | --- | --- |
| `GOOGLE_PLAY_URL` | The two launch-status lines and the phone bar read "Under Google Play review". | The public listing URL. Every one of them becomes a "Get it on Google Play" link. |
| `VOICE_CLIP_URL` | The hero button replays the silent clip and reads "Watch the 8-second clip". | A path to eight seconds of the encounter's **own** audio. The button becomes "Hear 8 seconds of it" and doubles as a mute toggle. |

`VOICE_CLIP_URL` is deliberately empty rather than wired to speech synthesis. The page's whole claim
is that everything on it is the real app, and a browser text-to-speech voice would be the one thing
on it that is not — it would also sound nothing like the voice the app actually uses. Record it by
screen-capturing an encounter with internal audio capture enabled, then export the audio alone:

```sh
ffmpeg -i encounter.mp4 -ss 0 -t 8 -vn -c:a aac -b:a 96k assets/audio/encounter-8s.m4a
```
