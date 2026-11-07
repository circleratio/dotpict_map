"""Convert an outline map SVG (polygons/paths) into a dot-art SVG made of
solid-color circles.

Works with any SVG whose visible shapes are <path> and/or <polygon>
elements, including nested <g transform="..."> groups (matrix / translate /
scale). Tested against:
  - maps/japan-map-full.svg  (Geolonia Japan prefecture map)
  - maps/world.svg           (Simplemaps world map)
  - maps/World_map_(Mercator_projection)_Pacific-centric.svg

Usage:
    python3 generate_dot_map.py --input maps/japan-map-full.svg --step 10 \\
        --color "#888888" --radius-ratio 0.42 --output output/japan-dot.svg

    python3 generate_dot_map.py -i maps/world.svg -s 14 -c "#666666" -r 0.45 -o output/world-dot.svg

Highlighting a region (dots whose centers fall inside the given polygon, in
input SVG coordinates, are drawn with a different color and radius):

    # Japan on World_map_(Mercator_projection)_Pacific-centric.svg
    python3 generate_dot_map.py \\
        -i "maps/World_map_(Mercator_projection)_Pacific-centric.svg" -s 4 \\
        --highlight-polygon "333,226.5 349,226.5 350,242 342,256 322,268 312,284 302,284 306,268 312,258 316,250 322,245 330,238" \\
        --highlight-color "#e60012" --highlight-step 2 --highlight-radius-ratio 0.45 \\
        -o output/world-pacific-dot.svg

When --output is omitted, the result is written to
output/<input-stem>-dot.svg. Missing output directories are created.
"""
import argparse
import math
import os
import re
import xml.etree.ElementTree as ET


NUM_RE = r'-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?'
PATH_TOKEN_RE = re.compile(r'[MmLlHhVvCcSsQqTtAaZz]|' + NUM_RE)
NUM_ONLY_RE = re.compile(NUM_RE)

# number of numeric args consumed per curve command (endpoint-only
# approximation; control points are not needed for a fill/outline test)
CURVE_ARGS = {'C': 6, 'S': 4, 'Q': 4, 'T': 2, 'A': 7}


def local_tag(elem):
    return elem.tag.split('}')[-1]


def parse_transform(s):
    """Parse a transform attribute into a single composed matrix (a,b,c,d,e,f)."""
    m = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    for name, args in re.findall(r'(\w+)\s*\(([^)]*)\)', s or ''):
        nums = [float(v) for v in re.findall(NUM_RE, args)]
        if name == 'matrix' and len(nums) == 6:
            t = tuple(nums)
        elif name == 'translate':
            tx = nums[0] if nums else 0.0
            ty = nums[1] if len(nums) > 1 else 0.0
            t = (1.0, 0.0, 0.0, 1.0, tx, ty)
        elif name == 'scale':
            sx = nums[0] if nums else 1.0
            sy = nums[1] if len(nums) > 1 else sx
            t = (sx, 0.0, 0.0, sy, 0.0, 0.0)
        else:
            continue
        m = compose(m, t)
    return m


def compose(m1, m2):
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def apply_matrix(m, x, y):
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


def parse_path_d(d):
    """Return a list of subpaths, each a list of (x, y) points (in local coords)."""
    tokens = PATH_TOKEN_RE.findall(d)
    i = 0
    cmd = None
    cx = cy = 0.0
    start_x = start_y = 0.0
    cur = []
    subpaths = []

    def read():
        nonlocal i
        v = float(tokens[i])
        i += 1
        return v

    while i < len(tokens):
        t = tokens[i]
        if re.match(r'^[A-Za-z]$', t):
            cmd = t
            i += 1
            if cmd in ('Z', 'z'):
                if cur:
                    subpaths.append(cur)
                cur = []
                cx, cy = start_x, start_y
                continue

        if cmd in ('M', 'm'):
            x, y = read(), read()
            if cmd == 'm':
                x += cx
                y += cy
            cx, cy = x, y
            start_x, start_y = x, y
            if cur:
                subpaths.append(cur)
            cur = [(cx, cy)]
            cmd = 'L' if cmd == 'M' else 'l'  # implicit repeats are linetos
        elif cmd in ('L', 'l'):
            x, y = read(), read()
            if cmd == 'l':
                x += cx
                y += cy
            cx, cy = x, y
            cur.append((cx, cy))
        elif cmd in ('H', 'h'):
            x = read()
            if cmd == 'h':
                x += cx
            cx = x
            cur.append((cx, cy))
        elif cmd in ('V', 'v'):
            y = read()
            if cmd == 'v':
                y += cy
            cy = y
            cur.append((cx, cy))
        elif cmd and cmd.upper() in CURVE_ARGS:
            n = CURVE_ARGS[cmd.upper()]
            vals = [read() for _ in range(n)]
            x, y = vals[-2], vals[-1]
            if cmd.islower():
                x += cx
                y += cy
            cx, cy = x, y
            cur.append((cx, cy))
        else:
            # unknown command; skip one number to avoid an infinite loop
            i += 1

    if cur:
        subpaths.append(cur)
    return subpaths


