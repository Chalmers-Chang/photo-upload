# web

## GOTCHA

- Slideshow `img { max-height: 100% }` does not shrink high-res JPEGs when the frame has no definite height; the photo paints at intrinsic size. Pin the frame with `minmax(0, 1fr)` and position the image with `max-width/max-height: 100%` so it letterboxes and stays centered.

## TASTE

- Admin project card: top-right 「刪除專案」 removes Redis, photo files, project record, and slug URLs (`/p/<slug>/` 404). 「只刪 Redis」 also drops the project/URLs but leaves files on disk.

- Fit photos inside the viewport (`object-fit: contain`). Do not set `width/height: 100%` or small photos get stretched.
