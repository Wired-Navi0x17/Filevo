"""Vector-like high-resolution icon generator for Sortwise.

Draws 256x256 supersampled icons with anti-aliasing and downsamples with
LANCZOS to 128x128 RGBA PNGs into ``src/assets/icons``.
"""

from __future__ import annotations

import math
from pathlib import Path
from PIL import Image, ImageDraw

ICON_DIR = Path(__file__).resolve().parent / "assets" / "icons"
ICON_DIR.mkdir(parents=True, exist_ok=True)

S = 256  # canvas size (supersampled)
TARGET = 128


def new_canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    return img, draw


def save_icon(img: Image.Image, name: str) -> None:
    scaled = img.resize((TARGET, TARGET), resample=Image.Resampling.LANCZOS)
    out_path = ICON_DIR / name
    scaled.save(out_path, format="PNG")


# ── Draw helpers ─────────────────────────────────────────────────────────────
def draw_folder_base(draw: ImageDraw.ImageDraw, tint: str = "#3b82f6") -> None:
    # Back tab
    draw.rounded_rectangle([28, 44, 114, 96], radius=14, fill="#1c212b", outline="#343c4d", width=3)
    # Main folder body
    draw.rounded_rectangle([20, 68, 236, 216], radius=20, fill="#1e2430", outline="#394254", width=4)
    # Subtle accent stripe / lip at top of folder body
    draw.rounded_rectangle([22, 68, 234, 88], radius=8, fill="#272f3f")
    # Soft corner highlight
    draw.line([(32, 70), (224, 70)], fill="#4a556b", width=2)


def make_folder_default() -> None:
    img, draw = new_canvas()
    draw_folder_base(draw)
    save_icon(img, "folder-default.png")


def make_folder_blue() -> None:
    img, draw = new_canvas()
    # Vibrant blue accent folder
    draw.rounded_rectangle([28, 44, 114, 96], radius=14, fill="#1d4ed8", outline="#3b82f6", width=3)
    draw.rounded_rectangle([20, 68, 236, 216], radius=20, fill="#2563eb", outline="#60a5fa", width=4)
    draw.rounded_rectangle([22, 68, 234, 88], radius=8, fill="#3b82f6")
    draw.line([(32, 70), (224, 70)], fill="#93c5fd", width=2)
    save_icon(img, "folder-blue.png")


def make_folder_documents() -> None:
    img, draw = new_canvas()
    draw_folder_base(draw)
    # Document sheet peek
    draw.rounded_rectangle([80, 100, 176, 184], radius=10, fill="#2c3444", outline="#475569", width=3)
    # Document lines
    draw.line([(98, 126), (158, 126)], fill="#94a3b8", width=4)
    draw.line([(98, 144), (158, 144)], fill="#94a3b8", width=4)
    draw.line([(98, 162), (138, 162)], fill="#64748b", width=4)
    save_icon(img, "folder-documents.png")


def make_folder_downloads() -> None:
    img, draw = new_canvas()
    draw_folder_base(draw)
    # Tray
    draw.line([(88, 172), (88, 186), (168, 186), (168, 172)], fill="#38bdf8", width=5)
    # Down arrow
    draw.line([(128, 108), (128, 164)], fill="#38bdf8", width=6)
    draw.polygon([(112, 148), (144, 148), (128, 168)], fill="#38bdf8")
    save_icon(img, "folder-downloads.png")


def make_folder_aiml() -> None:
    img, draw = new_canvas()
    draw_folder_base(draw)
    # Central AI chip
    draw.rounded_rectangle([100, 114, 156, 170], radius=8, fill="#1e1b4b", outline="#818cf8", width=4)
    # Core
    draw.rounded_rectangle([114, 128, 142, 156], radius=4, fill="#6366f1")
    # Chip pins
    for y in (126, 142, 158):
        draw.line([(88, y), (100, y)], fill="#a5b4fc", width=3)
        draw.line([(156, y), (168, y)], fill="#a5b4fc", width=3)
    for x in (114, 128, 142):
        draw.line([(x, 102), (x, 114)], fill="#a5b4fc", width=3)
        draw.line([(x, 170), (x, 182)], fill="#a5b4fc", width=3)
    save_icon(img, "folder-aiml.png")


