"""Rebuild the atlas gallery from the Git snapshot preceding the atlas.

The originals stay in their versioned locations. Each manifest row is one source
occurrence. Matching saved bytes share a figure ID and one preview.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import html
import json
import re
import subprocess
import tempfile
import textwrap
from collections import Counter
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
from zipfile import ZipFile

import pandas as pd
from IPython.display import SVG, Markdown, display
from IPython.display import Image as NotebookImage
from matplotlib import get_data_path
from matplotlib.figure import Figure
from PIL import Image, ImageDraw, ImageFont, ImageOps

SOURCE_REF = "8de629a"
REPO = "https://github.com/FelixYu120/DSC-291-Final-Project"
ATLAS = "notebooks/zimbabwe_visual_atlas.ipynb"
PRESTO = "experiments/presto_debug/Presto_debug.ipynb"
PROJECT_MAP = "_parked/docs/archive/project_map_2026-10-25.html"
GROUPS = (
    "Standalone project figures",
    "Notebook figures",
    "Archived notebook figures",
    "Archived project diagrams",
    "Provider documentation figures",
    "Reconstructed v2 report figures",
    "Reconstructed Presto diagnostics",
)


class Snapshot:
    def __init__(self, root: Path, ref: str):
        self.root = root.resolve()
        self.commit = self.git("rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()
        files = self.git("ls-tree", "-r", "-z", "--name-only", self.commit).decode().split("\0")
        self.files = [p for p in files if p and p != ATLAS and not p.startswith("results/visual_atlas/")]

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args])

    def read(self, path):
        return self.git("show", f"{self.commit}:{path}")

    def table(self, path):
        return pd.read_csv(BytesIO(self.read(str(path))))

    def url(self, path):
        return f"{REPO}/blob/{self.commit}/{quote(path, safe='/')}"


@dataclass
class FigureItem:
    figure_id: str
    group: str
    title: str
    mime: str
    data: bytes
    figure_type: str
    description: str


class Gallery:
    def __init__(self, snapshot: Snapshot):
        self.snapshot = snapshot
        self.items: dict[str, FigureItem] = {}
        self.rows: list[dict[str, str]] = []
        self._ids: dict[str, str] = {}
        # Bind the descriptions to the reviewed image bytes: aliases share captions
        # and a newly inserted notebook cell cannot silently inherit the wrong one.
        with Path(__file__).with_name("atlas_gallery_captions.csv").open(encoding="utf-8", newline="") as f:
            self._captions = {row["sha256"]: (row["figure_type"], row["description"])
                              for row in csv.DictReader(f)}

    def add(self, group, title, path, location, data, mime="image/png", status="Saved", recipe="", archive_hash=""):
        digest = hashlib.sha256(data).hexdigest()
        if digest not in self._ids:
            figure_id = f"G{len(self.items) + 1:03d}"
            self._ids[digest] = figure_id
            figure_type, description = self._captions.get(digest, ("", ""))
            self.items[figure_id] = FigureItem(figure_id, group, title, mime, data, figure_type, description)
        figure_id = self._ids[digest]
        item = self.items[figure_id]
        self.rows.append({
            "figure_id": figure_id, "group": group, "title": title, "status": status,
            "source": path, "location": location, "source_url": self.snapshot.url(path),
            "recipe": recipe, "sha256": digest, "source_commit": self.snapshot.commit,
            "archived_render_sha256": archive_hash,
            "matches_archived_render": str(archive_hash == digest).lower() if archive_hash else "",
            "figure_type": item.figure_type, "description": item.description,
        })
        return figure_id

    def write_manifest(self, path):
        """Save every figure ID, location, source link and preview-content SHA-256."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(self.rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(self.rows)

    def counts(self):
        return dict(Counter(item.group for item in self.items.values()))


