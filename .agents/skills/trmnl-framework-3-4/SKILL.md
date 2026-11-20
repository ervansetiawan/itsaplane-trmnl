---
name: trmnl-framework-3-4
description: >-
  TRMNL Framework v3.4 design system, Liquid template conventions, responsive
  utilities, ePaper image dithering, and plugin packaging rules. Use whenever
  creating, reviewing, or updating TRMNL plugin templates (`template.liquid`,
  `full.liquid`, `half_horizontal.liquid`, `half_vertical.liquid`,
  `quadrant.liquid`) or `settings.yml` / `.zip` packages.
---

# TRMNL Framework 3.4 Design System

Reference guide for building crisp, validator-compliant TRMNL ePaper plugins (1-bit, 2-bit, 4-bit) using **TRMNL Framework v3.4** (`https://trmnl.com/framework/docs/3.4`).

---

## 1. Hard Rules (TRMNL Validator & Gotchas)

1. **No `<style>` blocks**: Never include `<style>...</style>` in `.liquid` templates. Use native Framework classes.
2. **Minimize or eliminate inline `style="..."` attributes**:
   - Aim for **0** `style=` attributes.
   - Never put `style=` inside `{% for %}` loops.
   - Use `w--[...]`, `h--[...]`, `gap--*`, `mb--*`, `text--left`, `stretch-x`, `stretch-y`, and `divider` instead.
3. **Always include responsive classes (`lg:`, `portrait:`)**:
   - E.g. `portrait:flex--col`, `portrait:w--full`, `portrait:hidden`, `lg:gap--large`, `lg:value--large`, `lg:title--large`.
4. **Gotcha — `.label` is `display: flex` / `inline-flex`**:
   - Avoid putting `<strong>` + text directly inside `.label` (flex collapses spaces, e.g., `1.Clue`). Use `.description` or `.title--small` for prose/clues with inline `<strong>`.
5. **Gotcha — `.flex--col` centers children horizontally by default**:
   - For left-aligned lists/columns inside a flex row, prefer a plain `<div class="stretch-x text--left">` (or add `text--left` on each child) instead of `.flex--col`.
6. **Gotcha — Container Query Units (`cqw` vs `cqh`)**:
   - Always use `cqw` for width (`w--[46cqw]`) and `cqh` for height (`h--[80cqh]`), never `w--[80cqh]`.
   - Fixed pixel sizes also work (`w--[90px]`, `h--[54px]`), as do percentages (`w--[70%]`).
7. **Gotcha — `<table>` borders & sizing**:
   - TRMNL overrides HTML `width`/`height` attributes on `<table>` with `width: 100%`. Use `class="w--[42cqw] h--[80cqh]"` on `<table>` and do **not** put `.label` on `<td>` cells.

---

## 2. Layout & Sizing Primitives

- **Root structure**:
  ```liquid
  <div class="layout layout--col">
    <!-- main content -->
  </div>

  <div class="title_bar">
    <span class="title">{{ title }}</span>
    <span class="instance">{{ date }}</span>
  </div>
  ```
- **Containers**: `layout--col`, `layout--row`, `flex`, `flex--row`, `flex--col`, `flex--between`, `flex--center`, `flex--center-y`, `flex--end`.
- **Flex growth & shrinking**:
  - `stretch-x` (grow horizontally in row / vertically in col; includes `min-width: 0`).
  - `stretch-y` (grow vertically in row / horizontally in col; includes `min-height: 0`).
  - `shrink-0` (prevent shrinking).
  - `w--full`, `h--full`.
- **Grids**: `grid grid--cols-2`, `grid grid--cols-4`, `col--span-2` (note: `.grid` has built-in column gaps; do not use `.grid` for zero-gap crossword cells).
- **Spacing**: `gap--small`, `gap--medium`, `gap--large`, `mb--1`, `mb--2`, `mt--1`, `mt--2`, `px--1`, `px--2`.
- **Dividers**: `<div class="divider"></div>` (horizontal) and `<div class="divider--v portrait:hidden"></div>` (vertical).

---

## 3. Typography & Components

- **Headings & Values**:
  - `.value .value--small`, `.value--base`, `.value--large` (inside `.item > .meta + .content`).
  - `.title .title--small`, `.title--base`, `.title--large`.
- **Body & Labels**:
  - `.description` — standard readable prose (`text--left`).
  - `.label .label--small`, `.label--base` — uppercase/metadata labels.
  - `.label--inverted` — solid black pill with white text (great for status/category badges, pair with `px--2`).
  - `.label--underline` — underlined section header.
