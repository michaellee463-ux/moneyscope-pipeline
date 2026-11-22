"""1280x720 thumbnail from spec.json["thumbnail"].

spec["thumbnail"] = {
  "kicker": "THE REAL COST OF BLACK FRIDAY",      # small gold badge
  "left":  {"value": "$1,000", "label": "YOU BUY",  "color": "green", "bar": 1000},
  "right": {"value": "$1,441", "label": "YOU PAY",  "color": "red",   "bar": 1441},
  "footer": "22.36% APR · $35/month"
}
Usage: python thumbnail.py <episode_dir>  ->  <episode_dir>/thumbnail.jpg
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT = str(ROOT / "assets" / "fonts" / "ArchivoBlack-Regular.ttf")
C = {"bg": "#0A1630", "bg2": "#10214A", "grid": "#16295A", "green": "#2BD67B",
     "gold": "#F5B700", "red": "#FF4D4D", "white": "#FFFFFF", "dim": "#9FB0D0", "navy": "#0A1630"}


def fit(draw, text, max_w, start):
    s = start
    while s > 10:
        f = ImageFont.truetype(FONT, s)
        if draw.textlength(text, font=f) <= max_w:
            return f
        s -= 2
    return ImageFont.truetype(FONT, s)


def main(ep):
    ep = Path(ep)
    t = json.loads((ep / "spec.json").read_text())["thumbnail"]
    W, H = 1280, 720
    im = Image.new("RGB", (W, H), C["bg"])
    d = ImageDraw.Draw(im)
    for x in range(0, W, 64):
        d.line([(x, 0), (x, H)], fill=C["grid"], width=2)
    for y in range(0, H, 64):
        d.line([(0, y), (W, y)], fill=C["grid"], width=2)
    d.polygon([(0, 470), (W, 170), (W, H), (0, H)], fill=C["bg2"])

    # kicker badge
    kf = fit(d, t["kicker"], 1100, 46)
    kw = d.textlength(t["kicker"], font=kf)
    d.rectangle([60, 40, 60 + kw + 40, 40 + 74], fill=C["gold"])
    d.text((80, 50), t["kicker"], font=kf, fill=C["navy"])

    # two bars with big numbers
    base_y = 660
    maxb = max(t["left"]["bar"], t["right"]["bar"])
    for side, x0 in ((t["left"], 90), (t["right"], 690)):
        h = int(300 * side["bar"] / maxb)
        d.rectangle([x0, base_y - h, x0 + 500, base_y], fill=C[side["color"]])
        vf = fit(d, side["value"], 500, 150)
        vw = d.textlength(side["value"], font=vf)
        d.text((x0 + 250 - vw / 2, base_y - h - 175), side["value"], font=vf, fill=C[side["color"]],
               stroke_width=6, stroke_fill=C["navy"])
        lf = ImageFont.truetype(FONT, 44)
        lw = d.textlength(side["label"], font=lf)
        d.text((x0 + 250 - lw / 2, base_y - 62), side["label"], font=lf, fill=C["navy"])
    # arrow between
    d.polygon([(600, 360), (650, 395), (600, 430)], fill=C["white"])
    ff = ImageFont.truetype(FONT, 30)
    d.text((90, 672), t.get("footer", ""), font=ff, fill=C["dim"])
    bf = ImageFont.truetype(FONT, 30)
    bw = d.textlength("MONEYSCOPE", font=bf)
    d.text((W - 60 - bw, 672), "MONEYSCOPE", font=bf, fill=C["gold"])
    im.save(ep / "thumbnail.jpg", quality=92)
    print("thumbnail.jpg written")


if __name__ == "__main__":
    main(sys.argv[1])
