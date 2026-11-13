#!/usr/bin/env python3


import argparse
import math
import time
import tkinter as tk
import tkinter.font as tkfont

sin, cos, sqrt, exp, pi = math.sin, math.cos, math.sqrt, math.exp, math.pi

TOP, BOTTOM = 4.2, -1.9
VIEW_X = 0.6  # world x shown at the center of the window


def _unit(x, y, z):
    n = sqrt(x * x + y * y + z * z)
    return x / n, y / n, z / n


# Sunlight from the upper left, toward the viewer.
LX, LY, LZ = _unit(-0.55, 0.7, 0.5)

RAMP = ":-=+*#%@@"  # sparse -> dense reads as dark -> bright on a dark background

BACKGROUND = "#0a2a23"
COLORS = {
    # water
    "wa1": "#14392f", "wa2": "#215546", "wa3": "#4a7f70", "wa4": "#a3c7ba", "wa5": "#e2f0ea",
    # white plumage
    "w0": "#69727a", "w1": "#a6adb4", "w2": "#dce1e5", "w3": "#ffffff",
    # creamy neck and head
    "c0": "#80725a", "c1": "#c2ae8b", "c2": "#e8d9ba", "c3": "#fff2da",
    # reflection of the swan in the water
    "r0": "#1d4239", "r1": "#335c53", "r2": "#557a72",
    # beak, face, eye
    "beak": "#f07a3c", "beak_d": "#a24a28", "blk": "#151515", "eye": "#000000",
    # twigs and reeds
    "reed1": "#4a3520", "reed2": "#7d6038",
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def shade(b, family):
    """Brightness in [0, 1] -> (ramp character, color tag like 'w2')."""
    b = 0.0 if b < 0 else (0.999 if b >= 1 else b)
    return RAMP[int(b * len(RAMP))], family + str(min(3, int(b * 4.6)))


def stroke_char(angle):
    """Pick the ASCII character that best matches a stroke direction (radians)."""
    a = math.degrees(angle) % 180
    if a < 22.5 or a >= 157.5:
        return "-"
    if a < 67.5:
        return "/"
    if a < 112.5:
        return "|"
    return "\\"


def ellipse_light(u, v):
    """Lambert lighting on a bulging ellipse, given normalized coords (u, v)."""
    q = u * u + v * v
    nz = sqrt(1.0 - q) if q < 1 else 0.0
    return u * LX + v * LY + nz * LZ


def catmull_rom(points, steps):
    """Smooth curve through (x, y, radius) control points."""
    out = []
    n = len(points)
    for i in range(n - 1):
        p0 = points[max(i - 1, 0)]
        p1, p2 = points[i], points[i + 1]
        p3 = points[min(i + 2, n - 1)]
        for k in range(steps):
            s = k / steps
            s2, s3 = s * s, s * s * s
            out.append(tuple(
                0.5 * (2 * p1[j] + (p2[j] - p0[j]) * s
                       + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * s2
                       + (3 * p1[j] - p0[j] - 3 * p2[j] + p3[j]) * s3)
                for j in range(3)))
    out.append(points[-1])
    return out


# ---------------------------------------------------------------------------
# The swan's pose for one moment in time (all in swan-local coordinates)
# ---------------------------------------------------------------------------
# Proportions measured from a reference photo of a mute swan (1 unit ~ body height).
NECK_POINTS = [  # (x, y, radius) from the chest up to the back of the head
    (-2.45, 0.40, 0.38), (-2.40, 0.85, 0.28), (-1.95, 1.25, 0.21), (-1.50, 1.80, 0.19),
    (-1.38, 2.25, 0.18), (-1.62, 2.55, 0.18), (-2.00, 2.50, 0.20),
]

BODY = (0.55, 0.22, 3.25, 0.78)                    # cx, cy, a, b
TAIL = (3.05, 0.50, 1.30, 0.36, math.radians(16))  # cx, cy, a, b, rotation
COVERTS = (0.45, 1.20, 1.45, 0.68, math.radians(24))
N_FEATHERS = 17


class Pose:
    def __init__(self, t):
        # Gentle drift across the pond and a slow bob on the water.
        self.ox = 0.6 * sin(t * 0.11)
        self.oy = 0.035 * sin(t * 1.3)

        # Neck sways a little; every so often the head dips toward the water.
        sway = 0.07 * sin(t * 0.7)
        dip = 0.18 * max(0.0, sin(t * 0.23)) ** 3
        pts = []
        last = len(NECK_POINTS) - 1
        for i, (x, y, r) in enumerate(NECK_POINTS):
            k = i / last
            pts.append((x + sway * k * k - dip * 0.4 * k ** 3, y - dip * k ** 3, r))
        curve = catmull_rom(pts, 6)
        self.neck = []
        total = len(curve) - 1
        for i in range(total):
            ax, ay, ar = curve[i]
            bx, by, br = curve[i + 1]
            dx, dy = bx - ax, by - ay
            self.neck.append((ax, ay, ar, dx, dy, dx * dx + dy * dy or 1e-9, br - ar, i / total))
        xs = [p[0] for p in curve]
        ys = [p[1] for p in curve]
        self.neck_box = (min(xs) - 0.6, max(xs) + 0.6, min(ys) - 0.6, max(ys) + 0.6)

        # Head at the end of the neck, pointing down and to the left.
        ex, ey, _ = pts[-1]
        self.head = (ex - 0.15, ey - 0.27, 0.34, 0.24, math.radians(-118))
        hx, hy, _, _, ha = self.head
        bx, by = hx + cos(ha) * 0.27, hy + sin(ha) * 0.27
        beak_angle = math.radians(-100)
        self.beak = (bx, by, cos(beak_angle), sin(beak_angle), 0.66)
        self.knob = (bx + 0.03, by + 0.08, 0.13)
        self.eye = (hx - 0.08, hy + 0.07)

        # Raised wing: a fan of long feathers that ruffle slightly.
        self.feathers = []
        for i in range(N_FEATHERS):
            k = i / (N_FEATHERS - 1)
            bx = -0.6 + 2.0 * k
            by = 1.45 - 0.4 * k
            ang = math.radians(70 - 32 * k + 2.5 * sin(t * 1.6 + i * 0.8))
            length = 1.5 + 0.8 * sin(pi * (0.15 + 0.7 * k))
            self.feathers.append((bx, by, cos(ang), sin(ang), length, ang, k))


def in_rot_ellipse(x, y, e):
    cx, cy, a, b, rot = e
    dx, dy = x - cx, y - cy
    c, s = cos(rot), sin(rot)
    u = (dx * c + dy * s) / a
    v = (-dx * s + dy * c) / b
    return u, v, u * u + v * v <= 1.0


def sample_swan(x, y, P):
    """Return (char, color tag) for swan-local point (x, y), or None."""
    if y < 0 or x < -3.2 or x > 4.6 or y > 3.8:
        return None

    # --- beak, black face and knob, head -------------------------------
    bx, by, bdx, bdy, blen = P.beak
    rx, ry = x - bx, y - by
    s = rx * bdx + ry * bdy
    if 0 <= s <= blen:
        perp = abs(-rx * bdy + ry * bdx)
        if perp < 0.15 - 0.10 * s / blen:
            if s > blen - 0.12:
                return "#", "blk"          # dark nail at the tip
            return ("@" if perp < 0.07 else "%"), ("beak" if ry * -bdx + rx * bdy < 0.02 else "beak_d")
    kx, ky, kr = P.knob
    if (x - kx) ** 2 + (y - ky) ** 2 < kr * kr:
        return "@", "blk"
    hx, hy = P.head[0], P.head[1]
    ex, ey = P.eye
    # black mask from the eye down to the beak
    mx, my = bx - ex, by - ey
    m2 = mx * mx + my * my
    ms = max(0.0, min(1.0, ((x - ex) * mx + (y - ey) * my) / m2))
    if (x - ex - ms * mx) ** 2 + (y - ey - ms * my) ** 2 < (0.06 + 0.07 * ms) ** 2:
        return "#", "blk"
    u, v, inside = in_rot_ellipse(x, y, P.head)
    if inside:
        return shade(0.45 + 0.6 * max(0.0, ellipse_light((x - hx) / 0.34, (y - hy) / 0.34)), "c")

    # --- neck ------------------------------------------------------------
    x0, x1, y0, y1 = P.neck_box
    if x0 <= x <= x1 and y0 <= y <= y1:
        best = None
        for ax, ay, ar, dx, dy, l2, dr, frac in P.neck:
            t = ((x - ax) * dx + (y - ay) * dy) / l2
            t = 0.0 if t < 0 else (1.0 if t > 1 else t)
            px, py = x - ax - t * dx, y - ay - t * dy
            d2 = px * px + py * py
            r = ar + t * dr
            if d2 < r * r and (best is None or d2 / (r * r) < best[0]):
                best = (d2 / (r * r), px / r, py / r, frac)
        if best is not None:
            _, nx, ny, frac = best
            nz = sqrt(max(0.0, 1 - nx * nx - ny * ny))
            light = nx * LX + ny * LY + nz * LZ
            b = 0.42 + 0.62 * max(0.0, light) + 0.05 * sin(y * 23)
            return shade(b, "w" if frac < 0.3 else "c")

    # --- wing coverts (the rounded mass of small feathers) ---------------
    u, v, inside = in_rot_ellipse(x, y, COVERTS)
    if inside:
        row = math.floor(v * 4)
        scallop = abs(sin(u * 7 + row * 1.7))
        b = (0.5 + 0.55 * max(0.0, ellipse_light(u, v))) * (0.82 + 0.18 * scallop)
        return shade(b, "w")

    # --- long flight feathers fanned upward ----------------------------
    for fx, fy, cdx, cdy, length, ang, k in P.feathers:
        rx, ry = x - fx, y - fy
        s = rx * cdx + ry * cdy
        if 0 <= s <= length:
            f = s / length
            perp = -rx * cdy + ry * cdx + 0.12 * f * f  # slight curve
            w = 0.17 * (1 - 0.75 * f)
            if abs(perp) < w:
                edge = abs(perp) / w
                # Each feather is a bundle of parallel strokes along its quill;
                # the lower edge falls into shadow, which separates the feathers.
                ch = stroke_char(ang)
                b = 1.0 - 0.2 * k - (0.45 if perp < -0.4 * w else 0.05 * edge) - (0.15 if f < 0.15 else 0.0)
                return ch, "w" + str(max(0, min(3, int(b * 4.6))))

    # --- body and tail ---------------------------------------------------
    cx, cy, a, b_ = BODY
    u, v = (x - cx) / a, (y - cy) / b_
    tu, tv, in_tail = in_rot_ellipse(x, y, TAIL)
    if u * u + v * v <= 1.0 or in_tail:
        if u * u + v * v > 1.0:
            u, v = tu * 0.9, tv
        b = 0.38 + 0.66 * max(0.0, ellipse_light(u, v))
        b += 0.07 * sin(x * 11 + 2 * sin(y * 9)) * sin(y * 13)
        if y < 0.2:
            b *= 0.6 + 2.0 * y  # shadow where the body meets the water
        return shade(b, "w")
    return None


REFLECT = {"3": "r2", "2": "r1", "1": "r0", "0": "r0"}


def reflected(cell):
    ch, tag = cell
    if tag[0] in "wc":
        return ch, REFLECT[tag[-1]]
    if tag == "beak":
        return ch, "beak_d"
    return ch, "blk"


# ---------------------------------------------------------------------------
# Water
# ---------------------------------------------------------------------------
def water_value(x, y, t, ring_cx):
    w = y - BOTTOM                      # distance into the scene
    phase = (2.4 * w + 0.45 * w * w     # bands get tighter further away
             + 1.4 * sin(x * 0.45 + t * 0.6 + w * 0.3)
             + 0.9 * sin(x * 1.1 - t * 0.9 + w * 0.8)
             + 0.35 * sin(x * 2.7 + t * 1.7 - w))
    patches = 0.5 + 0.5 * sin(x * 0.3 - y * 0.5 + t * 0.15) * sin(x * 0.17 + y * 0.9 - t * 0.1)
    s = sin(phase) * (0.5 + 0.5 * patches)

    # Ripple rings spreading out from the swan's chest.
    dx, dy = x - ring_cx, y * 3.5
    if -3.5 < dx < 3.5 and -1.2 < y < 1.2:
        rho = sqrt(dx * dx + dy * dy)
        for k in range(4):
            rk = ((t * 0.25 + k / 4) % 1.0) * 3.2
            s += 0.9 * exp(-((rho - rk) / 0.08) ** 2) * (1 - rk / 3.2)
    return s


def water_cell(s):
    if s > 0.90:
        return "=", "wa5"
    if s > 0.76:
        return "~", "wa4"
    if s > 0.58:
        return "-", "wa3"
    if s > 0.35:
        return "-", "wa2"
    if s > 0.05:
        return ".", "wa1"
    return " ", None


# ---------------------------------------------------------------------------
# Foreground twigs (fixed in the scene, swaying slightly)
# ---------------------------------------------------------------------------
TWIGS = [  # (base x, base y, angle deg, length, phase)
    (1.30, -2.1, 70, 1.4, 0.0), (1.55, -2.1, 95, 1.1, 1.1), (1.80, -2.1, 60, 1.7, 2.0),
    (2.05, -2.1, 84, 1.9, 0.5), (2.30, -2.1, 112, 1.3, 2.7), (2.55, -2.1, 76, 2.0, 1.6),
    (2.85, -2.1, 64, 1.5, 0.9), (3.10, -2.1, 92, 2.2, 2.2), (3.40, -2.1, 72, 1.6, 0.3),
    (3.70, -2.1, 100, 1.9, 1.4), (4.00, -2.1, 82, 2.3, 2.5), (4.35, -2.1, 118, 1.2, 0.7),
    (-0.75, -2.1, 72, 1.0, 1.9), (-1.30, -2.1, 110, 0.6, 2.3), (-3.40, -2.1, 64, 0.7, 0.4),
]


def twig_segments(t):
    segs = []
    for bx, by, ang, length, ph in TWIGS:
        a = math.radians(ang + 2.0 * sin(t * 0.9 + ph))
        dx, dy = cos(a) * length, sin(a) * length
        segs.append((bx, by, dx, dy, dx * dx + dy * dy, a))
        # a short side branch partway up
        a2 = a + (0.6 if ph > 1.2 else -0.6)
        mx, my = bx + dx * 0.55, by + dy * 0.55
        dx2, dy2 = cos(a2) * length * 0.35, sin(a2) * length * 0.35
        segs.append((mx, my, dx2, dy2, dx2 * dx2 + dy2 * dy2, a2))
    return segs


def sample_twigs(x, y, segs, half_w):
    for ax, ay, dx, dy, l2, ang in segs:
        t = ((x - ax) * dx + (y - ay) * dy) / l2
        if 0 <= t <= 1:
            px, py = x - ax - t * dx, y - ay - t * dy
            if px * px + py * py < half_w * half_w:
                return stroke_char(ang), ("reed2" if t > 0.6 else "reed1")
    return None


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def render(cols, rows, aspect, t):
    P = Pose(t)
    dy_cell = (TOP - BOTTOM) / rows
    dx_cell = dy_cell / aspect
    x_left = VIEW_X - cols / 2 * dx_cell
    ring_cx = P.ox - 2.85
    twigs = twig_segments(t)
    twig_w = max(0.05, dx_cell * 0.55)
    ox, oy = P.ox, P.oy

    grid = []
    for r in range(rows):
        y = TOP - (r + 0.5) * dy_cell
        row = []
        if y < 0:
            wob_row = y * 7 + t * 2.2
            wob_row2 = y * 15 - t * 3.1
            ly_ref = -y - oy
        for c in range(cols):
            x = x_left + (c + 0.5) * dx_cell

            cell = sample_twigs(x, y, twigs, twig_w) if y < 0.3 else None
            if cell is None and y >= 0:
                cell = sample_swan(x - ox, y - oy, P)
            if cell is None:
                s = water_value(x, y, t, ring_cx)
                if y < 0 and ly_ref < 3.8:
                    wob = 0.09 * sin(wob_row + x * 0.5) + 0.04 * sin(wob_row2)
                    hit = sample_swan(x + wob - ox, ly_ref, P)
                    if hit is not None and s < 0.5:
                        cell = reflected(hit)
                if cell is None:
                    cell = water_cell(s)
            row.append(cell)
        grid.append(row)

    # The eye is smaller than a character cell, so place it directly.
    ex, ey = P.eye
    ec = int((ex + ox - x_left) / dx_cell)
    er = int((TOP - (ey + oy)) / dy_cell)
    if 0 <= er < rows and 0 <= ec < cols:
        grid[er][ec] = ("o", "eye")
    return grid


class SwanWindow:
    def __init__(self, root, args):
        self.root, self.args = root, args
        self.start = time.time()

        families = set(tkfont.families())
        family = next((f for f in ("Menlo", "Consolas", "DejaVu Sans Mono", "Courier New") if f in families), "Courier")
        self.font = tkfont.Font(family=family, size=args.font_size, weight="bold")
        self.char_w = self.font.measure("M")
        self.char_h = self.font.metrics("linespace")
        self.aspect = self.char_h / self.char_w

        root.title("ASCII Swan")
        root.configure(bg=BACKGROUND)
        root.geometry(f"{args.width}x{args.height}")
        self.text = tk.Text(root, font=self.font, bg=BACKGROUND, bd=0, highlightthickness=0,
                            padx=0, pady=0, wrap="none", cursor="arrow")
        self.text.pack(fill="both", expand=True)
        for tag, color in COLORS.items():
            self.text.tag_configure(tag, foreground=color)

        root.bind("<Escape>", lambda e: root.destroy())
        root.bind("q", lambda e: root.destroy())
        self.root.after(50, self.tick)

    def tick(self):
        frame_start = time.time()
        w = max(self.text.winfo_width(), 200)
        h = max(self.text.winfo_height(), 120)
        cols, rows = w // self.char_w, h // self.char_h - 1

        grid = render(cols, rows, self.aspect, (frame_start - self.start) * self.args.speed)

        # Merge neighbouring cells of the same color into runs: one insert per frame.
        chunks = []
        for row in grid:
            run, run_tag = [], None
            for ch, tag in row:
                if tag != run_tag and run:
                    chunks += ["".join(run), run_tag or ()]
                    run = []
                run_tag = tag
                run.append(ch)
            run.append("\n")
            chunks += ["".join(run), run_tag or ()]

        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", *chunks)
        self.text.configure(state="disabled")

        elapsed = int((time.time() - frame_start) * 1000)
        self.root.after(max(1, int(1000 / self.args.fps) - elapsed), self.tick)


def main():
    parser = argparse.ArgumentParser(description="Colored ASCII animation of a swan on a pond.")
    parser.add_argument("--font-size", type=int, default=6, help="smaller = more detail but slower (default 8)")
    parser.add_argument("--fps", type=float, default=20, help="target frames per second (default 20)")
    parser.add_argument("--speed", type=float, default=1.0, help="animation speed multiplier (default 1.0)")
    parser.add_argument("--width", type=int, default=1100, help="starting window width in pixels")
    parser.add_argument("--height", type=int, default=720, help="starting window height in pixels")
    args = parser.parse_args()

    root = tk.Tk()
    SwanWindow(root, args)
    root.mainloop()


if __name__ == "__main__":
    main()