- **KPI Item**:
  ```liquid
  <div class="item">
    <div class="meta"></div>
    <div class="content">
      <span class="value value--base lg:value--large">{{ metric }}</span>
      <span class="label label--base">Label</span>
    </div>
  </div>
  ```

---

## 4. Styles (`bg--*`, `rounded`, `text-stroke`, `border--*`)

Take advantage of TRMNL v3.4's rebuilt 14-step shade & style utilities (which automatically dither on 1-bit displays and render solid on 2-bit/4-bit displays):

- **Backgrounds (`bg--{token}`)**:
  - 14-step grayscale scale: `bg--gray-10` through `bg--gray-75` (steps of 5: `10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75`), plus `bg--black` and `bg--white`.
  - Great for subtle card containers (e.g., `bg--gray-70 rounded p--3` or `bg--gray-65 rounded`).
  - Chromatic tokens (e.g., `bg--red-40`) fall back to dithered gray on 1-bit and render color on color/4-bit screens.
- **Rounded Corners (`rounded`)**:
  - Use `rounded` (and size/corner modifiers) on cards, badges, and images (`v3.4` fixes clipped card borders).
- **Text Stroke (`text-stroke`)**:
  - Use when placing text over dithered `bg--gray-*` backgrounds so characters stay razor-sharp:
  - Widths: `text-stroke--small` (`2px`), `text-stroke--base` (`3.5px`), `text-stroke--medium` (`4.5px`), `text-stroke--large` (`6px`), `text-stroke--xlarge` (`7.5px`).
  - Shades: `text-stroke--white` / `text-stroke--{shade}`.
- **Borders (`border--h-{step}`, `border--v-{step}`)**:
  - Horizontal and vertical rules on the same `10..75` shade scale (note: older `border--h-1..7` classes are deprecated in 3.x).
  - For standard section rules, prefer `<div class="divider"></div>` or `<div class="divider--v portrait:hidden"></div>`.

---

## 5. Images, Dithering & Vector SVGs

- **Raster images**: Use `<img src="{{ url }}" class="image image-dither w--full h--[82cqh] object--contain rounded" />` so TRMNL's renderer dithers continuous-tone photos/artwork for 1-bit/2-bit ePaper.
- **1-Bit Vector SVGs**:
  - For charts, gauges, maps, and pixel art, use inline `<svg viewBox="...">`.
  - Add `shape-rendering="crispEdges"` on pixel-art SVGs to prevent hairline anti-aliasing gaps.
  - Add `preserveAspectRatio="none"` on progress bars / sparklines / bar charts that stretch to `w--full`.

---

## 6. Multi-View Guidelines

Every plugin should provide all 4 views:
- `template.liquid` (packaged as `full.liquid`) — Full `800×480`
- `half_horizontal.liquid` — `800×240` (keep compact, side-by-side `flex--row`)
- `half_vertical.liquid` — `400×480` (stacked `flex--col`, fewer list items)
- `quadrant.liquid` — `400×240` (essential KPI + primary visual or top 2 items only)

---

## 7. `settings.yml` & ZIP Packaging Rules

1. **ZIP root structure**: Place `settings.yml`, `full.liquid`, `half_horizontal.liquid`, `half_vertical.liquid`, and `quadrant.liquid` directly at the **root** of the `.zip` (not inside `src/`).
2. **`settings.yml` required fields**:
   - `description`: **≤ 35 characters** (also match inside `author_bio.description`).
   - `strategy: polling`, `polling_url`, `polling_verb: get`, `polling_headers: ""`, `refresh_interval` (`60` for hourly, `1440` for daily), `dark_mode: "no"`, `no_screen_padding: "no"`.
   - `author_bio.category` must be an approved value from `https://trmnl.com/api/categories` (e.g. `art`, `education`, `finance`, `games`, `nature`, `programming`, `sports`, `travel`, `weather` — note `science` is **not** approved; use `education` or `discovery`).
   - `author_bio.email_address`: `ervansetiawan@gmail.com`.
3. **Local preview (`trmnlp serve`)**:
   - `trmnlp` expects `.trmnlp.yml` and `src/` (`full.liquid`, `half_horizontal.liquid`, `half_vertical.liquid`, `quadrant.liquid`, `settings.yml`).
   - Set `strategy: static` in `src/settings.yml` when previewing `.trmnlp.yml` `variables:` locally, while keeping `strategy: polling` in the root `settings.yml` for production ZIPs.
