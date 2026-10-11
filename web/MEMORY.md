# web

## GOTCHA

- Slideshow `img { max-height: 100% }` does not shrink high-res JPEGs when the frame has no definite height; the photo paints at intrinsic size. Pin the frame with `minmax(0, 1fr)` and position the image with `max-width/max-height: 100%` so it letterboxes and stays centered.
- Do not sweep photos or rebuild `slideshow_q` on every `/api/slideshow` poll. Rebuild on upload, drop, and settings save. Poll only runs the Lua playhead; if the queue is empty but photos exist (first request after deploy), rebuild once.
- `.empty { display: grid }` overrides the `hidden` attribute, so 「尚無照片」 stays on top of real photos. Force `img[hidden], .empty[hidden] { display: none !important }`.
- Slideshow crossfade uses two stacked imgs and `opacity`; do not set `hidden` on them during the transition or `display: none` skips the fade.
- `Image.save(..., optimize=True)` on phone photos makes upload feel stuck (CPU Huffman pass). Save JPEG at quality 80 with no optimize; `draft()` + bilinear thumbnail for speed.

## TASTE

- Admin project card is a closed `<details>` by default; summary shows name, 「刪除專案」, and the three URLs. 「刪除專案」 removes Redis, photo files, project record, and slug URLs (`/p/<slug>/` 404). 「只刪 Redis」 also drops the project/URLs but leaves files on disk. Bottom-right settings store per-project `slideshow_interval`, `slideshow_fade`, `slideshow_queue_max`, `slideshow_per_device`, `lottery_sphere_max`, `lottery_seconds` on the Redis project hash; create copies defaults from `config/appsetting.py`. `slideshow_fade` is seconds (0–3, default 0.8; 0 = hard cut).

- Fit photos inside the viewport (`object-fit: contain`). Do not set `width/height: 100%` or small photos get stretched.
- Admin link lives in `base.html` (and slideshow, which does not extend base). Session cookie is permanent 30 days; `/admin` skips the login form when `session["admin"]` is set.
- Uploads are unlimited. Lottery uses each device's newest `LOTTERY_CHANCE_MAX` (default 10) photos; older tickets rotate off. Slideshow queue is `slideshow_q` (max `SLIDESHOW_QUEUE_MAX`, default 100). If total photos exceed that, keep each device's newest `SLIDESHOW_PER_DEVICE` (default 5) then the newest 100. Lottery is admin-only. After a draw, that device is added to `lottery_won:{project_id}` and skipped on later draws and the sphere (the winning spin still includes them). Admin 「重置抽獎」 only deletes that set; tickets and photos stay. Sphere keeps at least 30 photos (pad by repeat). Spin angular speed is exponential decay via rAF (`ω ∝ e^{-kt}`). Winner uses slideshow contain-and-center, inset `LOTTERY_PAD_CM` (default 2cm) from the screen. After the draw, top-left Back goes to project home; bottom 「再抽一位」 resets the stage and draws again.
- First visit with no `device_name:{id}` shows a nickname modal (`/api/profile`). Slideshow and lottery labels use that name via the photo's `device_id`.
- User-facing copy lives in `config/msg.py` as bilingual `中文 / English` strings. Templates get `msg` from the Flask context processor.
- Blank project slug = lowercase `project_name` with symbols/spaces stripped (`a-z0-9` only). Empty result (e.g. Chinese-only name) falls back to a short hex id.
- Project folder holds optional desktop/mobile pairs: `pjt-desktop.jpg`, `pjt-mobile.jpg`, `bkg-desktop.jpg`, `bkg-mobile.jpg`, `lot-desktop.jpg`, `lot-mobile.jpg`, plus `-sm.jpg` thumbs. Missing side falls back to the other, then legacy `pjt-home.jpg` / `bkg-slideshow.jpg` (lottery has no legacy file). Viewport ≤640px uses mobile. Full project delete `rmtree`s the folder. Slideshow photo has ~22px Apple-style corners and 2cm inset from the screen. Lottery uses the same `BKG_FADE` white overlay as slideshow.
- Project home layout CSS lives in the template (`position:fixed` stage + centered glass). Do not rely on `/static/style.css` for this or a cached stylesheet leaves the photo in document flow under the buttons. Pin `.admin-btn` to `position:fixed; z-index:30` on that page; the full-viewport stage sits above a sticky topbar and covers Admin on desktop.
- Home/slideshow look knobs live in `config/appsetting.py` (and matching env): `PJT_FADE`, `BKG_FADE`, `TITLE_FADE`, `BUTTON_FADE`, `BUTTON_TEXT_FADE` are 0–1 (0 = original, 1 = gone/white). Button fills: `UPLOAD_BTN_COLOR`, `SLIDESHOW_BTN_COLOR`, `LOTTERY_BTN_COLOR`. Glass padding: `GLASS_PAD_CM` (desktop) and `GLASS_PAD_MOBILE_CM` (≤640px). Upload page edge inset: `UPLOAD_PAD_CM`. Lottery winner inset: `LOTTERY_PAD_CM` (default 2). Templates read them via `cfg`.
