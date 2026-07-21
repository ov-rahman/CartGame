#!/usr/bin/env python3
"""
style-forge — инструмент единого стиля для карточного роглайка.

Идея: нейросеть (ChatGPT) рисует ТОЛЬКО субъект на прозрачном фоне.
Всё остальное — рамка, бумага, палитра, типографика — детерминированно
собирается здесь. Поэтому стиль не может "уплыть".

Команды:
  python3 forge.py prompts            — сгенерить промпты для ChatGPT (в prompts/)
  python3 forge.py build              — собрать готовые карты (в output/)
  python3 forge.py build --card prick — собрать одну карту

Для сборки карты кладёшь картинку из ChatGPT в inbox/<id>.png .
Если файла нет — рисуется плейсхолдер, чтобы видеть будущую карту.
"""
import argparse
import json
import os
import zlib
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))


# ────────────────────────────────────────────────────────── утилиты

def load_json(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return json.load(f)


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def font(cfg, role, size):
    return ImageFont.truetype(os.path.join(HERE, cfg["fonts"][role]), size)


def fit_font(cfg, role, text, max_w, start, min_size=14):
    """Подбирает размер шрифта, чтобы текст влез в max_w."""
    size = start
    while size > min_size:
        f = font(cfg, role, size)
        if f.getlength(text) <= max_w:
            return f
        size -= 2
    return font(cfg, role, min_size)


def wrap(draw, text, f, max_w):
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=f) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


# ────────────────────────────────────────────────────────── стиль

