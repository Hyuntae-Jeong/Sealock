"""
Generate macOS (.icns) and Windows (.ico) app icons from icon_for_mac.png.

- Mac : square macOS-style "squircle" with WHITE background, mascot centered.
- Win : background removed (누끼), TRANSPARENT background, multi-size .ico.

Background removal keeps the whole connected subject (sea lion + rock + magnifier)
and strips the white backdrop AND its soft grey drop-shadow, while preserving
interior light areas (eyes, magnifier lens) via border-connected flood fill.
"""
import io
import struct
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageChops

HERE = __import__("os").path.dirname(__import__("os").path.abspath(__file__))
SRC = HERE + "/icon_for_mac.png"


# ---------------------------------------------------------------- cutout ----
def make_cutout():
    src = Image.open(SRC).convert("RGBA")
    # flatten onto white so we work with the real RGB the artist intended
    flat = Image.alpha_composite(Image.new("RGBA", src.size, (255, 255, 255, 255)), src).convert("RGB")
    arr = np.array(flat)
    H, W = arr.shape[:2]

    mn = arr.min(axis=2).astype(int)
    mx = arr.max(axis=2).astype(int)
    # background-like = bright AND near-neutral (white bg + grey shadow), not the
    # brown seal / teal rock / coloured details.
    cand = (mn >= 180) & ((mx - mn) <= 40)

    # keep only background CONNECTED to the image border (so enclosed light areas
    # such as the eyes / lens highlights survive). Pad a white frame, flood from a
    # corner across the candidate region.
    cu8 = (cand.astype("uint8") * 255)
    m = Image.frombytes("L", (W, H), cu8.tobytes())
    P = Image.new("L", (W + 2, H + 2), 255)
    P.paste(m, (1, 1))
    ImageDraw.floodfill(P, (0, 0), 128, thresh=10)
    flooded = np.array(P)[1:-1, 1:-1]
    bg = flooded == 128

    alpha = np.where(bg, 0, 255).astype("uint8")
    A = Image.frombytes("L", (W, H), alpha.tobytes())
    # tiny feather for smooth edges (no erosion -> keeps thin whiskers)
    A = A.filter(ImageFilter.GaussianBlur(0.5))

    cut = np.dstack([arr, np.array(A)]).astype("uint8")
    cutout = Image.fromarray(cut, "RGBA")

    # trim to subject bbox
    am = np.array(A)
    ys, xs = np.where(am > 16)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    subject = cutout.crop((int(x0), int(y0), int(x1), int(y1)))

    kept = int((am > 16).sum())
    print(f"cutout: source {W}x{H}, subject bbox {subject.size}, "
          f"removed {100*(1-kept/am.size):.1f}% as background")
    return subject


# ----------------------------------------------------------------- squircle -
def squircle_mask(canvas, body, n=5.0, ss=4):
    """Apple-like superellipse mask, anti-aliased via supersampling."""
    S = canvas * ss
    a = (body * ss) / 2.0
    c = (S - 1) / 2.0
    yy, xx = np.mgrid[0:S, 0:S]
    v = (np.abs(xx - c) / a) ** n + (np.abs(yy - c) / a) ** n
    M = Image.frombytes("L", (S, S), ((v <= 1.0).astype("uint8") * 255).tobytes())
    return M.resize((canvas, canvas), Image.LANCZOS)


def make_mac(subject):
    CAN, BODY = 1024, 824
    mask = squircle_mask(CAN, BODY, n=5.0, ss=4)

    img = Image.new("RGBA", (CAN, CAN), (0, 0, 0, 0))

    # soft floating drop-shadow (macOS look)
    shadow = Image.new("RGBA", (CAN, CAN), (0, 0, 0, 0))
    shadow.paste(Image.new("RGBA", (CAN, CAN), (0, 0, 0, 55)), (0, 0), mask)
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    shadow = ImageChops.offset(shadow, 0, 12)
    img = Image.alpha_composite(img, shadow)

    # white body
    body = Image.new("RGBA", (CAN, CAN), (0, 0, 0, 0))
    body.paste(Image.new("RGBA", (CAN, CAN), (255, 255, 255, 255)), (0, 0), mask)
    img = Image.alpha_composite(img, body)

    # mascot centered within safe area
    content = int(BODY * 0.84)
    sub = subject.copy()
    sub.thumbnail((content, content), Image.LANCZOS)
    img.alpha_composite(sub, ((CAN - sub.size[0]) // 2, (CAN - sub.size[1]) // 2))

    img.save(HERE + "/icon_mac_1024.png")
    save_icns(img, HERE + "/icon_mac.icns")
    print(f"mac : icon_mac.icns + icon_mac_1024.png (squircle {BODY}px on {CAN}px)")
    return img


# -------------------------------------------------------- container writers -
def save_icns(img, path):
    specs = [(b"icp4", 16), (b"icp5", 32), (b"icp6", 64),
             (b"ic07", 128), (b"ic08", 256), (b"ic09", 512), (b"ic10", 1024),
             (b"ic11", 32), (b"ic12", 64), (b"ic13", 256), (b"ic14", 512)]
    chunks = b""
    for ostype, sz in specs:
        b = io.BytesIO()
        img.resize((sz, sz), Image.LANCZOS).save(b, format="PNG")
        png = b.getvalue()
        chunks += ostype + struct.pack(">I", len(png) + 8) + png
    with open(path, "wb") as f:
        f.write(b"icns" + struct.pack(">I", 8 + len(chunks)) + chunks)


def save_ico(images, path):
    images = sorted(images, key=lambda im: im.size[0])
    pngs = [(_png(im), im.size[0]) for im in images]
    n = len(pngs)
    hdr = struct.pack("<HHH", 0, 1, n)
    off = 6 + 16 * n
    ent = b""
    data = b""
    for png, s in pngs:
        ent += struct.pack("<BBBBHHII", 0 if s >= 256 else s, 0 if s >= 256 else s,
                            0, 0, 1, 32, len(png), off)
        off += len(png)
        data += png
    with open(path, "wb") as f:
        f.write(hdr + ent + data)


def _png(im):
    b = io.BytesIO()
    im.save(b, format="PNG")
    return b.getvalue()


def make_win(subject):
    sw, sh = subject.size
    side = max(sw, sh)
    pad = int(side * 0.04)
    box = side + 2 * pad
    canvas = Image.new("RGBA", (box, box), (0, 0, 0, 0))
    canvas.alpha_composite(subject, ((box - sw) // 2, (box - sh) // 2))

    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [canvas.resize((s, s), Image.LANCZOS) for s in sizes]
    save_ico(imgs, HERE + "/icon_win.ico")
    canvas.resize((256, 256), Image.LANCZOS).save(HERE + "/icon_win_256.png")
    subject.save(HERE + "/seal_cutout.png")
    print(f"win : icon_win.ico ({','.join(map(str, sizes))}) + "
          f"icon_win_256.png + seal_cutout.png")


if __name__ == "__main__":
    subject = make_cutout()
    make_mac(subject)
    make_win(subject)
    print("done.")
