# Style guide

Read this before any UI change. Update it when you add a page, a token, or a shared partial.

## Where styles live

| File | Owns |
| --- | --- |
| `web/templates/_theme.html` | Design tokens (`--frost-*`, `--ink-*`, `--btn-*`), `--glass` / `--chrome-inset` per viewport, `.glass-stage`, `.glass-card`, `.glass-wait` |
| `web/templates/_cover_layout.html` | Cover-photo page layout (`.pjt-stage`, title, mark, lead, big buttons, `--pjt-*` sizes) plus the decode-then-blur script. Used by project home and Ichiban Kuji |
| `web/templates/_admin_chrome.html` | Top-right 「管理 / Admin」 pill and the top-left `.back-btn` pill |
| `web/templates/_stage_bg.html` | Full-screen `<picture>` background + white fade (slideshow, lottery). Set `bg_desktop` / `bg_mobile` before including |
| `web/templates/_progress_veil.html` | Upload pie overlay |
| `web/static/style.css` | Base form controls, admin cards, `.btn` defaults, `.flash`. Do not put page layout here (cached) |
| `web/static/profile.css` | Nickname modal |
| `config/appsetting.py` | Look knobs read as `cfg.*` (fades, button colors, glass padding) |

`_theme.html` is included by `base.html` (all pages that extend it) and directly by `slideshow.html` / `lottery.html`. Everything that needs `cfg` lives in a Jinja partial, not in a static CSS file.

## Viewport split

- Mobile `@media (max-width: 640px)`, desktop `@media (min-width: 641px)`. Nothing in between.
- Size knobs (font size, padding, gaps, mark size) live only in those two blocks. Shared layout stays outside `@media`.
- When a request is about size, spacing, type, or images and does not say which, ask 手機 or 桌機 first and edit only that block.
- Cover photos are always `<picture>` with a `(max-width: 640px)` source so only one JPEG downloads. Missing side falls back to the other.

## Tokens

| Token | Value | Use |
| --- | --- | --- |
| `--bg` | `#f4efe6` cream | Page background (style.css) |
| `--ink` | `#1c1915` | Body text |
| `--muted` | `#6b6459` | Labels, meta |
| `--card` | `#fffcf7` | Admin cards, inputs |
| `--line` | `#ddd4c6` | Card and input borders |
| `--err` | `#9f1239` | Danger button, error flash |
| `--frost-fill` | `rgba(255,255,255,0.42)` | Glass fill once blur is on |
| `--frost-solid` | `rgba(255,255,255,0.72)` | Glass fill before the cover decodes |
| `--frost-line` | `rgba(255,255,255,0.55)` | Glass and pill border |
| `--frost-shadow` | `0 8px 32px rgba(28,25,21,0.08)` | Glass and pill shadow |
| `--frost-blur` | `blur(28px) saturate(180%)` | `backdrop-filter` |
| `--ink-fade` | ink at `1 - BUTTON_TEXT_FADE` | Button and pill labels (bold) |
| `--ink-soft` | `rgba(28,25,21,0.48)` | Text on glass (slideshow name/note, progress label) |
| `--btn-upload` | `UPLOAD_BTN_COLOR` `#f4efe6` at `1 - BUTTON_FADE` | Big button: upload |
| `--btn-slideshow` | `SLIDESHOW_BTN_COLOR` `#d4d1cc` | Big button: slideshow, secondary |
| `--btn-lottery` | `LOTTERY_BTN_COLOR` gold `#d4af37` | Big button: lottery, Ichiban Kuji |
| `--glass` | 2cm desktop / 1cm mobile (`GLASS_PAD_CM`, `GLASS_PAD_MOBILE_CM`) | Inset of the stage glass |
| `--chrome-inset` | same as `--glass` | Left/right of Back and Admin pills |

Gold pie / sparkle accent: `#d4af37`, pale gold `#ffe9b0`, silver `#d8dde3`.

Fonts: body `"PingFang TC", "Noto Sans TC", sans-serif`. Project title on cover pages uses the script stack `"Snell Roundhand", "Savoye LET", "Segoe Script", "Apple Chancery", "Kaiti TC", "STKaiti", "KaiTi", cursive` at weight 400 and `1 - TITLE_FADE` opacity.

## Building blocks

### Glass stage

```html
<div class="glass-stage my-stage">
  <div class="glass-card">
    <div class="glass-body">…</div>
  </div>
  {% include "_credit.html" %}
</div>
```

- `.glass-stage`: fixed full viewport, grid rows `minmax(0, 1fr) auto`, gap 0.1cm, padding `var(--glass)`, top padding at least 64px (room for the chrome pills). `@ChalmersProduction` sits 0.1cm under the glass.
- `.glass-card`: radius 28px, frost fill/border/shadow/blur. Pages only add `display`, `padding`, and `overflow` (`auto` for forms, `hidden` + inner scroll for the admin list).
- `.glass-body`: centered column, `width: min(720px, 100%)` (login uses 360px).
- The cover glass scrolls (`overflow: auto`) when its buttons do not fit (for example four admin buttons at 1280×800).
- Cover pages put `.glass-wait` on the stage wrapper. The glass stays `--frost-solid` without blur until the background `img.decode()` resolves, then JS adds `.is-ready` (Safari samples an empty layer otherwise).

### Buttons