STANDALONE_TITLES = {
    "data/processed/zimbabwe_midterm_v1/data_overview.png": "Zimbabwe Lacuna data overview · v1",
    "data/processed/zimbabwe_midterm_v2/data_overview.png": "Zimbabwe Lacuna data overview · v2",
    "data/runs/zimbabwe_aggregation_v1/comparison.png": "Zimbabwe seasonal aggregation comparison · v1",
    "data/runs/zimbabwe_merge_v1/comparison.png": "Lacuna and Zimbabwe 2024 merge · v1",
    "data/runs/zimbabwe_transfer_diagnosis_v1/diagnosis.png": "Zimbabwe transfer diagnostics · v1",
    "data/runs/zimbabwe_weather_compact_v1/compact_weather_comparison.png": "Compact weather features · v1",
    "data/runs/zimbabwe_weather_v1/weather_comparison.png": "Full weather features · v1",
    "results/aggregation_v2/comparison.png": "Zimbabwe seasonal aggregation comparison · v2",
    "results/quality_remediation/point_area_example.png": "Point-to-field sampling support",
}


def _standalone_and_notebooks(gallery):
    snapshot = gallery.snapshot
    for path in snapshot.files:
        ext = Path(path).suffix.lower()
        if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"):
            continue
        title = STANDALONE_TITLES.get(path, Path(path).stem.replace("_", " "))
        mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml"}.get(ext, f"image/{ext[1:]}")
        gallery.add(GROUPS[0], title, path, "Image file", snapshot.read(path), mime)
    for path in (p for p in snapshot.files if p.endswith(".ipynb")):
        group = GROUPS[2] if path.startswith("_parked/") else GROUPS[1]
        heading = Path(path).stem.replace("_", " ")
        for cell_no, cell in enumerate(json.loads(snapshot.read(path))["cells"], 1):
            if cell["cell_type"] == "markdown":
                headings = re.findall(r"^#{1,6}\s+(.+)", "".join(cell["source"]), re.MULTILINE)
                if headings:
                    heading = headings[-1].strip()
            images = [(f"output {i}", out.get("data", {})) for i, out in enumerate(cell.get("outputs", []), 1)]
            images.extend((f"attachment {name}", value) for name, value in cell.get("attachments", {}).items())
            for position, payload in images:
                for mime, value in payload.items():
                    if mime.startswith("image/"):
                        value = "".join(value)
                        data = value.encode() if mime == "image/svg+xml" else base64.b64decode(value)
                        gallery.add(group, heading, path, f"cell {cell_no}, {position}", data, mime)


def _embedded_documents(gallery):
    snapshot = gallery.snapshot
    project_map = snapshot.read(PROJECT_MAP).decode()
    palette = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]+)", project_map.split("@media", 1)[0]))
    titles = ["From field observations to held-out yield estimates", "From one field to satellite inputs and a yield label",
              "Decision gates in the original experiment plan"]
    for i, (source, title) in enumerate(zip(re.findall(r"<svg\b.*?</svg>", project_map, re.DOTALL), titles, strict=True), 1):
        # The original HTML supplies CSS colors and HTML entities outside the SVG.
        standalone = re.sub(r"var\(--([\w-]+)\)", lambda m: palette[m.group(1)], source)
        standalone = re.sub(r"&([A-Za-z]+);", lambda m: m[0] if m[1] in {"amp", "quot", "lt", "gt", "apos"}
                            else html.unescape(m[0]), standalone)
        standalone = standalone.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" style="color:#24332b;font-family:sans-serif;background:white" ', 1)
        gallery.add(GROUPS[3], title, PROJECT_MAP, f"diagram {i}", standalone.encode(), "image/svg+xml")

    manual = next(p for p in snapshot.files if p.startswith("data/raw/zimbabwe/") and p.endswith(".slides.html"))
    pdf = next(p for p in snapshot.files if p.startswith("data/raw/zimbabwe/") and p.endswith(".pdf"))
    figures = re.findall(r'<img\b[^>]*\bsrc="data:image/png;base64,([^"]+)"', snapshot.read(manual).decode(), re.IGNORECASE)
    # Reviewed the PDF's ten images against the HTML export at the source revision.
    pages = [2, 3, 6, 7, 8, 9, 11, 12, 15, 16]
    titles = ["Yield histogram", "Yield versus yield divided by 100", "Training predictions", "Testing predictions",
              "Feature importance", "Tuned feature importance", "Raster prediction", "Yield histogram",
              "Crop mask feature importance", "Crop mask raster prediction"]
    for i, (figure, page, title) in enumerate(zip(figures, pages, titles, strict=True), 1):
        data = base64.b64decode(figure)
        title = f"Lacuna provider manual · {title}"
        gallery.add(GROUPS[4], title, manual, f"HTML figure {i}", data)
        gallery.add(GROUPS[4], title, pdf, f"page {page}", data, status="Same image in PDF")

    manual = next(p for p in snapshot.files if p.startswith("data/raw/malawi/") and p.endswith(".docx"))
    with ZipFile(BytesIO(snapshot.read(manual))) as doc:
        for member, title in [("word/media/image1.png", "Malawi village sampling frame"),
                              ("word/media/image2.png", "Malawi crop-cut placement")]:
            gallery.add(GROUPS[4], title, manual, member, doc.read(member))


