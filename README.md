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
| `mdblist_url` | string | optional | `"username/list-slug"` or full mdblist.com URL |
| `sort` | string | `"score.desc"` | MDBList sort order (see [MDBList Sort](#mdblist-sort-options)) |
| `logo` | string | optional | Path to logo image for auto accent extraction |
| `accent_color` | string | optional | Manual override — `"R,G,B"` or `"#RRGGBB"` |
| `no_accent` | bool | `false` | Skip gradient overlay entirely |
| `focus` | string | `"center-right"` | Focal point preset or `"x,y"` custom values |
| `count` | int | `60` | Max titles after merging all sources |
| `fanart` | bool | `true` | Use Fanart.tv for higher quality thumbnails |

> At least one of `"sources"` or `"mdblist_url"` must be present per entry. Both can be set together for a mixed entry.

---

## Gradient — How the Math Works

The gradient system is the visual heart of each backdrop. Using **NumPy**, the entire 1920×1080 canvas is treated as a mathematical grid — no pixel-by-pixel loops.

**Variable reference:**

| Variable | Meaning |
|---|---|
| `w`, `h` | Total width and height of the image |
| `xg`, `yg` | X (horizontal) and Y (vertical) coordinate grids of the full canvas |
| `diag` | Maximum diagonal distance from corner to corner |
| `np.clip(value, min, max)` | Safety net — guarantees values never exceed the defined range |

---

### 1. Left Shadow — Linear X-Axis Fade

```python
mix_left = np.clip(1.0 - xg / (w * 0.60), 0.0, 1.0)
alpha_left = np.clip(220 * (mix_left ** 1.2), 0, 255)
left_img = _create_layer(6, 6, 8, alpha_left)
```

- **Spread** (`w * 0.60`) — Shadow zone stretches 60% across the screen
- **Fade** (`1.0 - ...`) — Inverts the math so the left edge is fully opaque (`1.0`) and hits transparent (`0.0`) at the 60% mark
- **Curve** (`** 1.2`) — Exponential easing; bends the fade smoothly rather than a harsh linear falloff
- **Intensity** (`220 *`) — Max opacity 220/255 using RGB `(6, 6, 8)` — a very dark charcoal blue

---

### 2. Bottom Shadow — Linear Y-Axis Fade

```python
mix_bottom = np.clip((yg - h * 0.40) / (h * 0.60), 0.0, 1.0)
alpha_bottom = np.clip(220 * (mix_bottom ** 1.2), 0, 255)
```

- **Start point** (`yg - h * 0.40`) — Shadow waits until 40% down the screen; anything above is clipped to `0.0` (invisible)
- **Spread** (`/ (h * 0.60)`) — The remaining 60% of the canvas is the full fade zone
- **Curve & Intensity** — Same 1.2 exponent and 220 max opacity as the left shadow

---

### 3. Bottom-Left Radial Corner — Pythagorean Distance

```python
dist_bl = np.hypot(xg, h - yg)
mix_bl = np.clip(1.0 - (dist_bl / diag) / 0.75, 0.0, 1.0)
alpha_bl = np.clip(255 * (mix_bl ** 1.8), 0, 255)
```

- **Shape** (`np.hypot`) — Uses the Pythagorean theorem to calculate straight-line distance from every pixel to the bottom-left corner; produces a circular radial fade instead of a line
- **Spread** (`/ 0.75`) — Circular darkness reaches 75% of the way across the canvas diagonally
- **Curve** (`** 1.8`) — Much higher exponent; darkness stays tightly packed in the corner and drops off aggressively
- **Intensity** (`255`) — Absolute maximum opacity — extreme bottom-left corner is completely pitch black

---

### 4. Top-Right Accent Glow

```python
dist_tr = np.hypot(w - xg, yg)
mix_tr = np.clip(1.0 - (dist_tr / diag) / 0.90, 0.0, 1.0)
alpha_tr = np.clip(100 * (mix_tr ** 1.4), 0, 255)
...
tr_img = tr_img.filter(ImageFilter.GaussianBlur(radius=max(28, w // 64)))
```

- **Shape** (`np.hypot(w - xg, yg)`) — Calculates circular distance from the top-right corner
- **Spread** (`/ 0.90`) — Massive spread; glow reaches 90% of the canvas diagonally
- **Intensity** (`100 *`) — Capped at 100/255 to keep the colour transparent and atmospheric — full opacity would cover the posters entirely
- **Blur** (`GaussianBlur`) — Diffuses the mathematically perfect circle into a soft, realistic lens-flare glow

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
<summary><strong>Example 3 — MDBList-only entry</strong></summary>

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
- **Titles:** fetched from MDBList → resolved via TMDB `/find/{imdb_id}`
- **Sort:** highest IMDb-rated titles first

> No logo? Just remove the `logo` line — accent comes from the label name.

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

`no_accent: true` skips the entire gradient step. `accent_color` and `logo` fields are ignored when this is set.

> Use `"shadow_only": true` for only the left-side shadow.

</details>

<details>
<summary><strong>Example 7 — Genre backdrop</strong></summary>

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
<summary><strong>Example 8 — Anime (language + genre filter combined)</strong></summary>

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
<summary><strong>Example 9 — Multiple TMDB sources interleaved</strong></summary>

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
<summary><strong>Example 10 — Network-specific (Netflix originals via network ID)</strong></summary>

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
<summary><strong>Example 11 — Top rated with minimum vote threshold</strong></summary>

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
<summary><strong>Example 12 — Custom focus point with hex accent</strong></summary>

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

Start with `movie:` or `tv:` then any TMDB `/discover` query parameters.

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

**Custom:** `"0.4,0.6"` — specify any X,Y values from `0.0` to `1.0`

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
- Keyword match in title, original title, and overview text (`hentai`, `porn`, `pornography`, `erotica`, `xxx`, `jav`, `milf`, `fetish`, `bondage`, `bdsm`, `ecchi`, `yaoi`, `yuri`, `uncensored`, and others)
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
- `no_accent: true` → `None` — gradient skipped at step 8
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
- `GET api.mdblist.com/lists/user/{username}` → find list matching the slug → get numeric `list_id`
- `GET api.mdblist.com/lists/{list_id}/items` → sorted by `sort` field → items include `imdb_id`
- For each item: `GET api.themoviedb.org/3/find/{imdb_id}?external_source=imdb_id` → resolve to full TMDB item dict
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
- Grid tilted 10° clockwise
- Focus-weighted placement — best images near the focal point
- Grid oversized to fill canvas after rotation

**STEP 8** — Apply gradient overlay *(skipped entirely if `no_accent: true`)*
- Left-side dark fade — ~45% from left edge
- Bottom dark fade — ~50% from bottom edge
- Bottom-left dark vignette — corner deepening
- Top-right accent glow — resolved RGB colour, Gaussian-blurred

**STEP 9** — Save as WebP
- 1920×1080, quality 82, method 6
- Written directly as WebP to the output path — no `.jpg` at any point

**STEP 10** — Report
- Success → prints output path and file size in KB
- Failure → prints reason, skips entry, continues with the rest