def make_folder_algorithms() -> None:
    img, draw = new_canvas()
    draw_folder_base(draw)
    # Tree graph: root (128, 112), left (92, 164), right (164, 164)
    draw.line([(128, 116), (92, 160)], fill="#34d399", width=4)
    draw.line([(128, 116), (164, 160)], fill="#34d399", width=4)
    # Node circles
    draw.ellipse([114, 102, 142, 130], fill="#064e3b", outline="#10b981", width=4)
    draw.ellipse([78, 148, 106, 176], fill="#064e3b", outline="#10b981", width=4)
    draw.ellipse([150, 148, 178, 176], fill="#064e3b", outline="#10b981", width=4)
    save_icon(img, "folder-algorithms.png")


def make_folder_calculus() -> None:
    img, draw = new_canvas()
    draw_folder_base(draw)
    # Integral symbol ∫
    points = [
        (148, 106), (138, 102), (128, 108), (128, 168), (118, 178), (108, 174)
    ]
    # Draw curve
    for i in range(len(points) - 1):
        draw.line([points[i], points[i+1]], fill="#f43f5e", width=6)
    # dx
    draw.ellipse([148, 144, 158, 154], fill="#fb7185")
    draw.line([(158, 138), (158, 158)], fill="#fb7185", width=3)
    save_icon(img, "folder-calculus.png")


def make_folder_datascience() -> None:
    img, draw = new_canvas()
    draw_folder_base(draw)
    # Bar chart
    bars = [
        ([84, 152, 104, 184], "#059669"),
        ([110, 132, 130, 184], "#10b981"),
        ([136, 114, 156, 184], "#34d399"),
        ([162, 100, 182, 184], "#6ee7b7"),
    ]
    for bbox, col in bars:
        draw.rounded_rectangle(bbox, radius=3, fill=col)
    # Trend line
    draw.line([(94, 146), (120, 126), (146, 108), (172, 94)], fill="#ffffff", width=3)
    save_icon(img, "folder-datascience.png")


def make_folder_cybersecurity() -> None:
    img, draw = new_canvas()
    draw_folder_base(draw)
    # Shield
    shield = [(128, 104), (166, 116), (166, 150), (128, 184), (90, 150), (90, 116)]
    draw.polygon(shield, fill="#78350f", outline="#f59e0b", width=4)
    # Keyhole
    draw.ellipse([122, 132, 134, 144], fill="#fef3c7")
    draw.polygon([(124, 142), (132, 142), (130, 156), (126, 156)], fill="#fef3c7")
    save_icon(img, "folder-cybersecurity.png")


def make_folder_cloud() -> None:
    img, draw = new_canvas()
    draw_folder_base(draw)
    # Cloud puffs
    draw.ellipse([96, 128, 134, 166], fill="#38bdf8")
    draw.ellipse([122, 112, 164, 154], fill="#38bdf8")
    draw.ellipse([150, 128, 180, 166], fill="#38bdf8")
    draw.rounded_rectangle([108, 142, 172, 166], radius=8, fill="#38bdf8")
    save_icon(img, "folder-cloud.png")
    save_icon(img, "folder-cloudcomputing.png")


def make_folder_games() -> None:
    img, draw = new_canvas()
    draw_folder_base(draw)
    # Gamepad body
    draw.rounded_rectangle([86, 118, 170, 166], radius=16, fill="#312e81", outline="#a855f7", width=4)
    # D-pad
    draw.line([(102, 134), (102, 150)], fill="#c084fc", width=4)
    draw.line([(94, 142), (110, 142)], fill="#c084fc", width=4)
    # Buttons
    draw.ellipse([144, 132, 152, 140], fill="#f43f5e")
    draw.ellipse([154, 142, 162, 150], fill="#10b981")
    save_icon(img, "folder-games.png")


def make_folder_music() -> None:
    img, draw = new_canvas()
    draw_folder_base(draw)
    # Beamed notes
    draw.ellipse([98, 154, 118, 174], fill="#ec4899")
    draw.ellipse([144, 144, 164, 164], fill="#ec4899")
    draw.line([(116, 164), (116, 114)], fill="#f472b6", width=4)
    draw.line([(162, 154), (162, 104)], fill="#f472b6", width=4)
    draw.line([(116, 114), (164, 104)], fill="#f472b6", width=6)
    save_icon(img, "folder-music.png")