def _v2_report_figures(gallery):
    # Invoke only figure writers, using committed score tables and zero model fits.
    import matplotlib

    from cropyield.experiments import (
        zimbabwe_diagnosis,
        zimbabwe_merge,
        zimbabwe_weather,
        zimbabwe_weather_compact,
    )

    s = gallery.snapshot
    merge = "results/merge_v2/merge"
    diagnosis = "results/merge_v2/diagnosis"
    compact = "results/weather_v2/compact"
    full = "results/weather_v2/full"
    cells = s.table("data/processed/zimbabwe_weather_v2/weather_matched_cells.csv")
    matched = cells.groupby("season_year", as_index=False).mean(numeric_only=True)
    recipes = [
        (merge, "comparison.png", "Lacuna and Zimbabwe 2024 merge · v2", zimbabwe_merge.plot_results,
         [s.table(f"{merge}/metrics.csv"), s.table(f"{merge}/paired_differences.csv"),
          json.loads(s.read("configs/zimbabwe_merge_v2.json"))]),
        (diagnosis, "diagnosis.png", "Zimbabwe transfer diagnostics · v2", zimbabwe_diagnosis.plot_diagnosis,
         [s.table(f"{diagnosis}/{name}.csv") for name in
          ("metrics", "paired_differences", "error_decomposition", "source_metrics")]),
        (full, "weather_comparison.png", "Full weather features · v2", zimbabwe_weather.plot_results,
         [s.table(f"{full}/metrics.csv"), s.table(f"{full}/paired_differences.csv"), matched]),
        (compact, "compact_weather_comparison.png", "Compact weather features · v2",
         zimbabwe_weather_compact.plot_results, [s.table(f"{compact}/metrics.csv")]),
    ]
    backend = matplotlib.get_backend()
    try:
        with matplotlib.rc_context(), tempfile.TemporaryDirectory() as d:
            matplotlib.rcdefaults()
            for folder, name, title, writer, args in recipes:
                dst = Path(d) / name
                writer(dst, *args)
                manifest = json.loads(s.read(f"{folder}/manifest.json"))
                gallery.add(GROUPS[5], title, f"{folder}/RESULTS.md", f"report link {name}", dst.read_bytes(),
                            status="Reconstructed", recipe=f"{writer.__module__}.{writer.__name__}",
                            archive_hash=manifest["outputs"][name]["sha256"])
    finally:
        if matplotlib.get_backend() != backend:
            matplotlib.use(backend)


def _presto_figures(gallery):
    for stage in ("one", "two", "none", "light", "medium", "strong"):
        base = f"experiments/presto_debug/runs/latest/{stage}"
        history = gallery.snapshot.table(f"{base}/history.csv")
        for title, columns, ylabel in [
            ("loss", ("train_mse", "fit_mode_mse", "val_mse"), "MSE (t/ha)²"),
            ("gradient norms", ("encoder_grad_norm", "head_grad_norm"), "L2 gradient norm"),
        ]:
            fig = Figure(figsize=(8, 3.6), layout="constrained")
            ax = fig.subplots()
            for col in columns:
                if col in history and history[col].notna().any():
                    ax.plot(history.epoch, history[col], label=col)
            ax.set(title=f"Presto {stage} · {title}", xlabel="Epoch", ylabel=ylabel)
            ax.grid(alpha=.25)
            ax.legend()
            buf = BytesIO()
            fig.savefig(buf, format="png", dpi=110)
            gallery.add(GROUPS[6], f"Presto {stage} · {title}", f"{base}/history.csv", stage, buf.getvalue(),
                        status="Reconstructed", recipe=f"{PRESTO}, cell 11")

        table = gallery.snapshot.table(f"{base}/predictions.csv")
        fig = Figure(figsize=(5, 5), layout="constrained")
        ax = fig.subplots()
        for split, rows in table.groupby("split"):
            ax.scatter(rows.observed, rows.predicted, s=20, alpha=.65, label=str(split))
        values = pd.concat([table.observed, table.predicted]).dropna()
        limits = [values.min(), values.max()]
        ax.plot(limits, limits, "--", color="gray")
        ax.set(title=f"Presto {stage}", xlabel="Observed yield (t/ha)", ylabel="Predicted yield (t/ha)")
        ax.grid(alpha=.25)
        ax.legend()
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=110)
        gallery.add(GROUPS[6], f"Presto {stage} · observed and predicted", f"{base}/predictions.csv", stage,
                    buf.getvalue(), status="Reconstructed", recipe=f"{PRESTO}, cell 13")


