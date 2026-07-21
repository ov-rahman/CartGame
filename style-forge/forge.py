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
import numpy as np
from PIL import Image, ImageDraw, ImageFont

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

def draw_gem(base, x, y, r, number, color, cfg):
    d = ImageDraw.Draw(base)
    ink = hex2rgb(cfg["card"]["ink"])
    d.ellipse([x - r, y - r, x + r, y + r], fill=hex2rgb(color), outline=ink, width=6)
    d.arc([x - r + 8, y - r + 8, x + r - 8, y + r - 8], 200, 340, fill=(255, 255, 255, 90), width=4)
    f = font(cfg, "number", int(r * 1.25))
    s = str(number)
    w = d.textlength(s, font=f)
    asc, desc = f.getmetrics()
    d.text((x - w / 2, y - (asc + desc) / 2), s, font=f, fill=(255, 255, 255))


def draw_coin(base, x, y, r, number, cfg):
    d = ImageDraw.Draw(base)
    ink = hex2rgb(cfg["card"]["ink"])
    col = hex2rgb(cfg["coin_color"])
    d.ellipse([x - r, y - r, x + r, y + r], fill=col, outline=ink, width=5)
    d.ellipse([x - r + 7, y - r + 7, x + r - 7, y + r - 7], outline=ink, width=2)
    f = font(cfg, "number", int(r * 1.05))
    s = str(number)
    w = d.textlength(s, font=f)
    asc, desc = f.getmetrics()
    d.text((x - w / 2, y - (asc + desc) / 2), s, font=f, fill=hex2rgb(cfg["card"]["ink"]))


# ────────────────────────────────────────────────────────── карта

def make_card(card, subject, cfg):
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

    # окно арта
    ax0, ay0, ax1, ay1 = 46, 92, W - 46, 512
    inset = make_paper(ax1 - ax0, ay1 - ay0, cfg)
    inset = Image.eval(inset, lambda p: int(p * 0.93))  # чуть темнее
    img.paste(inset, (ax0, ay0), inset)

    subj = apply_grade(subject, cfg)
    subj = fit_contain(subj, (ax1 - ax0 - 28, ay1 - ay0 - 28))
    img.paste(subj, (ax0 + (ax1 - ax0 - subj.width) // 2,
                     ay0 + (ay1 - ay0 - subj.height) // 2), subj)
    d.rounded_rectangle([ax0, ay0, ax1, ay1], radius=16, outline=ink, width=4)

    # баннер с названием
    by0, by1 = 528, 590
    banner = hex2rgb(tstyle["banner"])
    d.rounded_rectangle([40, by0, W - 40, by1], radius=14, fill=banner, outline=ink, width=4)
    tf = fit_font(cfg, "title", card["name"], W - 130, 42)
    tw = tf.getlength(card["name"])
    asc, desc = tf.getmetrics()
    d.text(((W - tw) / 2, (by0 + by1) / 2 - (asc + desc) / 2 + 2),
           card["name"], font=tf, fill=hex2rgb(tstyle["banner_ink"]))

    # тип (мелкие капсы с разрядкой)
    lf = font(cfg, "body", 22)
    label = " ".join(tstyle["label"])
    lw = lf.getlength(label)
    d.text(((W - lw) / 2, by1 + 12), label, font=lf, fill=ink_soft)

    # описание
    bf = font(cfg, "body", 30)
    lines = wrap(d, card["text"], bf, W - 130)
    ty = 664
    for line in lines:
        lw = d.textlength(line, font=bf)
        d.text(((W - lw) / 2, ty), line, font=bf, fill=ink)
        ty += 40

    # энергия (самоцвет слева сверху)
    ecol = cfg["energy_colors"].get(str(card["cost"]), cfg["energy_colors"]["default"])
    draw_gem(img, m + 30, m + 30, 42, card["cost"], ecol, cfg)

    # цена (монета справа снизу), если есть
    if "price" in card:
        draw_coin(img, W - m - 40, H - m - 40, 40, card["price"], cfg)

    return img


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


def cmd_build(cfg, cat, args):
    os.makedirs(os.path.join(HERE, "output"), exist_ok=True)
    cards = [c for c in cat["cards"] if not args.card or c["id"] == args.card]
    if not cards:
        print(f"Карта '{args.card}' не найдена в catalog.json")
        return
    for card in cards:
        inbox = os.path.join(HERE, "inbox", f"{card['id']}.png")
        if os.path.exists(inbox):
            subject, tag = Image.open(inbox).convert("RGBA"), "арт"
        else:
            subject, tag = placeholder_subject(card, cfg), "плейсхолдер"
        out = os.path.join(HERE, "output", f"{card['id']}.png")
        make_card(card, subject, cfg).save(out)
        print(f"  ✓ {card['name']:<14} [{tag}] → output/{card['id']}.png")
    print("Готово.")


def main():
    cfg = load_json("style.config.json")
    cat = load_json("catalog.json")
    ap = argparse.ArgumentParser(description="style-forge — единый стиль карт")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prompts", help="сгенерить промпты для ChatGPT")
    b = sub.add_parser("build", help="собрать карты")
    b.add_argument("--card", help="id одной карты")
    args = ap.parse_args()
    {"prompts": cmd_prompts, "build": cmd_build}[args.cmd](cfg, cat, args)


if __name__ == "__main__":
    main()