def make_folder_pictures() -> None:
    img, draw = new_canvas()
    draw_folder_base(draw)
    # Picture frame
    draw.rounded_rectangle([86, 108, 170, 172], radius=8, fill="#0f172a", outline="#38bdf8", width=3)
    # Sun
    draw.ellipse([140, 118, 154, 132], fill="#facc15")
    # Mountain
    draw.polygon([(94, 166), (122, 134), (142, 156), (154, 144), (164, 166)], fill="#0284c7")
    save_icon(img, "folder-pictures.png")


def make_folder_videos() -> None:
    img, draw = new_canvas()
    draw_folder_base(draw)
    # Film frame
    draw.rounded_rectangle([86, 110, 170, 170], radius=10, fill="#18181b", outline="#a1a1aa", width=3)
    # Play triangle
    draw.polygon([(118, 126), (146, 140), (118, 154)], fill="#ef4444")
    save_icon(img, "folder-videos.png")


def make_disk() -> None:
    img, draw = new_canvas()
    # HDD chassis
    draw.rounded_rectangle([32, 28, 224, 228], radius=24, fill="#1b202c", outline="#3b4458", width=4)
    # Top plate recess
    draw.rounded_rectangle([44, 40, 212, 216], radius=18, fill="#141822", outline="#293040", width=2)
    # Magnetic Platter
    draw.ellipse([64, 52, 192, 180], fill="#262d3d", outline="#475569", width=4)
    draw.ellipse([88, 76, 168, 156], fill="#1c2230", outline="#64748b", width=2)
    # Spindle
    draw.ellipse([114, 102, 142, 130], fill="#94a3b8", outline="#e2e8f0", width=3)
    draw.ellipse([124, 112, 132, 120], fill="#0f172a")
    # Read/Write Arm
    draw.line([(128, 116), (184, 164)], fill="#cbd5e1", width=5)
    draw.ellipse([180, 160, 192, 172], fill="#f59e0b")
    # Status LED
    draw.ellipse([54, 194, 66, 206], fill="#10b981")
    save_icon(img, "disk.png")


def draw_doc_base(draw: ImageDraw.ImageDraw, badge_text: str, badge_col: str) -> None:
    # Page with folded corner
    # Points: top-left, fold-start-x, fold-y-start, right-edge, bottom-right, bottom-left
    page = [
        (48, 24), (160, 24), (208, 72), (208, 232), (48, 232)
    ]
    draw.polygon(page, fill="#1c212c", outline="#384357", width=4)
    # Fold triangle
    draw.polygon([(160, 24), (160, 72), (208, 72)], fill="#293243", outline="#384357", width=3)
    # Badge rectangle
    draw.rounded_rectangle([68, 116, 188, 160], radius=8, fill=badge_col)
    # Label simulated text bar inside badge
    draw.line([(88, 138), (168, 138)], fill="#ffffff", width=6)
    # Sheet text lines
    draw.line([(68, 88), (140, 88)], fill="#64748b", width=4)
    draw.line([(68, 180), (188, 180)], fill="#475569", width=4)
    draw.line([(68, 198), (152, 198)], fill="#475569", width=4)


def make_file_pdf() -> None:
    img, draw = new_canvas()
    draw_doc_base(draw, "PDF", "#dc2626")
    save_icon(img, "file-pdf.png")


def make_file_docx() -> None:
    img, draw = new_canvas()
    draw_doc_base(draw, "DOCX", "#2563eb")
    save_icon(img, "file-docx.png")


def make_file_pptx() -> None:
    img, draw = new_canvas()
    draw_doc_base(draw, "PPTX", "#ea580c")
    save_icon(img, "file-pptx.png")


def make_file_text() -> None:
    img, draw = new_canvas()
    # Simple plain text document
    draw_doc_base(draw, "TXT", "#475569")
    save_icon(img, "file-text.png")


def main() -> None:
    make_disk()
    make_file_pdf()
    make_file_docx()
    make_file_pptx()
    make_file_text()
    make_folder_default()
    make_folder_blue()
    make_folder_documents()
    make_folder_downloads()
    make_folder_aiml()
    make_folder_algorithms()
    make_folder_calculus()
    make_folder_datascience()
    make_folder_cybersecurity()
    make_folder_cloud()
    make_folder_games()
    make_folder_music()
    make_folder_pictures()
    make_folder_videos()
    print("Successfully generated 128x128 crisp anti-aliased icons.")


if __name__ == "__main__":
    main()
