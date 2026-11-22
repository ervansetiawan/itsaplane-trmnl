# TRMNL Plugin Development & Packaging Guide

Instructions for adding, previewing, testing, and packaging TRMNL plugins in this repository (`itsaplane-trmnl`).

---

## 1. Backend Endpoint (`app.py` + Module)

1. **Create a module** (e.g., `my_plugin.py`) exposing a Flask `Blueprint` (preferred over adding large handlers directly into `app.py`):
   ```python
   from flask import Blueprint, jsonify

   my_plugin_bp = Blueprint("my_plugin", __name__)

   @my_plugin_bp.route("/my_endpoint", methods=["GET"])
   def my_endpoint():
       return jsonify({...})
   ```
2. **Register it in `app.py`**:
   ```python
   from my_plugin import my_plugin_bp
   app.register_blueprint(my_plugin_bp)
   ```
3. **API & Image Best Practices**:
   - Reuse a `requests.Session()` with a `User-Agent` header.
   - Add a short in-memory TTL cache (`15–30s`), retry once on `HTTP 429` (`~1.1s` backoff), and configure a fallback provider when possible.
   - Return real upstream error codes (`429`, `502`, `504`) instead of masking failures as `404`.
   - For slow static geometry/map data (e.g., Overpass/OSM), cache results on disk under `cache/` and commit the pre-warmed cache so Render cold starts respond immediately.
   - For ePaper graphics, render 4-shade (`0, 85, 170, 255`) PNGs and return them as `data:image/png;base64,...` data URIs.

---

## 2. TRMNL Framework v3.4 Templates (`plugins/<plugin-name>/`)

Follow `.agents/skills/trmnl-framework-3-4/SKILL.md`:

- **No `<style>` blocks** and **no inline `style="..."` attributes**.
- Include responsive `portrait:` and `lg:` utility classes.
- Keep `<img>` aspect ratios intact (`w--auto h--full` or exact `w--[432px] h--[324px]`) so pixels remain 1:1 square.
- Required files inside `plugins/<plugin-name>/`:
  - `src/full.liquid` (`800×480`)
  - `src/half_horizontal.liquid` (`800×240`)
  - `src/half_vertical.liquid` (`400×480`)
  - `src/quadrant.liquid` (`400×240`)
  - `src/settings.yml`
  - `.trmnlp.yml`
  - Root copies matching the other plugins: `template.liquid` (copy of `src/full.liquid`), `half_horizontal.liquid`, `half_vertical.liquid`, `quadrant.liquid`, and `settings.yml`.
- **`settings.yml` rules**:
  - `strategy: polling`
  - `polling_url: 'https://itsaplane-trmnl.onrender.com/<endpoint>'`
  - `description` (and `author_bio.description`): **≤ 35 characters**
  - `author_bio.category`: approved TRMNL category (`art`, `education`, `finance`, `games`, `nature`, `programming`, `sports`, `travel`, `weather`, etc.).

---

## 3. Local Preview (`trmnlp serve`)

1. Start the Flask backend locally (e.g., on port `5000` or `5001`).
2. Temporarily point `polling_url` in `plugins/<plugin-name>/src/settings.yml` to `http://127.0.0.1:<port>/<endpoint>` (or use `strategy: static` with `.trmnlp.yml` `variables:`).
3. Run:
   ```powershell
   trmnlp serve -d plugins/<plugin-name> -p 4568
   ```
4. Open `http://127.0.0.1:4568` and verify **Full**, **Half Horizontal**, **Half Vertical**, and **Quadrant** views, then restore `polling_url` to `https://itsaplane-trmnl.onrender.com/<endpoint>`.

---

## 4. Packaging (`dist/<plugin-name>.zip`)

Package the 5 files from `src/` directly at the **root** of `dist/<plugin-name>.zip` (never nested under `src/`):

```powershell
python -c "
import shutil, zipfile, pathlib
name = '<plugin-name>'
root = pathlib.Path('plugins') / name
src = root / 'src'
shutil.copy2(src / 'settings.yml', root / 'settings.yml')
shutil.copy2(src / 'full.liquid', root / 'template.liquid')
for f in ['half_horizontal.liquid', 'half_vertical.liquid', 'quadrant.liquid']:
    shutil.copy2(src / f, root / f)
with zipfile.ZipFile(pathlib.Path('dist') / f'{name}.zip', 'w', zipfile.ZIP_DEFLATED) as zf:
    for f in ['settings.yml', 'full.liquid', 'half_horizontal.liquid', 'half_vertical.liquid', 'quadrant.liquid']:
        zf.write(src / f, arcname=f)
"
```

---

## 5. Lint, Test & Deploy

Run CI checks before committing and pushing to `main` (which triggers Render auto-deploy):

```powershell
.\trmnl\Scripts\python.exe -m pylint app.py <new_module>.py --fail-under=8
.\trmnl\Scripts\python.exe -m pytest tests/test_app.py -k "not test_rate_to_arrow_non_integer_string and not test_rate_to_arrow_float_string" -v
git add app.py <new_module>.py plugins/<plugin-name>
git commit -m "Add <plugin-name> plugin"
git push origin main
```