def collect_gallery(root, ref=SOURCE_REF):
    """Return all catalogued figures and per-occurrence provenance at the atlas baseline."""
    gallery = Gallery(Snapshot(Path(root), ref))
    _standalone_and_notebooks(gallery)
    _embedded_documents(gallery)
    _v2_report_figures(gallery)
    _presto_figures(gallery)
    return gallery


def show_figure(gallery, figure_id, *, with_caption=True):
    """Display the original full-resolution figure (or reconstructed chart)."""
    item = gallery.items[figure_id]
    if item.mime == "image/svg+xml":
        display(SVG(data=item.data.decode()))
    else:
        display(NotebookImage(data=item.data))
    if with_caption and item.description:
        display(Markdown(f"**{figure_id} · {item.figure_type}.** {item.description}"))


def _sheet(items):
    """Create a two-column contact sheet. Figure IDs resolve to full-size images."""
    width, chart_height, label_height = 650, 340, 56
    rows = (len(items) + 1) // 2
    page = Image.new("RGB", (width * 2, (chart_height + label_height + 16) * rows), "#ffffff")
    draw = ImageDraw.Draw(page)
    font = ImageFont.truetype(str(Path(get_data_path()) / "fonts/ttf/DejaVuSans.ttf"), 18)
    for i, item in enumerate(items):
        x, y = i % 2 * width, i // 2 * (chart_height + label_height + 16)
        caption = textwrap.fill(f"{item.figure_id}  {item.title}", width=60, max_lines=2, placeholder="…")
        draw.multiline_text((x + 12, y + 6), caption, font=font, fill="#172e37", spacing=3)
        with Image.open(BytesIO(item.data)) as raw:
            img = ImageOps.contain(raw.convert("RGBA"), (width - 18, chart_height), Image.Resampling.LANCZOS)
            pos = (x + (width - img.width) // 2, y + label_height + (chart_height - img.height) // 2)
            page.paste(img, pos, img)
    buffer = BytesIO()
    page.save(buffer, format="JPEG", quality=84, optimize=True, subsampling=0)
    return buffer.getvalue()


def show_gallery(gallery, group=None):
    """Display each unique visual once, with linked source locations under its preview."""
    groups = GROUPS if group is None else (group,)
    for section in groups:
        source_ids = {row["figure_id"] for row in gallery.rows if row["group"] == section}
        items = [item for item in gallery.items.values() if item.group == section]
        display(Markdown(f"### {section}\n\n{len(items)} unique previews · {len(source_ids)} figures referenced in this section."))
        for start in range(0, len(items), 6):
            chunk = items[start:start + 6]
            if chunk[0].mime == "image/svg+xml":
                for item in chunk:
                    display(Markdown(f"**{item.figure_id} · {item.title}**"))
                    show_figure(gallery, item.figure_id, with_caption=False)
            else:
                display(NotebookImage(data=_sheet(chunk), format="jpeg", width=1150))
            links = []
            for item in chunk:
                sources = [row for row in gallery.rows if row["figure_id"] == item.figure_id]
                refs = [f"[{Path(row['source']).name} · {row['location']}]({row['source_url']})" for row in sources]
                caption = f"{item.description} " if item.description else ""
                links.append(f"- **{item.figure_id}** {caption}{' · '.join(refs)}")
            display(Markdown("\n\n".join(links)))
