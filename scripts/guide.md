# 🎬 Backdrop Automation

> Auto-generate stunning 1080p movie & TV backdrop grids — powered by TMDB, Fanart.tv, and MDBList. Runs monthly via GitHub Actions. Zero manual work.

---

## Credits

| Contribution | Source |
|---|---|
| Rendering engine + Fanart logic | [`luckynumb3rs/stremio-perfect-setup`](https://github.com/luckynumb3rs/stremio-perfect-setup) → `backdrop.py` |
| MDBList fetch + adult filter | [`bramst0ne/prism-wallpapers`](https://github.com/bramst0ne/prism-wallpapers) → `backdrop_T2_flat.py` |
| Accent colour extraction | [`luckynumb3rs/stremio-perfect-setup`](https://github.com/luckynumb3rs/stremio-perfect-setup) → `accent.py` |

---

## How It Works

Every **1st of the month**, GitHub Actions runs `generate.py`, which:

1. Reads `backdrop-config.json`
2. For each entry — resolves accent colour automatically
3. Fetches titles from TMDB sources, MDBList, or both mixed
4. Downloads thumbnails — **Fanart.tv first**, TMDB as fallback
5. Composites a **1080p tilted landscape-only grid**
6. Applies gradient overlay *(unless `no_accent: true`)*
7. Saves directly as **WebP** — no `.jpg` written at any point
8. Commits everything back to your repo

> **`generate.py` is fully self-contained** — one script, no subprocesses, no external scripts called at runtime. `accent.py` and `backdrop.py` stay in the repo for reference only and are not executed.

---

## File Structure

```
scripts/
  generate.py           ← the only script that runs — handles everything
  accent.py             ← kept for reference, not called at runtime
  backdrop.py           ← kept for reference, not called at runtime
  backdrop-config.json  ← YOUR config — the only file you ever edit

.github/workflows/
  generate-backdrops.yml  ← GitHub Action — do not edit
```

---

## GitHub Secrets Required

Add secrets at: **Your repo → Settings → Secrets and variables → Actions → New repository secret**

| Secret | Required | Purpose |
|---|---|---|
| `TMDB_API_KEY` | ✅ Required | Every entry needs this |
| `FANART_API_KEY` | Optional | Significantly better thumbnail quality when set |
| `MDBLIST_API_KEY` | Conditional | Only needed for entries that have `mdblist_url` |

---

## Accent Colour — Fully Automatic

You never need to set a colour manually. The script resolves it automatically for every entry using this priority chain:

| Priority | Condition | Result |
|---|---|---|
| 1 | `"no_accent": true` | Skip gradient entirely — pure tile grid |
| 2 | `"accent_color"` set in config | Use that exact colour, skip everything else |
| 3 | `"logo"` file exists | Scan image, extract dominant vibrant colour |
| 4 | Logo set but file missing | Fall through to next priority |
| 5 | No logo at all | Generate vibrant colour from label name |

**In practice:**

- Streaming entry with logo file → colour extracted from the logo image ✅
- MDBList entry, no logo → vibrant colour from the label string ✅
- Trending / genre, no logo → vibrant colour from `"Trending"` etc. ✅
- Any entry with `no_accent: true` → no overlay at all, pure grid ✅

---

## All Config Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | string | **required** | Unique slug — lowercase, hyphens only |
| `label` | string | **required** | Display name, used for fallback accent too |
| `output` | string | **required** | Output path for the saved `.webp` file |
| `sources` | array | optional | TMDB source strings (see [Sources](#sources--complete-format-reference)) |
| `mdblist_url` | string or array | optional | `"username/list-slug"`, full mdblist.com URL, or an array of either for multiple lists |
| `sort` | string | `"score.desc"` | MDBList sort order (see [MDBList Sort](#mdblist-sort-options)) |
| `logo` | string | optional | Path to logo image for auto accent extraction |
| `accent_color` | string | optional | Manual override — `"R,G,B"` or `"#RRGGBB"` |
| `no_accent` | bool | `false` | Skip all shadows and gradient overlay entirely — pure tile grid |
| `shadow_only` | bool | `false` | Apply dark UI shadows but no colour glow — useful for neutral/clean entries |
| `focus` | string | `"center-right"` | Focal point preset or `"x,y"` custom values (see [Focus Options](#focus-options)) |
| `count` | int | `60` | Max titles after merging all sources |
| `fanart` | bool | `true` | Use Fanart.tv for higher quality thumbnails |

> At least one of `"sources"` or `"mdblist_url"` must be present per entry. Both can be set together for a mixed entry.

> When `mdblist_url` is an array, each list is fetched separately and results are round-robin interleaved before deduplication.

---

## Gradient — How the Math Works

The gradient system is the visual heart of each backdrop. Using **NumPy**, the entire 1920×1080 canvas is treated as a mathematical grid — no pixel-by-pixel loops. Four layers are composited on top of each other in order: three dark shadow layers first, then the colour glow on top.

**Variable reference:**

| Variable | Meaning |
|---|---|
| `w`, `h` | Total canvas width and height (1920 × 1080) |
| `xg`, `yg` | X and Y coordinate grids — every pixel has a known position |
| `diag` | Corner-to-corner diagonal distance (~2203px at 1080p) |
| `np.clip(value, min, max)` | Hard clamp — keeps values inside a defined range no matter what |

---

### Layer 1 — Left Shadow

A horizontal linear fade that darkens the left side of the canvas. This is where UI text or a logo sits in most Stremio layouts, so it needs a clean dark base.

```python
mix_left   = np.clip(1.0 - xg / (w * 0.60), 0.0, 1.0)
alpha_left = np.clip(220 * (mix_left ** 1.2), 0, 255)
left_img   = _create_layer(6, 6, 8, alpha_left)
```

| Knob | Value | What it does | Customise |
|---|---|---|---|
| **Spread** | `w * 0.60` | Shadow covers 60% of the canvas width from the left edge. The right 40% is completely unaffected. | Narrower: `0.40` — tighter shadow, more grid stays bright. Wider: `0.80` — shadow bleeds far right. |
| **Fade direction** | `1.0 - ...` | Inverts the math so the left edge is fully opaque (`1.0`) and fades to transparent at the spread boundary. | Don't change — flipping this would darken the right side instead. |
| **Curve** | `** 1.2` | Exponential easing. Controls how quickly the shadow falls off — higher values stay dark longer then drop fast. | Linear: `** 1.0`. Heavy ease: `** 2.0` — hugs the left edge, fades very fast. |
| **Intensity** | `220 *` | Peak opacity at the left edge — 220/255, near-black but not fully opaque. | Lighter: `160` — grid bleeds through softly. Full black edge: `255`. |
| **Shadow colour** | `(6, 6, 8)` | RGB of the shadow layer — a near-black charcoal blue. Shared with layers 2 and 3. | Pure black: `(0, 0, 0)`. Dark navy: `(4, 6, 18)`. |

---

### Layer 2 — Bottom Shadow

A vertical linear fade that darkens the bottom portion of the canvas. Works together with the left shadow to create a dark lower-left anchor area.

```python
mix_bottom   = np.clip((yg - h * 0.40) / (h * 0.60), 0.0, 1.0)
alpha_bottom = np.clip(220 * (mix_bottom ** 1.2), 0, 255)
bottom_img   = _create_layer(6, 6, 8, alpha_bottom)
```

| Knob | Value | What it does | Customise |
|---|---|---|---|
| **Start point** | `h * 0.40` | Shadow stays invisible for the top 40% of the screen. Anything above this line is clipped to `0.0`. | Earlier: `0.20` — shadow begins higher up. Later: `0.60` — only the bottom 40% gets dark. |
| **Spread** | `/ (h * 0.60)` | The fade fills the remaining 60% of canvas height below the start point. | Start point + spread should always sum to `1.0`. E.g. start `0.50` → spread `/ (h * 0.50)`. |
| **Curve & Intensity** | `** 1.2` / `220 *` | Intentionally matched to the left shadow to keep both layers visually balanced. | Heavier bottom: `255 * (mix ** 1.5)`. Change both shadows together if adjusting. |

---

### Layer 3 — Bottom-Left Corner Vignette

A radial (circular) darkness anchored to the bottom-left corner. Adds depth beyond what the two linear shadows achieve — creates the feeling of the image receding into the corner.

```python
dist_bl  = np.hypot(xg, h - yg)
mix_bl   = np.clip(1.0 - (dist_bl / diag) / 0.75, 0.0, 1.0)
alpha_bl = np.clip(255 * (mix_bl ** 1.8), 0, 255)
```

| Knob | Value | What it does | Customise |
|---|---|---|---|
| **Shape** | `np.hypot(xg, h - yg)` | Pythagorean distance from every pixel to the bottom-left corner. `h - yg` flips the Y axis so distance is measured from the bottom — produces a circle, not a line. | Move to bottom-right: `np.hypot(w - xg, h - yg)`. Top-left: `np.hypot(xg, yg)`. |
| **Spread** | `/ 0.75` | Circular zone reaches 75% of the diagonal. Smaller = tight corner dot. Larger = darkness bleeds across the image. | Tight: `/ 0.45`. Expansive: `/ 1.0` — covers the entire canvas diagonally. |
| **Curve** | `** 1.8` | Higher than the linear shadows. Darkness is extremely concentrated at the corner and drops off aggressively — keeps the image centre clean. | Gentle vignette: `** 1.2`. Extreme dot: `** 3.0` — tiny pitch-black spot only. |
| **Intensity** | `255 *` | Maximum opacity at the corner pixel. Combined with the high curve, creates a convincing depth anchor without overwhelming the rest of the image. | Reduce to `200` if the corner looks crushed. |

---

### Layer 4 — Top-Right Accent Glow

The only coloured layer. A radial glow in the accent colour anchored to the top-right corner, then blurred into a soft atmospheric haze. This is what gives each backdrop its unique colour identity.

```python
dist_tr  = np.hypot(w - xg, yg)
mix_tr   = np.clip(1.0 - (dist_tr / diag) / 0.40, 0.0, 1.0)
alpha_tr = np.clip(55 * (mix_tr ** 1.4), 0, 255)
tr_img   = tr_img.filter(ImageFilter.GaussianBlur(radius=max(28, w // 64)))
```

| Knob | Value | What it does | Customise |
|---|---|---|---|
| **Shape** | `np.hypot(w - xg, yg)` | Distance from every pixel to the top-right corner. `w - xg` flips the X axis; `yg` measures from the top (Y=0 at top). | Move to top-left: `np.hypot(xg, yg)`. Centre glow: `np.hypot(w/2 - xg, h/2 - yg)`. |
| **Spread** | `/ 0.40` | The mathematical circle extends 40% of the diagonal before clipping. The Gaussian blur below diffuses it further in practice. | Tighter: `/ 0.25` — colour stays close to the corner. Wider: `/ 0.65` — colour washes across most of the canvas. |
| **Intensity** | `55 *` | Peak opacity of 55/255 — deliberately low and transparent. The colour tints atmospherically without covering the posters. | Subtle: `30`. Vivid: `100` — strong colour wash, may overpower dark posters. |
| **Curve** | `** 1.4` | Moderate easing producing a natural soft falloff. The blur step below matters more than this value for the final look. | Harder edge: `** 2.5` then increase blur radius. Flat even wash: `** 1.0`. |
| **Blur radius** | `max(28, w // 64)` | Gaussian blur in pixels — evaluates to `30px` at 1920px wide. This turns the hard mathematical circle into a soft lens-flare haze. | Sharper glow: `max(10, w // 120)`. Ultra soft: `max(60, w // 32)`. |

> **Compositing order matters.** The three dark layers are applied first (`bl → left → bottom`), then the colour glow goes on top. To make the accent sit underneath the shadows instead — darker and more subdued — move the `alpha_composite` call for `tr_img` to before the shadow composites inside `apply_gradient()`.

---

## Grid & Layout Constants

These constants live at the top of `generate.py` and control the physical layout of the tile grid, the camera angle, the left-side opacity fade, and the depth-of-field blur engine. They are global — changing any of them affects every entry in the config.

> All constants are in `scripts/generate.py` under the `# T2 GRID CONSTANTS & CAMERA SETTINGS` block near the top of the file.

---

### Tile Size & Grid Dimensions

```python
TILE_W = 372   # Tile width in pixels
TILE_H = 210   # Tile height in pixels
GAP    = 9     # Gap between tiles in pixels
ROWS   = 10    # Number of tile rows in the grid
COLS   = 10    # Number of tile columns in the grid
```

| Constant | Value | What it does | Customise |
|---|---|---|---|
| `TILE_W` / `TILE_H` | `372` / `210` | Base tile dimensions — exactly 16:9 ratio. Every downloaded image is cropped and resized to fit this box. | Keep the ratio at 16:9 or tiles will letterbox. E.g. `480 / 270`, `320 / 180`. Larger = fewer tiles visible, each sharper. |
| `GAP` | `9` | Pixel gap between every tile horizontally and vertically. | `0` — seamless borderless grid. `18` — more breathing room between tiles. `4` — tighter, denser feel. |
| `ROWS` / `COLS` | `10` / `10` | Logical grid size before the 10-row/10-column buffer is added. The actual grid rendered is `(COLS + 10) × (ROWS + 10)` to prevent clipping after rotation. | Increasing these has minimal visual effect since the canvas crops the grid anyway. Only needed if you see edge clipping after extreme tilt angles. |

---

### Card Corner Radius

```python
CARD_RADIUS = 9
```

| Constant | Value | What it does | Customise |
|---|---|---|---|
| `CARD_RADIUS` | `9` | Rounded corner radius applied to every tile in pixels. The radius scales proportionally when tiles are resized. | `0` — sharp square corners. `18` — noticeably rounded. `TILE_H // 2` — pill shape (avoid — looks strange on landscape tiles). |

---

### Camera Tilt & Stagger

```python
TILT_DEG = 10    # Counter-clockwise rotation of the entire grid
STAGGER  = 0.35  # Brick-wall row offset as a fraction of (tile width + gap)
```

| Constant | Value | What it does | Customise |
|---|---|---|---|
| `TILT_DEG` | `10` | Rotates the entire grid counter-clockwise by this many degrees before cropping to the 1920×1080 canvas. Higher values create a more dramatic diagonal feel. | `0` — flat horizontal grid, no tilt. `6` — subtle lean. `15` — very aggressive diagonal, tiles appear smaller. |
| `STAGGER` | `0.35` | Each row is offset horizontally by `STAGGER × (TILE_W + GAP)` pixels relative to the row above it — like brickwork. This breaks the dead-straight vertical column alignment and adds visual depth. | `0.0` — no stagger, columns align perfectly. `0.5` — half-tile offset, classic brick pattern. `0.75` — heavy offset, more chaotic feel. |

---

### Left-Side Opacity Fade

```python
FADE_LEFT  = 0.30   # Opacity of tiles on the far left of the grid
FADE_RIGHT = 1.00   # Opacity of tiles on the far right of the grid
```

This is a separate effect from the gradient shadow in `apply_gradient()`. It directly dims the tile images themselves based on their horizontal position — tiles near the left edge are rendered at `FADE_LEFT` opacity, tiles near the right edge at `FADE_RIGHT`. The fade is applied at tile-render time, before the gradient layer is composited on top.

| Constant | Value | What it does | Customise |
|---|---|---|---|
| `FADE_LEFT` | `0.30` | Minimum tile opacity on the far-left side. `0.30` means left-edge tiles render at 30% transparency — they are dimmed but still visible through the gradient. | `0.0` — left tiles are completely invisible. `0.50` — dimmer but still present. `1.0` — no fade at all, all tiles same brightness. |
| `FADE_RIGHT` | `1.00` | Maximum tile opacity on the right side. Keep at `1.0` for full brightness on the right. | Lower this (e.g. `0.80`) for an overall darker grid. Useful if your accent glow is very bright. |

> `FADE_LEFT` and `FADE_RIGHT` work together with the gradient's left shadow. The gradient darkens the left canvas area with a colour overlay; `FADE_LEFT` dims the actual tile images underneath. Both effects stack — reducing `FADE_LEFT` makes the left side even darker than the gradient alone.

---

### Default Focal Point

```python
FOCUS_X = 0.5   # Default horizontal focal point (0.0 = left, 1.0 = right)
FOCUS_Y = 0.0   # Default vertical focal point (0.0 = top, 1.0 = bottom)
```

This is the fallback focal point used when no `focus` field is set in a config entry and `build_grid()` is called without a focus argument. In practice, every config entry sets `focus` explicitly (or defaults to `"center-right"`), so these values only matter for the `"t2-default"` focus preset.

The focal point controls two things: which area of the grid gets the sharpest, best-quality tiles placed in it (tiles from the front of the downloaded list are placed closest to the focal point), and where the camera mathematically centres after rotation.

| Constant | Value | What it does | Customise |
|---|---|---|---|
| `FOCUS_X` | `0.5` | Default horizontal centre — middle of the canvas width. | `0.0` — camera anchors to the left edge. `1.0` — anchors to the right edge. |
| `FOCUS_Y` | `0.0` | Default vertical centre — top of the canvas. Combined with `FOCUS_X = 0.5`, the default is top-centre, which is why `"t2-default"` looks different from `"center"`. | `0.5` — true centre. `1.0` — bottom of the canvas. |

---

### Depth of Field (DoF) Blur Engine

```python
DOF_BLUR_MAX = 0.0   # Maximum blur radius in pixels (0 = disabled)
DOF_FALLOFF  = 1.5   # Exponential rate of blur increase from the focal point
```

The DoF system calculates the distance of every pixel from the focal point and applies a proportional Gaussian blur — tiles far from the focal point appear slightly out of focus, like a DSLR lens effect. It is **disabled by default** (`DOF_BLUR_MAX = 0.0`) because it significantly increases render time and the effect is subtle at 1080p.

| Constant | Value | What it does | Customise |
|---|---|---|---|
| `DOF_BLUR_MAX` | `0.0` | Maximum blur radius in pixels applied to tiles at the furthest distance from the focal point. Set to `0` to skip the DoF pass entirely. | `0.0` — disabled (default, fastest). `4.0` — subtle cinematic softness. `8.0` — strong blur on far-edge tiles, noticeable at 1080p. `12.0` — heavy effect, slow to render. |
| `DOF_FALLOFF` | `1.5` | Controls how quickly blur increases as distance from the focal point grows. Higher values keep the in-focus zone sharp for longer then blur aggressively at the edges. | `1.0` — linear increase, even blur across the canvas. `2.0` — sharp centre, fast falloff. `3.0` — very tight focus zone, almost everything else blurred. |

> **Performance note:** enabling DoF (`DOF_BLUR_MAX > 0`) runs 6 Gaussian blur passes across a 1920×1080 NumPy array and blends them per-pixel. On GitHub Actions this adds roughly 15–30 seconds per entry. With 44 entries, that is 10–20 extra minutes per run. Only enable if the visual result is worth it for your use case.

---

### Canvas Background Colour

```python
canvas = Image.new("RGBA", (canvas_w, canvas_h), (10, 10, 12, 255))
```

This is the background colour of the canvas that shows through gaps between tiles and around the edges of the rotated grid. It is hardcoded inside `build_grid()` rather than a top-level constant.

| Value | What it does | Customise |
|---|---|---|
| `(10, 10, 12, 255)` | Near-black with a very slight blue tint — almost identical to the shadow colour `(6, 6, 8)` so gaps are invisible. | Pure black: `(0, 0, 0, 255)`. Dark charcoal: `(18, 18, 20, 255)`. To change it, find `Image.new("RGBA", (canvas_w, canvas_h), (10, 10, 12, 255))` inside `build_grid()` and edit the RGB tuple. |

---

## Config Examples

<details>
<summary><strong>Example 1 — Minimal entry (auto accent from label name)</strong></summary>

```json
{
  "name":   "trending",
  "label":  "Trending",
  "output": "custom/backdrop/trending.webp",
  "sources": [
    "movie:/trending/movie/week?language=en-US",
    "tv:/trending/tv/week?language=en-US"
  ]
}
```

- **Accent:** vibrant colour generated from the word `"Trending"`
- **Images:** TMDB backdrops only — no Fanart key required

</details>

<details>
<summary><strong>Example 2 — Full streaming service entry (auto accent from logo)</strong></summary>

```json
{
  "name":   "netflix",
  "label":  "Netflix",
  "logo":   "streaming/logo/Netflix.webp",
  "output": "streaming/backdrop/netflix.webp",
  "focus":  "center-right",
  "count":  60,
  "fanart": true,
  "sources": [
    "movie:sort_by=popularity.desc&with_watch_providers=8&watch_region=IN",
    "tv:sort_by=popularity.desc&with_watch_providers=8&watch_region=IN"
  ]
}
```

- **Accent:** extracted from `Netflix.webp` automatically
- **Images:** Fanart.tv thumbs, TMDB backdrop fallback
- **Focus:** right-of-centre for streaming service layout

</details>

<details>
<summary><strong>Example 3 — MDBList-only entry (multiple lists as array)</strong></summary>

```json
{
  "name":        "my-top-picks",
  "label":       "My Top Picks",
  "logo":        "custom/logo/picks.webp",
  "output":      "custom/backdrop/top-picks.webp",
  "focus":       "center",
  "count":       60,
  "fanart":      true,
  "mdblist_url": [
    "snoak/netflix-top-10-shows",
    "snoak/netflix-top-10-movies"
  ],
  "sort":        "imdbrating.desc"
}
```

- **Accent:** extracted from `picks.webp` — or from label if logo missing
- **Titles:** fetched from both MDBList lists → round-robin interleaved → resolved via TMDB `/find/{imdb_id}`
- **Sort:** highest IMDb-rated titles first

> No logo? Just remove the `logo` line — accent comes from the label name automatically.

</details>

<details>
<summary><strong>Example 4 — Mixed entry (TMDB + MDBList in the same backdrop)</strong></summary>

```json
{
  "name":        "netflix-picks",
  "label":       "Netflix Picks",
  "logo":        "streaming/logo/Netflix.webp",
  "output":      "custom/backdrop/netflix-picks.webp",
  "focus":       "center-right",
  "count":       60,
  "fanart":      true,
  "mdblist_url": "yourUsername/netflix-favs",
  "sort":        "score.desc",
  "sources": [
    "movie:sort_by=popularity.desc&with_watch_providers=8&watch_region=IN",
    "tv:sort_by=popularity.desc&with_watch_providers=8&watch_region=IN"
  ]
}
```

TMDB titles and MDBList titles are round-robin interleaved so neither source dominates. Both are deduplicated by TMDB ID before compositing.

</details>

<details>
<summary><strong>Example 5 — Manual accent colour override</strong></summary>

```json
{
  "name":         "hbo-max",
  "label":        "HBO Max",
  "logo":         "streaming/logo/HBO-max.webp",
  "output":       "streaming/backdrop/hbo-max.webp",
  "focus":        "center-right",
  "count":        60,
  "fanart":       true,
  "accent_color": "151,181,216",
  "sources": [
    "movie:sort_by=popularity.desc&with_watch_providers=384&watch_region=US",
    "tv:sort_by=popularity.desc&with_watch_providers=384&watch_region=US"
  ]
}
```

`accent_color` bypasses logo scanning entirely. Only set this if auto-detection produces the wrong colour. Accepts `"R,G,B"` or `"#RRGGBB"`.

</details>

<details>
<summary><strong>Example 6 — No gradient at all (pure tile grid)</strong></summary>

```json
{
  "name":      "clean-grid",
  "label":     "Clean Grid",
  "no_accent": true,
  "output":    "custom/backdrop/clean-grid.webp",
  "focus":     "center",
  "count":     60,
  "fanart":    true,
  "sources": [
    "movie:/trending/movie/week?language=en-US",
    "tv:/trending/tv/week?language=en-US"
  ]
}
```

`no_accent: true` skips the entire gradient step — no shadows, no colour glow. `accent_color` and `logo` fields are ignored when this is set.

</details>

<details>
<summary><strong>Example 7 — Shadows only, no colour glow</strong></summary>

```json
{
  "name":        "clean-shadow",
  "label":       "Clean Shadow",
  "shadow_only": true,
  "output":      "custom/backdrop/clean-shadow.webp",
  "focus":       "center",
  "count":       60,
  "fanart":      true,
  "sources": [
    "movie:/trending/movie/week?language=en-US",
    "tv:/trending/tv/week?language=en-US"
  ]
}
```

`shadow_only: true` applies the three dark shadow layers (left fade, bottom fade, corner vignette) but skips the top-right colour glow entirely. Useful for entries where you want depth but a neutral, colour-agnostic look. `accent_color` and `logo` are ignored.

</details>

<details>
<summary><strong>Example 8 — Genre backdrop</strong></summary>

```json
{
  "name":   "action",
  "label":  "Action",
  "output": "custom/backdrop/action.webp",
  "focus":  "top-right",
  "count":  60,
  "fanart": true,
  "sources": [
    "movie:sort_by=popularity.desc&with_genres=28",
    "tv:sort_by=popularity.desc&with_genres=28"
  ]
}
```

</details>

<details>
<summary><strong>Example 9 — Anime (language + genre filter combined)</strong></summary>

```json
{
  "name":   "anime",
  "label":  "Anime",
  "output": "custom/backdrop/anime.webp",
  "focus":  "center-right",
  "count":  60,
  "fanart": true,
  "sources": [
    "tv:sort_by=popularity.desc&with_genres=16&with_original_language=ja"
  ]
}
```

</details>

<details>
<summary><strong>Example 10 — Multiple TMDB sources interleaved</strong></summary>

```json
{
  "name":   "weekend-watch",
  "label":  "Weekend Watch",
  "output": "custom/backdrop/weekend-watch.webp",
  "focus":  "center",
  "count":  60,
  "fanart": true,
  "sources": [
    "movie:/trending/movie/week?language=en-US",
    "tv:/trending/tv/week?language=en-US",
    "movie:/movie/top_rated?language=en-US",
    "tv:/tv/top_rated?language=en-US"
  ]
}
```

All four sources are fetched, round-robin interleaved, and deduplicated.

</details>

<details>
<summary><strong>Example 11 — Network-specific (Netflix originals via network ID)</strong></summary>

```json
{
  "name":   "netflix-originals",
  "label":  "Netflix Originals",
  "logo":   "streaming/logo/Netflix.webp",
  "output": "custom/backdrop/netflix-originals.webp",
  "focus":  "center-right",
  "count":  60,
  "fanart": true,
  "sources": [
    "tv:sort_by=popularity.desc&with_networks=213"
  ]
}
```

</details>

<details>
<summary><strong>Example 12 — Top rated with minimum vote threshold</strong></summary>

```json
{
  "name":   "top-rated",
  "label":  "Top Rated",
  "output": "custom/backdrop/top-rated.webp",
  "focus":  "center",
  "count":  60,
  "fanart": true,
  "sources": [
    "movie:sort_by=vote_average.desc&vote_count.gte=500",
    "tv:sort_by=vote_average.desc&vote_count.gte=200"
  ]
}
```

</details>

<details>
<summary><strong>Example 13 — Custom focus point with hex accent</strong></summary>

```json
{
  "name":         "sci-fi",
  "label":        "Sci-Fi",
  "output":       "custom/backdrop/sci-fi.webp",
  "focus":        "0.7,0.3",
  "count":        60,
  "fanart":       true,
  "accent_color": "#4A90D9",
  "sources": [
    "movie:sort_by=popularity.desc&with_genres=878",
    "tv:sort_by=popularity.desc&with_genres=878"
  ]
}
```

</details>

---

## `sources` — Complete Format Reference

### Format A — Discover Mode *(no leading slash)*

Start with `movie:` or `tv:` then any TMDB `/discover` query parameters. The alias `series:` also works as an alternative to `tv:`.

```bash
# Streaming provider (India)
"movie:sort_by=popularity.desc&with_watch_providers=8&watch_region=IN"
"tv:sort_by=popularity.desc&with_watch_providers=8&watch_region=IN"

# Streaming provider (US)
"movie:sort_by=popularity.desc&with_watch_providers=8&watch_region=US"

# Genre filter
"movie:sort_by=popularity.desc&with_genres=28"
"tv:sort_by=popularity.desc&with_genres=18"

# Highest rated (minimum votes)
"movie:sort_by=vote_average.desc&vote_count.gte=500"
"tv:sort_by=vote_average.desc&vote_count.gte=200"

# Language filter
"tv:sort_by=popularity.desc&with_original_language=ja"

# Language + genre combined
"tv:sort_by=popularity.desc&with_genres=16&with_original_language=ja"

# Network filter (TV only)
"tv:sort_by=popularity.desc&with_networks=213"

# Company / studio filter
"movie:sort_by=popularity.desc&with_companies=21"

# Recently released
"movie:sort_by=primary_release_date.desc"
"tv:sort_by=first_air_date.desc"
```

### Format B — Direct Endpoint Mode *(leading slash)*

Start with `movie:/` or `tv:/` followed by any TMDB endpoint path.

```bash
# Trending this week
"movie:/trending/movie/week?language=en-US"
"tv:/trending/tv/week?language=en-US"

# Trending today
"movie:/trending/movie/day?language=en-US"
"tv:/trending/tv/day?language=en-US"

# Popular globally
"movie:/movie/popular?language=en-US"
"tv:/tv/popular?language=en-US"

# Top rated all time
"movie:/movie/top_rated?language=en-US"
"tv:/tv/top_rated?language=en-US"

# Upcoming
"movie:/movie/upcoming?language=en-US"

# Now playing in theatres
"movie:/movie/now_playing?language=en-US"
```

---

## TMDB Discover Sort Values

| Value | Description |
|---|---|
| `popularity.desc` | Most popular right now *(recommended)* |
| `vote_average.desc&vote_count.gte=500` | Highest rated with minimum 500 votes |
| `primary_release_date.desc` | Most recently released |
| `revenue.desc` | Highest grossing of all time |
| `vote_count.desc` | Most voted on |

---

## MDBList Sort Options

| Value | Description |
|---|---|
| `score.desc` | MDBList combined score — default when `sort` is not set |
| `score.asc` | Lowest score first |
| `imdbrating.desc` | Highest IMDb rating first |
| `imdbrating.asc` | Lowest IMDb rating first |
| `imdbvotes.desc` | Most IMDb votes first |
| `tmdbpopular.desc` | TMDB popularity metric |
| `released.desc` | Most recently released first |
| `released.asc` | Oldest releases first |

---

## `focus` Options

| Preset | X | Y | Best for |
|---|---|---|---|
| `"center"` | 0.50 | 0.50 | General use, trending, genre, top rated |
| `"center-right"` | 0.65 | 0.45 | Streaming services — default |
| `"top-right"` | 0.72 | 0.28 | Dynamic feel, action, sci-fi |
| `"top-center"` | 0.52 | 0.30 | Clean and balanced look |
| `"t2-default"` | 0.50 | 0.00 | Top-edge anchor — grid heavy at the top |

**Custom:** `"0.4,0.6"` — specify any X,Y values from `0.0` to `1.0`

X is horizontal position (0.0 = far left, 1.0 = far right). Y is vertical position (0.0 = top, 1.0 = bottom). The focal point controls which part of the grid gets the sharpest, best-quality tiles.

---

## `accent_color` Reference

Only set this if auto-detection gives the wrong colour for a specific entry. Leave it out to use automatic detection from logo or label.

**Format:** `"R,G,B"` or `"#RRGGBB"` — both accepted.

| Service | R,G,B | Hex |
|---|---|---|
| Netflix | `"213,30,39"` | `#D51E27` |
| Prime Video | `"40,124,224"` | `#287CE0` |
| Disney+ / Hotstar | `"30,201,212"` | `#1EC9D4` |
| Apple TV+ | `"212,142,191"` | `#D48EBF` |
| HBO Max | `"151,181,216"` | `#97B5D8` |
| Crunchyroll | `"223,106,32"` | `#DF6A20` |
| Paramount+ | `"32,111,223"` | `#206FDF` |
| Discovery+ | `"226,112,53"` | `#E27035` |
| Trending | `"100,80,200"` | `#6450C8` |
| Top Rated | `"255,180,0"` | `#FFB400` |

---

## Provider IDs

### India (`watch_region=IN`)

| Service | ID |
|---|---|
| Netflix | `8` |
| Amazon Prime Video | `119` |
| Disney+ Hotstar | `122` |
| Apple TV+ | `350` |
| Crunchyroll | `283` |
| Discovery+ | `584` |

### US (`watch_region=US`)

| Service | ID |
|---|---|
| Netflix | `8` |
| Prime Video | `9` |
| Disney+ | `337` |
| Apple TV+ | `350` |
| HBO Max | `384` |
| Hulu | `15` |
| Paramount+ | `531` |
| Peacock | `386` |
| Crunchyroll | `283` |
| Discovery+ | `584` |

---

## Network IDs — use with `with_networks=ID`

| Network | ID |
|---|---|
| Netflix | `213` |
| HBO | `49` |
| HBO Max | `3186` |
| Apple TV+ | `2552` |
| Amazon | `1024` |
| Disney Channel | `54` |
| FX | `88` |
| Showtime | `67` |
| AMC | `174` |
| BBC | `4` |

---

## Genre IDs — use with `with_genres=ID`

| Genre | ID | Genre | ID | Genre | ID |
|---|---|---|---|---|---|
| Action | `28` | Comedy | `35` | Drama | `18` |
| Horror | `27` | Sci-Fi | `878` | Thriller | `53` |
| Crime | `80` | Animation | `16` | Mystery | `9648` |
| Romance | `10749` | Documentary | `99` | Fantasy | `14` |
| Adventure | `12` | History | `36` | Music | `10402` |

---

## Content Safety

`generate.py` has an integrated adult content filter that runs on every title fetched from both TMDB and MDBList before image download begins.

**What it blocks automatically:**

- TMDB adult flag (`include_adult=false` sent on every API request)
- Keyword match in title, original title, and overview text: `hentai`, `porn`, `pornography`, `erotica`, `xxx`, `av girl`, `jav`, `milf`, `fetish`, `bondage`, `bdsm`, `ecchi`, `yaoi`, `yuri`, `uncensored`, `creampie`, `bukkake`
- JAV-style alphanumeric codes (e.g. `ABP-123`, `FC2-456`)
- Obscure low-engagement content (`vote_count < 15` and `popularity < 5`)
- TMDB IDs listed in the `BLOCKED_IDS` set in `generate.py`

**How to permanently block a specific title:**

1. Find its TMDB ID — the console prints every fetched title during a run
2. Open `scripts/generate.py`
3. Find `BLOCKED_IDS` near the top of the file:

```python
BLOCKED_IDS = {
    1241752,
    95897,
}
```

4. Add the new ID:

```python
BLOCKED_IDS = {
    1241752,
    95897,
    912345,   # ← add here
}
```

5. Commit — blocked in all future runs across all entries

---

## Adding a New Backdrop

1. Open `scripts/backdrop-config.json` in your GitHub repo
2. Click the ✏️ pencil icon to edit
3. Find the last `}` before the closing `]`
4. Add a comma after it
5. Paste a new entry — copy the closest matching example from this guide
6. Edit `name`, `label`, `output`, and `sources` / `mdblist_url`
7. Commit the change

**Rules:**
- `name` must be unique across all entries, lowercase, hyphens only
- `output` path determines where the WebP is saved in your repo
- At least one of `sources` or `mdblist_url` must be present

Runs automatically on the **1st of every month**.

To trigger immediately: **Repo → Actions tab → Generate Backdrops → Run workflow**

---

## What `generate.py` Does — Step by Step

For each entry in `backdrop-config.json`:

**STEP 1** — Read all fields from the entry

**STEP 2** — Resolve accent colour
- `no_accent: true` → `None` — all shadows and gradient skipped entirely
- `shadow_only: true` → shadows applied, colour glow skipped
- `accent_color` set → parse and use directly
- Logo file exists → scan pixels, extract dominant vibrant colour
- Logo missing → fall through
- No logo → deterministic vibrant colour from label string

**STEP 3** — Fetch TMDB titles *(only if `sources` is set)*
- For each source string — no leading slash → `/discover/movie` or `/discover/tv`; leading slash → direct TMDB endpoint
- Paginate up to 3 pages per source
- Round-robin interleave results from multiple sources
- Adult filter applied to every result

**STEP 4** — Fetch MDBList titles *(only if `mdblist_url` is set)*
- `mdblist_url` can be a single string or an array — each list is fetched separately
- `GET api.mdblist.com/lists/user/{username}` → find list matching the slug → get numeric `list_id`
- `GET api.mdblist.com/lists/{list_id}/items` → sorted by `sort` field → items include `imdb_id`
- For each item: `GET api.themoviedb.org/3/find/{imdb_id}?external_source=imdb_id` → resolve to full TMDB item dict
- Multiple lists are round-robin interleaved before deduplication
- Adult filter applied to every resolved item

**STEP 5** — Merge all titles
- Round-robin interleave TMDB and MDBList results
- Deduplicate by `(media_type, tmdb_id)`
- Trim to `count` limit

**STEP 6** — Download thumbnails
- For each title, in order:
  - `fanart: true` AND `FANART_API_KEY` set:
    - TV → get `tvdb_id` → Fanart `/tv/{tvdb_id}` → best `tvthumb`
    - Movie → Fanart `/movies/{tmdb_id}` → best `moviethumb`
    - Fanart priority: preferred language (English) → original title language → textless / no-language artwork → any other non-empty language
  - TMDB fallback → `backdrop_path` at `w1280`
  - Skip title if nothing found after all fallbacks
- Minimum 12 tiles enforced — repeats if fewer downloaded

**STEP 7** — Composite 1080p grid
- Landscape-only tiles at 16:9 (372×210px base scaled to canvas)
- Grid tilted 10° counter-clockwise
- Focus-weighted placement — best images near the focal point
- Grid oversized to fill canvas after rotation

**STEP 8** — Apply gradient overlay
- Skipped entirely if `no_accent: true`
- If `shadow_only: true` — layers 1–3 applied, layer 4 (colour glow) skipped
- Layer 1: left-side dark fade — 60% spread from left edge
- Layer 2: bottom dark fade — starts at 40%, fills remaining 60%
- Layer 3: bottom-left dark vignette — 75% diagonal spread, 255 intensity
- Layer 4: top-right accent glow — 40% spread, 55 intensity, Gaussian-blurred

**STEP 9** — Save as WebP
- 1920×1080, quality 82, method 6
- Written directly as WebP to the output path — no `.jpg` at any point

**STEP 10** — Report
- Success → prints output path and file size in KB
- Failure → prints reason, skips entry, continues with the rest
