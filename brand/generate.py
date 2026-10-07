"""Generates every Launder logo asset from one geometry definition.

    python brand/generate.py

The symbol: a water drop (cleanliness, water) cut by a single fabric wave (movement), with a small teal
"fresh" dot. SVGs are written by hand-built paths; PNGs are rasterised from the same curves with PIL at 4x and
downsampled, so no Cairo/Inkscape dependency is needed.
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
PRIMARY, TEAL, WHITE, INK = "#0F4C81", "#14B8A6", "#FFFFFF", "#1E293B"

# Geometry on a 64x64 grid.
DROP = [((32, 5), (32, 5), (13, 25), (13, 39)), ((13, 39), (13, 50.5), (21.5, 59), (32, 59)),
        ((32, 59), (42.5, 59), (51, 50.5), (51, 39)), ((51, 39), (51, 25), (32, 5), (32, 5))]
WAVE = [((19, 41), (24, 35.5), (28, 35.5), (32, 41)), ((32, 41), (36, 46.5), (40, 46.5), (45, 41))]
DOT = (48.5, 12.5, 4.5)

DROP_D = "M32 5C32 5 13 25 13 39C13 50.5 21.5 59 32 59C42.5 59 51 50.5 51 39C51 25 32 5 32 5Z"
WAVE_D = "M19 41C24 35.5 28 35.5 32 41C36 46.5 40 46.5 45 41"


def symbol_svg(drop=PRIMARY, wave=WHITE, dot=TEAL, size=64) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="{size}" height="{size}" role="img" aria-label="Launder">'
            f'<path d="{DROP_D}" fill="{drop}"/>'
            f'<path d="{WAVE_D}" fill="none" stroke="{wave}" stroke-width="4.5" stroke-linecap="round"/>'
            f'<circle cx="{DOT[0]}" cy="{DOT[1]}" r="{DOT[2]}" fill="{dot}"/></svg>\n')


def horizontal_svg(text=INK, drop=PRIMARY, wave=WHITE, dot=TEAL) -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 236 64" width="236" height="64" role="img" aria-label="Launder">'
            f'<path d="{DROP_D}" fill="{drop}"/>'
            f'<path d="{WAVE_D}" fill="none" stroke="{wave}" stroke-width="4.5" stroke-linecap="round"/>'
            f'<circle cx="{DOT[0]}" cy="{DOT[1]}" r="{DOT[2]}" fill="{dot}"/>'
            f'<text x="66" y="44" font-family="Manrope, \'DM Sans\', Arial, sans-serif" font-size="34" font-weight="700" '
            f'letter-spacing="-0.5" fill="{text}">Launder</text></svg>\n')


def bezier(p0, p1, p2, p3, steps=48):
    for i in range(steps + 1):
        t = i / steps
        mt = 1 - t
        yield (mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0],
               mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1])


def render(size: int, background: str | None, scale: float = 1.0, drop=PRIMARY, wave=WHITE, dot=TEAL) -> Image.Image:
    """Renders the symbol centred on a square canvas. `scale` < 1 leaves padding (needed for adaptive icons)."""
    ss = size * 4
    img = Image.new("RGBA", (ss, ss), background or (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    unit = ss * scale / 64
    offset = (ss - 64 * unit) / 2

    def pt(p):
        return (offset + p[0] * unit, offset + p[1] * unit)

    outline = [pt(p) for seg in DROP for p in bezier(*seg)]
    draw.polygon(outline, fill=drop)
    wave_pts = [pt(p) for i, seg in enumerate(WAVE) for p in list(bezier(*seg))[(1 if i else 0):]]
    half = 4.5 * unit / 2
    left, right = [], []
    for i, (x, y) in enumerate(wave_pts):  # offset the centre line along its normal to get a clean stroke outline
        ax, ay = wave_pts[max(i - 1, 0)]
        bx, by = wave_pts[min(i + 1, len(wave_pts) - 1)]
        dx, dy = bx - ax, by - ay
        length = (dx * dx + dy * dy) ** 0.5 or 1
        nx, ny = -dy / length * half, dx / length * half
        left.append((x + nx, y + ny))
        right.append((x - nx, y - ny))
    draw.polygon(left + right[::-1], fill=wave)
    for end in (wave_pts[0], wave_pts[-1]):
        draw.ellipse([end[0] - half, end[1] - half, end[0] + half, end[1] + half], fill=wave)
    cx, cy = pt(DOT[:2])
    r = DOT[2] * unit
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=dot)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    out = ROOT / "svg"
    out.mkdir(exist_ok=True)
    (out / "launder-symbol.svg").write_text(symbol_svg())
    (out / "launder-symbol-mono-dark.svg").write_text(symbol_svg(drop=INK, wave=WHITE, dot=INK))
    (out / "launder-symbol-mono-light.svg").write_text(symbol_svg(drop=WHITE, wave=PRIMARY, dot=WHITE))
    (out / "launder-logo-horizontal.svg").write_text(horizontal_svg())
    (out / "launder-logo-horizontal-dark-bg.svg").write_text(horizontal_svg(text=WHITE, drop=WHITE, wave=PRIMARY, dot=TEAL))

    png = ROOT / "png"
    png.mkdir(exist_ok=True)
    # Launcher icon: white tile, symbol at 68% so it survives rounded-square masks.
    render(1024, WHITE, 0.68).save(png / "app-icon-1024.png")
    # Android adaptive foreground: transparent, symbol inside the 66% safe zone.
    render(1024, None, 0.56).save(png / "app-icon-foreground-1024.png")
    # Splash mark and monochrome notification icon (Android requires white-on-transparent).
    render(512, None, 1.0).save(png / "splash-symbol-512.png")
    render(256, None, 0.9, drop=WHITE, wave=(0, 0, 0, 0), dot=WHITE).save(png / "notification-icon-256.png")
    for size in (32, 192, 512):
        render(size, WHITE, 0.8).save(png / f"favicon-{size}.png")
    print("Wrote", sorted(p.name for p in out.iterdir()) + sorted(p.name for p in png.iterdir()))


if __name__ == "__main__":
    main()