- Big cover buttons (`.pjt-stage .btn`): full width inside `.actions`, bold `--ink-fade` label, 1px white border, `white-space: pre-line` for the two-line 中文 / English label. Fill: default `--btn-upload`, `.secondary` `--btn-slideshow`, `.lottery` `--btn-lottery`. Sizes come from `--pjt-btn-*` (desktop 18px / `22px 20px` / radius 16; mobile 16px / `16px 14px` / radius 14).
- Chrome pills (`.back-btn`, `.chrome-end .admin-btn`): frost fill + border, `8px 14px`, 14px bold `--ink-fade`, radius 999px, `top: 12px`, inset `--chrome-inset`. Back is always 「返回 / Back」 (`msg.lottery_back`) to the project home.
- Admin list: `.btn` (ink), `.btn.secondary` (card), `.btn.small`, `.btn.danger.delete-project` (~70% size). Logout uses the pill look, min-height 44px, `appearance: none`.
- Destructive actions use the in-page confirm pattern: a `.delete-arm` with an arm button and a hidden `.delete-confirm` form (「確認」/「取消」). Do not use `window.confirm` (the lottery reset is the one legacy exception).

### Overlays

- Progress veil: fixed, inset 2cm, frost glass, gold pie. Show with `.is-on` only (never an unscoped `display: grid`, it beats `hidden`).
- Full-screen dim for previews: `rgba(28,25,21,0.82)`, click to close.
- Modal card (nickname): `#fffcf7`, radius 16px, `rgba(28,25,21,0.55)` backdrop.
- Glass panel overlays (Ichiban Kuji `.kuji-panel`): fixed, inset `var(--glass)` (top at least 64px), `rgba(28,25,21,0.28)` backdrop, `.glass-card` inside, scroll inside the card, close pill top-right of the card. Below the chrome (z-index 20 vs 30) so Back and Admin stay usable. While a panel is open, `body.panel-open` hides the page glass so it does not blur through as a smudge.
- Anything with a `[hidden]` state and its own `display` needs `[hidden] { display: none !important; }`.

### Backgrounds

- `<picture>` covering the viewport with `object-fit: cover`, then a white `.stage-fade` / `.pjt-fade` overlay at `BKG_FADE` / `PJT_FADE` opacity.
- Photos are always `object-fit: contain`, centered, `max-width/max-height: 100%` inside a `minmax(0, 1fr)` frame. Never `width/height: 100%` on a photo.
- Photo corners: 22px; shadow `box-shadow`, not `filter: drop-shadow`.

### Copy

- All user-facing strings live in `config/msg.py` as `中文 / English` (or `中文\nEnglish`). Templates read `msg`.
- Multi-line strings need `white-space: pre-line`. In JS use `{{ msg.x | tojson }}`. HTML attributes collapse `\n`, so use `&#10;` there.

## Pages

| Page | Template | Layout |
| --- | --- | --- |
| Site landing `/` | `index.html` | Plain `.hero` on cream |
| Project home `/p/<slug>/` | `project_home.html` + `_cover_layout.html` | `pjt-*` cover photo, `.glass-wait` glass with script title, optional `pjt-mark`, lead, big buttons: 上傳照片 (upload) / 輪播照片 (secondary) / 一番賞 (lottery gold) / 抽獎 (lottery gold, admin only) |
| Upload `/p/<slug>/upload` | `upload.html` | Cream glass stage, left-aligned bilingual labels, centered submit, Back pill, progress veil |
| Slideshow `/p/<slug>/slideshow` | `slideshow.html` | Dark page. `wall`: `bkg-*` background, name glass above, photo (22px corners, 2cm inset), note glass below. `full`: cream letterbox, photo only. Chrome fades after 5s idle |
| Lottery `/p/<slug>/lottery` (admin) | `lottery.html` | `lot-*` background, 3D sphere, sparkles canvas, winner contain-and-center inset `LOTTERY_PAD_CM`, side thumbs, gold pill 「再抽一位」, white bold 「重置抽獎」 bottom-left |
| Ichiban Kuji `/p/<slug>/kuji` | `kuji.html` + `_cover_layout.html` | Same cover layout as home with `kuji-*` background (falls back to `pjt-*`) and `kuji-mark`. Chance line under the lead. Buttons: 查看獎品狀態 (secondary) / 抽一番賞 (lottery gold) / 我的獎品 (upload). Glass panel overlays for status, tear, and my prizes |
| Admin login `/admin/login` | `admin_login.html` | Cream glass stage, 360px body |
| Admin list `/admin` | `admin.html` | Cream glass stage, scroll inside the glass, `<details>` project cards. After 「更多」: four collapsed blocks (首頁 / 輪播 / 抽獎 / 一番賞), each with that page’s assets and its own 參數設定. 2-col asset grid (1 col on mobile). Logout pill above the credit |

## New-page checklist

1. Extend `base.html` (gets `_theme.html`, chrome, credit, nickname modal). Full-screen dark pages include `_theme.html` and `_admin_chrome.html` themselves.
2. Use `.glass-stage` + `.glass-card` (or `_cover_layout.html` for a cover-photo page). Do not copy the frost values; use the tokens.
3. Back pill top-left to project home, Admin pill top-right, credit 0.1cm under the glass.
4. Background photos as desktop/mobile assets in `store.ASSETS`, rendered with `<picture>`.
5. Size knobs only in the mobile / desktop blocks.
6. Strings in `config/msg.py`, bilingual, `pre-line`.
7. Screenshot at 390px and 1280px wide before calling it done.