def apply_grade(img, cfg):
    """Приводит субъект к общей тональности игры (тёплый сепия + зерно)."""
    g = cfg["grade"]
    arr = np.asarray(img.convert("RGBA")).astype(np.float32)
    rgb, alpha = arr[..., :3].copy(), arr[..., 3]

    lum = (rgb * np.array([0.299, 0.587, 0.114])).sum(2, keepdims=True)
    rgb = lum + (rgb - lum) * g["saturation"]          # десатурация
    rgb *= np.array(g["warm"])                          # тёплый баланс
    rgb = (rgb - 128) * g["contrast"] + 128             # контраст

    t = np.clip(lum / 255.0, 0, 1)                      # тональная сшивка
    shadow = np.array(hex2rgb(g["sepia_shadow"]), np.float32)
    highl = np.array(hex2rgb(g["paper_highlight"]), np.float32)
    tone = shadow * (1 - t) + highl * t
    rgb = rgb * (1 - g["tone_amount"]) + tone * g["tone_amount"]

    if g["grain"]:
        rgb += np.random.normal(0, g["grain"], rgb.shape[:2])[..., None]

    rgb = np.clip(rgb, 0, 255)
    out = np.dstack([rgb, alpha]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def make_paper(w, h, cfg):
    """Процедурная состаренная бумага: тон + волокна + виньетка."""
    c = cfg["card"]
    base = np.array(hex2rgb(c["paper_base"]), np.float32)
    img = np.ones((h, w, 3), np.float32) * base

    img += np.random.normal(0, 6, (h, w, 1))            # мелкое зерно
    low = np.random.normal(0, 1, (max(2, h // 8), max(2, w // 8), 1)).astype(np.float32)
    blot = Image.fromarray(
        ((low[:, :, 0] - low.min()) / (np.ptp(low) + 1e-6) * 255).astype("uint8")
    ).resize((w, h))
    img += (np.asarray(blot).astype(np.float32)[..., None] - 128) / 128 * 9  # пятна

    xx = np.linspace(-1, 1, w)[None, :, None]
    yy = np.linspace(-1, 1, h)[:, None, None]
    r = np.sqrt(xx ** 2 + yy ** 2)
    img *= np.clip(1 - (r - 0.7) * 0.35, 0.82, 1)       # виньетка

    img = np.clip(img, 0, 255).astype(np.uint8)
    return Image.fromarray(img, "RGB").convert("RGBA")


def fit_contain(img, box):
    bw, bh = box
    iw, ih = img.size
    s = min(bw / iw, bh / ih)
    return img.resize((max(1, int(iw * s)), max(1, int(ih * s))), Image.LANCZOS)


def tfont(cfg, px):
    return ImageFont.truetype(os.path.join(HERE, cfg["font_main"]), int(px))


def fit_tfont(cfg, text, max_w, start):
    size = int(start)
    while size > 12:
        f = tfont(cfg, size)
        if f.getlength(text) <= max_w:
            return f
        size -= 2
    return tfont(cfg, 12)


def ctext(d, cx, y, s, f, fill, sw=0):
    """Текст по центру относительно cx, с утолщением через обводку (sw)."""
    d.text((cx - d.textlength(s, font=f) / 2, y), s, font=f, fill=fill, stroke_width=sw, stroke_fill=fill)


def autocrop_alpha(img, pad=2):
    a = np.asarray(img.convert("RGBA"))[..., 3]
    ys, xs = np.where(a > 12)
    return img.crop((max(0, xs.min() - pad), max(0, ys.min() - pad), xs.max() + pad, ys.max() + pad))


def fit_width(img, w):
    return img.resize((int(w), int(img.height * w / img.width)), Image.LANCZOS)


# ────────────────────────────────────────────────────────── износ

def card_seed(card):
    """Стабильный сид на карту → каждая портится по-своему, но воспроизводимо."""
    return zlib.crc32(card["id"].encode()) & 0xFFFFFFFF


def rounded_mask(w, h, r):
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    return m


def fray_edges(mask, strength):
    """Отгрызает случайные кусочки по краю маски — рваная бумага."""
    w, h = mask.size
    m = np.asarray(mask).astype(np.float32) / 255.0
    blur = np.asarray(mask.filter(ImageFilter.GaussianBlur(8))).astype(np.float32) / 255.0
    band = (blur > 0.03) & (blur < 0.97)
    small = np.random.rand(max(2, h // 4), max(2, w // 4))
    noise = np.asarray(Image.fromarray((small * 255).astype("uint8")).resize((w, h))).astype(np.float32) / 255.0
    m[band & (noise < 0.5 * strength)] = 0.0
    soft = Image.fromarray((m * 255).astype("uint8")).filter(ImageFilter.GaussianBlur(0.6))
    return np.asarray(soft).astype(np.float32) / 255.0


def distress(img, cfg):
    """Пятна, разводы, царапины, тёмные потёртые края, рваный контур."""
    w = cfg["wear"]
    W, H = img.size

    # пятна и разводы — на мягком слое
    soft = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(soft)
    sc = hex2rgb(w["spot_color"])
    for _ in range(w["spots"]):
        r = np.random.randint(3, 12)
        x, y = np.random.randint(0, W), np.random.randint(0, H)
        sd.ellipse([x - r, y - r, x + r, y + r], fill=sc + (int(np.random.randint(18, 50)),))
    st = hex2rgb(w["stain_color"])
    for _ in range(w["stains"]):
        R = np.random.randint(70, 140)
        x = np.random.randint(0, W // 3) if np.random.rand() < 0.5 else np.random.randint(2 * W // 3, W)
        y = np.random.randint(0, H // 3) if np.random.rand() < 0.5 else np.random.randint(2 * H // 3, H)
        sd.ellipse([x - R, y - R, x + R, y + R], fill=st + (int(np.random.randint(12, 26)),))
    img = Image.alpha_composite(img, soft.filter(ImageFilter.GaussianBlur(3)))

    # царапины — тонкие резкие линии
    scr = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cd = ImageDraw.Draw(scr)
    for _ in range(w["scratches"]):
        x1, y1 = np.random.randint(0, W), np.random.randint(0, H)
        x2, y2 = x1 + np.random.randint(-130, 130), y1 + np.random.randint(-45, 45)
        a = int(np.random.randint(22, 46))
        col = (255, 250, 235, a) if np.random.rand() < 0.5 else (28, 20, 12, a)
        cd.line([x1, y1, x2, y2], fill=col, width=1)
    img = Image.alpha_composite(img, scr)

    # тёмные потёртые края + рваный контур
    arr = np.asarray(img).astype(np.float32)
    ring = 1.0 - np.asarray(rounded_mask(W, H, w["corner_radius"]).filter(
        ImageFilter.GaussianBlur(15))).astype(np.float32) / 255.0
    arr[..., :3] *= (1 - w["edge_darken"] * ring[..., None])
    arr[..., 3] *= fray_edges(rounded_mask(W, H, w["corner_radius"]), w["fray"])
    return Image.fromarray(np.clip(arr, 0, 255).astype("uint8"), "RGBA")


# ────────────────────────────────────────────────────────── ценник (магазин)

def draw_price_plate(base, cx, top, price, cfg):
    """Тёмный ценник с монетой под картой — как на скрине магазина."""
    d = ImageDraw.Draw(base, "RGBA")
    pw, ph = 236, 88
    x0, y0 = cx - pw // 2, top
    edge = (18, 12, 7)
    d.rounded_rectangle([x0, y0, x0 + pw, y0 + ph], radius=18,
                        fill=hex2rgb(cfg["shop"]["plate_color"]) + (245,), outline=edge, width=4)
    cy = y0 + ph // 2
    cr = 27
    coin_x = x0 + 52
    d.ellipse([coin_x - cr, cy - cr, coin_x + cr, cy + cr], fill=hex2rgb(cfg["coin_color"]), outline=edge, width=4)
    d.ellipse([coin_x - cr + 8, cy - cr + 8, coin_x + cr - 8, cy + cr - 8], outline=edge, width=2)
    f = tfont(cfg, 48)
    s = str(price)
    asc, desc = f.getmetrics()
    d.text((coin_x + cr + 18, cy - (asc + desc) / 2), s, font=f, fill=(240, 224, 190), stroke_width=1, stroke_fill=(240, 224, 190))


# ────────────────────────────────────────────────────────── плейсхолдер

def placeholder_subject(card, cfg, size=760):
    """Рисуется, если реальной картинки из ChatGPT ещё нет."""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    col = hex2rgb(cfg["types"][card["type"]]["banner"])
    cx = cy = size // 2

    d.ellipse([cx - 250, cy - 250, cx + 250, cy + 250], fill=col + (70,),
              outline=col + (180,), width=6)

    icon = {"attack": "sword", "skill": "shield", "power": "star", "item": "potion"}[card["type"]]
    ink = col + (230,)
    if icon == "sword":
        d.polygon([(cx, cy - 190), (cx + 26, cy + 120), (cx - 26, cy + 120)], fill=ink)
        d.rectangle([cx - 70, cy + 120, cx + 70, cy + 150], fill=ink)
    elif icon == "shield":
        d.polygon([(cx - 150, cy - 150), (cx + 150, cy - 150),
                   (cx + 150, cy + 40), (cx, cy + 190), (cx - 150, cy + 40)], fill=ink)
    elif icon == "star":
        pts = []
        for k in range(10):
            ang = -np.pi / 2 + k * np.pi / 5
            rad = 190 if k % 2 == 0 else 80
            pts.append((cx + rad * np.cos(ang), cy + rad * np.sin(ang)))
        d.polygon(pts, fill=ink)
    else:  # potion
        d.ellipse([cx - 120, cy - 60, cx + 120, cy + 170], fill=ink)
        d.rectangle([cx - 45, cy - 190, cx + 45, cy - 40], fill=ink)

    f = font(cfg, "title", 38)
    for i, line in enumerate(["сюда встанет", "арт из ChatGPT"]):
        w = d.textlength(line, font=f)
        d.text((cx - w / 2, size - 150 + i * 46), line, font=f, fill=(43, 32, 24, 210))
    return im


# ────────────────────────────────────────────────────────── бэйджи

def draw_badge(base, x, y, size, number, color, cfg):
    """Квадратный бейдж стоимости в углу карты — как на референс-скринах."""
    d = ImageDraw.Draw(base, "RGBA")
    ink = hex2rgb(cfg["card"]["ink"])
    col = tuple(int(c * 0.82) for c in color)
    d.rounded_rectangle([x, y, x + size, y + size], radius=16, fill=col, outline=ink, width=5)
    d.rounded_rectangle([x + 7, y + 7, x + size - 7, y + size - 7], radius=10,
                        outline=(255, 255, 255, 55), width=2)
    f = font(cfg, "number", int(size * 0.62))
    s = str(number)
    tw = f.getlength(s)
    asc, desc = f.getmetrics()
    d.text((x + size / 2 - tw / 2, y + size / 2 - (asc + desc) / 2), s, font=f, fill=(244, 230, 200))


# ────────────────────────────────────────────────────────── карта

def template_card(card, subject, cfg):
    """Карта на основе готового PNG-шаблона (прозрачный фон): вставляем арт,
    вписываем стоимость/название/описание. Свою линию не рисуем —
    ориентируемся на слабую линию, уже нарисованную на шаблоне."""
    t = cfg["template"]
    base = fit_width(autocrop_alpha(Image.open(os.path.join(HERE, t["image"])).convert("RGBA")), t["target_width"])
    W, H = base.size
    img = base.copy()
    d = ImageDraw.Draw(img)
    cx = int(W * t["center_x"])
    ink, cream, sw = hex2rgb(t["ink"]), hex2rgb(t["cream"]), t["stroke"]

    # арт по центру, над линией
    a = t["art_box"]
    ax0, ay0, ax1, ay1 = int(W * a[0]), int(H * a[1]), int(W * a[2]), int(H * a[3])
    subj = autocrop_alpha(subject.convert("RGBA"))
    if t.get("grade_subject"):
        subj = apply_grade(subj, cfg)
    subj = fit_contain(subj, (ax1 - ax0, ay1 - ay0))
    img.alpha_composite(subj, (cx - subj.width // 2, ay0 + (ay1 - ay0 - subj.height) // 2))

    # стоимость в бейдж (у предметов энергии нет)
    if card["type"] != "item":
        bf = tfont(cfg, W * t["badge_size"])
        ba, bd = bf.getmetrics()
        ctext(d, int(W * t["badge_center"][0]), int(H * t["badge_center"][1]) - (ba + bd) / 2,
              str(card["cost"]), bf, cream, sw["badge"])

    # название (над штатной линией)
    tf = fit_tfont(cfg, card["name"], W * 0.8, W * t["name_size"])
    ta, td = tf.getmetrics()
    ctext(d, cx, int(H * t["name_y"]) - (ta + td) / 2, card["name"], tf, ink, sw["name"])

    # описание (под штатной линией)
    df = tfont(cfg, W * t["desc_size"])
    ty = int(H * t["desc_y"])
    for ln in wrap(d, card["text"], df, W * 0.74):
        ctext(d, cx, ty, ln, df, ink, sw["desc"])
        ty += int(W * t["line_step"])
    return img


def make_card(card, subject, cfg):
    if cfg.get("template", {}).get("enabled"):
        return template_card(card, subject, cfg)
    np.random.seed(card_seed(card))          # каждая карта портится по-своему
    W, H = cfg["card"]["width"], cfg["card"]["height"]
    ink = hex2rgb(cfg["card"]["ink"])
    ink_soft = hex2rgb(cfg["card"]["ink_soft"])
    tstyle = cfg["types"][card["type"]]

    img = make_paper(W, H, cfg)
    d = ImageDraw.Draw(img)

    # рамка
    m = 18
    d.rounded_rectangle([m, m, W - m, H - m], radius=34, outline=ink, width=6)
    d.rounded_rectangle([m + 11, m + 11, W - m - 11, H - m - 11], radius=26, outline=ink_soft, width=2)

    # арт "плавает" на бумаге (без рамки-окна), с едва заметной тёплой подложкой
    ax0, ay0, ax1, ay1 = 60, 118, W - 60, 500
    acx, acy = (ax0 + ax1) // 2, (ay0 + ay1) // 2
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([ax0 + 20, ay0 + 30, ax1 - 20, ay1],
                                 fill=hex2rgb(cfg["card"]["paper_dark"]) + (75,))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(20)))

    subj = apply_grade(subject, cfg)
    subj = fit_contain(subj, (ax1 - ax0, ay1 - ay0))
    img.paste(subj, (acx - subj.width // 2, acy - subj.height // 2), subj)
    d = ImageDraw.Draw(img)

    # название — без баннера, крупный текст + орнаментная линейка (как на скринах)
    name_y = 552
    tf = fit_font(cfg, "title", card["name"], W - 150, 50)
    tw = tf.getlength(card["name"])
    asc, desc = tf.getmetrics()
    d.text(((W - tw) / 2, name_y - (asc + desc) / 2), card["name"], font=tf, fill=ink)
    ry = name_y + 40
    d.line([130, ry, W - 130, ry], fill=ink_soft, width=2)
    for dx in (130, W - 130):
        d.polygon([(dx, ry - 6), (dx + 6, ry), (dx, ry + 6), (dx - 6, ry)], fill=ink_soft)

    # описание
    bf = font(cfg, "body", 30)
    lines = wrap(d, card["text"], bf, W - 140)
    ty = ry + 26
    for line in lines:
        lw = d.textlength(line, font=bf)
        d.text(((W - lw) / 2, ty), line, font=bf, fill=ink)
        ty += 40

    # стоимость — квадратный бейдж в углу (у предметов энергии нет)
    if card["type"] != "item":
        draw_badge(img, m + 4, m + 4, 82, card["cost"], hex2rgb(tstyle["banner"]), cfg)

    # лёгкий сдвиг тона на карту — чтобы бумага не была одинаковой у всех
    jit = cfg["wear"]["tone_jitter"]
    arr = np.asarray(img).astype(np.float32)
    arr[..., :3] += np.random.uniform(-jit, jit, 3)
    img = Image.fromarray(np.clip(arr, 0, 255).astype("uint8"), "RGBA")

    return distress(img, cfg)


# ────────────────────────────────────────────────────────── команды

def build_prompt(card, cfg):
    sb = cfg["style_bible"]
    return (
        f"{card['art']}. "
        f"{sb['prompt_suffix']}. "
        f"{sb['framing']} "
        f"Avoid: {sb['negative']}."
    )


def cmd_prompts(cfg, cat, args):
    os.makedirs(os.path.join(HERE, "prompts"), exist_ok=True)
    combined = ["# Промпты для ChatGPT\n",
                "Открой ОДИН чат в ChatGPT и генери все ассеты в нём — так стиль держится лучше.",
                "Проси PNG с прозрачным фоном. Скачанный файл клади в `inbox/<id>.png`.\n"]
    for card in cat["cards"]:
        p = build_prompt(card, cfg)
        with open(os.path.join(HERE, "prompts", f"{card['id']}.txt"), "w", encoding="utf-8") as f:
            f.write(p + "\n")
        combined.append(f"\n## {card['name']}  (`inbox/{card['id']}.png`)\n\n{p}\n")
    with open(os.path.join(HERE, "prompts", "ALL.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(combined))
    print(f"Готово: {len(cat['cards'])} промптов в prompts/ (см. prompts/ALL.md)")


def render_card(card, cfg):
    """Собирает готовую (потрёпанную) карту. Берёт арт из inbox/ или плейсхолдер."""
    inbox = os.path.join(HERE, "inbox", f"{card['id']}.png")
    if os.path.exists(inbox):
        return make_card(card, Image.open(inbox).convert("RGBA"), cfg), "арт"
    return make_card(card, placeholder_subject(card, cfg), cfg), "плейсхолдер"


def cmd_build(cfg, cat, args):
    os.makedirs(os.path.join(HERE, "output"), exist_ok=True)
    cards = [c for c in cat["cards"] if not args.card or c["id"] == args.card]
    if not cards:
        print(f"Карта '{args.card}' не найдена в catalog.json")
        return
    templated = cfg.get("template", {}).get("enabled")
    mrot = cfg["wear"]["max_rotation"]
    for card in cards:
        img, tag = render_card(card, cfg)
        if not templated:                                   # шаблон уже «кривой» вручную — не крутим
            angle = np.random.default_rng(card_seed(card)).uniform(-mrot, mrot)
            img = img.rotate(angle, expand=True, resample=Image.BICUBIC)
        img.save(os.path.join(HERE, "output", f"{card['id']}.png"))
        print(f"  ✓ {card['name']:<14} [{tag}] → output/{card['id']}.png")
    print("Готово.")


def cmd_shop(cfg, cat, args):
    """Магазинный вариант карты: обычная карта + ценник снизу, отдельной картинкой."""
    outdir = os.path.join(HERE, "output", "shop")
    os.makedirs(outdir, exist_ok=True)
    priced = [c for c in cat["cards"] if "price" in c]
    if not priced:
        print("В catalog.json нет карт с полем 'price'.")
        return
    gap, plate_h = 20, 88
    for card in priced:
        card_img, tag = render_card(card, cfg)
        W, H = card_img.size
        canvas = Image.new("RGBA", (W, H + gap + plate_h + 6), (0, 0, 0, 0))
        canvas.paste(card_img, (0, 0), card_img)
        draw_price_plate(canvas, W // 2, H + gap, card["price"], cfg)
        canvas.save(os.path.join(outdir, f"{card['id']}.png"))
        print(f"  ✓ {card['name']:<14} [{tag}] + ценник {card['price']}◎ → output/shop/{card['id']}.png")
    print("Готово.")


def main():
    cfg = load_json("style.config.json")
    cat = load_json("catalog.json")
    ap = argparse.ArgumentParser(description="style-forge — единый стиль карт")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prompts", help="сгенерить промпты для ChatGPT")
    b = sub.add_parser("build", help="собрать карты")
    b.add_argument("--card", help="id одной карты")
    sub.add_parser("shop", help="собрать витрину магазина")
    args = ap.parse_args()
    {"prompts": cmd_prompts, "build": cmd_build, "shop": cmd_shop}[args.cmd](cfg, cat, args)


if __name__ == "__main__":
    main()
