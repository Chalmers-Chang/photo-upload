# web

## GOTCHA

- Slideshow `img { max-height: 100% }` does not shrink high-res JPEGs when the frame has no definite height; the photo paints at intrinsic size. Pin the frame with `minmax(0, 1fr)` and position the image with `max-width/max-height: 100%` so it letterboxes and stays centered.
- `.empty { display: grid }` overrides the `hidden` attribute, so 「尚無照片」 stays on top of real photos. Force `img[hidden], .empty[hidden] { display: none !important }`.
- `Image.save(..., optimize=True)` on phone photos makes upload feel stuck (CPU Huffman pass). Save JPEG at quality 80 with no optimize; `draft()` + bilinear thumbnail for speed.

## TASTE

- Admin project card: top-right 「刪除專案」 removes Redis, photo files, project record, and slug URLs (`/p/<slug>/` 404). 「只刪 Redis」 also drops the project/URLs but leaves files on disk.

- Fit photos inside the viewport (`object-fit: contain`). Do not set `width/height: 100%` or small photos get stretched.
- Admin link lives in `base.html` (and slideshow, which does not extend base). Session cookie is permanent 30 days; `/admin` skips the login form when `session["admin"]` is set.
- One upload = one Redis ticket (`ticket_seq` serial + `device_id` cookie). Lottery is admin-only. Sphere keeps at least 30 photos (pad by repeat). Spin angular speed is exponential decay via rAF (`ω ∝ e^{-kt}`). Winner uses slideshow contain-and-center.
- First visit with no `device_name:{id}` shows a nickname modal (`/api/profile`). Slideshow and lottery labels use that name via the photo's `device_id`.
- User-facing copy lives in `config/msg.py` as bilingual `中文 / English` strings. Templates get `msg` from the Flask context processor.
- Blank project slug = lowercase `project_name` with symbols/spaces stripped (`a-z0-9` only). Empty result (e.g. Chinese-only name) falls back to a short hex id.
- Project folder holds optional `pjt-home.jpg` (home button cover) and `bkg-slideshow.jpg` (slideshow backdrop). Admin uploads/deletes them; full project delete `rmtree`s the folder. Slideshow photo has ~22px Apple-style corners and 2cm inset from the screen.