def load_polygons(src):
    tree = ET.parse(src)
    root = tree.getroot()
    identity = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    polygons = []  # list of list[(x, y)]

    def walk(elem, matrix):
        tag = local_tag(elem)
        transform = elem.get('transform')
        m = compose(matrix, parse_transform(transform)) if transform else matrix

        if tag == 'polygon':
            pts_attr = elem.get('points', '')
            nums = [float(v) for v in NUM_ONLY_RE.findall(pts_attr)]
            pts = list(zip(nums[0::2], nums[1::2]))
            if len(pts) >= 3:
                polygons.append([apply_matrix(m, x, y) for x, y in pts])
        elif tag == 'path':
            d = elem.get('d', '')
            for sub in parse_path_d(d):
                if len(sub) >= 3:
                    polygons.append([apply_matrix(m, x, y) for x, y in sub])

        for child in elem:
            walk(child, m)

    walk(root, identity)
    return polygons


def point_in_poly(x, y, poly):
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            x_int = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_int:
                inside = not inside
        j = i
    return inside


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-i', '--input', default='maps/japan-map-full.svg',
                    help='input SVG file (default: maps/japan-map-full.svg)')
    ap.add_argument('-s', '--step', type=float, default=10.0, help='dot pitch in local SVG units (default: 10)')
    ap.add_argument('-c', '--color', default='#888888', help='dot color (default: #888888)')
    ap.add_argument('-r', '--radius-ratio', type=float, default=0.42, help='dot radius as a ratio of step (default: 0.42)')
    ap.add_argument('--highlight-polygon', default=None,
                    help='polygon "x,y x,y ..." in input SVG coordinates; dots inside it are highlighted')
    ap.add_argument('--highlight-color', default='#e60012', help='highlight dot color (default: #e60012)')
    ap.add_argument('--highlight-step', type=float, default=None,
                    help='dot pitch inside the highlight polygon (default: same as --step)')
    ap.add_argument('--highlight-radius-ratio', type=float, default=0.6,
                    help='highlight dot radius as a ratio of highlight step (default: 0.6)')
    ap.add_argument('-o', '--output', default=None, help='output SVG file (default: "output/<input-stem>-dot.svg")')
    args = ap.parse_args()

    if args.output:
        out_path = args.output
    else:
        stem = re.sub(r'\.svg$', '', os.path.basename(args.input), flags=re.I)
        out_path = os.path.join('output', stem + '-dot.svg')

    highlight = None
    if args.highlight_polygon:
        nums = [float(v) for v in NUM_ONLY_RE.findall(args.highlight_polygon)]
        highlight = list(zip(nums[0::2], nums[1::2]))
        if len(highlight) < 3:
            raise SystemExit('--highlight-polygon needs at least 3 points')

    polygons = load_polygons(args.input)
    if not polygons:
        raise SystemExit(f'No polygons/paths found in {args.input}')

    poly_data = []
    all_x, all_y = [], []
    for pts in polygons:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        poly_data.append(((min(xs), min(ys), max(xs), max(ys)), pts))
        all_x.extend(xs)
        all_y.extend(ys)

    minx, maxx = min(all_x), max(all_x)
    miny, maxy = min(all_y), max(all_y)

    def is_land(x, y):
        for bbox, pts in poly_data:
            bx0, by0, bx1, by1 = bbox
            if x < bx0 or x > bx1 or y < by0 or y > by1:
                continue
            if point_in_poly(x, y, pts):
                return True
        return False

    step = args.step
    pad = step
    x0, y0 = minx - pad, miny - pad
    x1, y1 = maxx + pad, maxy + pad
    width, height = x1 - x0, y1 - y0

    cols = int(math.floor(width / step)) + 1
    rows = int(math.floor(height / step)) + 1
    radius = step * args.radius_ratio
    hl_step = args.highlight_step or step
    hl_radius = hl_step * args.highlight_radius_ratio

    circles = []
    for r in range(rows):
        y = y0 + r * step
        for c in range(cols):
            x = x0 + c * step
            if highlight and point_in_poly(x, y, highlight):
                continue
            if is_land(x, y):
                circles.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}"/>')

    # the highlight region gets its own grid, anchored to the base grid origin
    # so that it lines up with the base dots when hl_step divides step
    hl_circles = []
    if highlight:
        hx0 = min(p[0] for p in highlight)
        hy0 = min(p[1] for p in highlight)
        hx1 = max(p[0] for p in highlight)
        hy1 = max(p[1] for p in highlight)
        c0 = int(math.ceil((hx0 - x0) / hl_step))
        c1 = int(math.floor((hx1 - x0) / hl_step))
        r0 = int(math.ceil((hy0 - y0) / hl_step))
        r1 = int(math.floor((hy1 - y0) / hl_step))
        for r in range(r0, r1 + 1):
            y = y0 + r * hl_step
            for c in range(c0, c1 + 1):
                x = x0 + c * hl_step
                if point_in_poly(x, y, highlight) and is_land(x, y):
                    hl_circles.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{hl_radius:.2f}"/>')

    # highlighted dots go last so they are drawn on top of the base dots
    hl_group = ''
    if hl_circles:
        hl_group = (
            f'  <g fill="{args.highlight_color}">\n'
            + "\n".join(f"    {c}" for c in hl_circles)
            + "\n  </g>\n"
        )

    svg = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.2f} {y0:.2f} {width:.2f} {height:.2f}">\n'
        '  <title>Dot art map</title>\n'
        f'  <g fill="{args.color}">\n'
        + "\n".join(f"    {c}" for c in circles)
        + "\n  </g>\n"
        + hl_group
        + "</svg>\n"
    )

    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(svg)

    print(f'dots={len(circles)} highlighted={len(hl_circles)} cols={cols} rows={rows} step={step} -> {out_path}')


if __name__ == '__main__':
    main()
