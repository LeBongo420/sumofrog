"""Composite a real 相撲 (sumo) red seal onto logo A. Writes art/logo_v2.jpg and PNG sizes."""
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

ART = Path(__file__).resolve().parent.parent / "art"
FONT = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"
RED = (184, 44, 32)
random.seed(1185)  # fixed so the seal is reproducible

def seal(w, h, s=4):
    W, H = w * s, h * s
    mask = Image.new("L", (W, H), 0)  # 255 = red ink
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle((0, 0, W - 1, H - 1), radius=6 * s, fill=255)
    # JP face of the Noto Serif CJK collection
    font = None
    for idx in range(10):
        f = ImageFont.truetype(FONT, int(H * 0.40), index=idx)
        if "JP" in " ".join(f.getname()):
            font = f; break
    font = font or ImageFont.truetype(FONT, int(H * 0.40))
    for i, ch in enumerate("相撲"):  # read top to bottom
        cy = H * (0.28 + 0.46 * i)
        d.text((W / 2, cy), ch, font=font, fill=0, anchor="mm")
    # worn stamp: speckle holes in the ink and a slightly ragged edge
    noise = Image.effect_noise((W, H), 70).point(lambda v: 0 if v > 205 else 255)
    noise = noise.filter(ImageFilter.GaussianBlur(1.2)).point(lambda v: 255 if v > 110 else 0)
    mask = ImageChops.multiply(mask, noise)
    edge = Image.new("L", (W, H), 255)
    ed = ImageDraw.Draw(edge)
    for _ in range(140):
        x, y = random.randrange(W), random.choice([random.randrange(3 * s), H - 1 - random.randrange(3 * s)])
        if random.random() < 0.5:
            x, y = random.choice([random.randrange(3 * s), W - 1 - random.randrange(3 * s)]), random.randrange(H)
        r = random.randint(1, 3) * s // 2
        ed.ellipse((x - r, y - r, x + r, y + r), fill=0)
    mask = ImageChops.multiply(mask, edge).filter(ImageFilter.GaussianBlur(0.8 * s / 2))
    return mask.resize((w, h), Image.LANCZOS)

def main():
    logo = Image.open(ART / "logo.jpg").convert("RGB")
    # 1. cover the old made-up seal (748-830 x 761-860) with paper sampled just left of it
    patch = logo.crop((780, 560, 876, 672))  # clean paper above the seal
    logo.paste(patch, (741, 754))
    # 2. stamp the new seal, multiplied so the paper texture shows through the ink
    x, y, w, h = 744, 758, 88, 106
    m = seal(w, h)
    region = logo.crop((x, y, x + w, y + h))
    ink = ImageChops.multiply(region, Image.new("RGB", (w, h), RED).point(lambda v: min(255, int(v * 1.25))))
    logo.paste(Image.composite(ink, region, m.point(lambda v: int(v * 0.95))), (x, y))
    logo.save(ART / "logo_v2.jpg", quality=95)
    for n in (512, 256, 128, 64):
        logo.resize((n, n), Image.LANCZOS).save(ART / f"logo_v2_{n}.png")
    logo.crop((700, 720, 880, 900)).resize((540, 540), Image.LANCZOS).save("/tmp/seal_v2_zoom.png")

if __name__ == "__main__":
    main()
