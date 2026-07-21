# -*- coding: utf-8 -*-
"""
Card Forge — простой интерфейс для сборки карт на iPhone (Pythonista).

Открой этот файл в Pythonista и нажми ▶️ Run. Появятся большие кнопки:
  • Собрать все карты      — пересобирает всё в output/
  • Собрать магазин        — варианты с ценником в output/shop/
  • Показать карту         — выбрать карту и посмотреть её
  • Добавить иконку        — выбрать карту и подложить картинку из Фото

Никаких команд вводить не нужно — только тапы.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import ui
import console
import dialogs
import forge

try:
    import photos
except ImportError:
    photos = None

cfg = forge.load_json("style.config.json")


def cards():
    return forge.load_json("catalog.json")["cards"]


class Args:
    def __init__(self, card=None):
        self.card = card


# ─────────────────────────────────────────── действия кнопок

def build_all(sender):
    console.show_activity("Собираю карты…")
    try:
        forge.cmd_build(cfg, forge.load_json("catalog.json"), Args())
        console.hud_alert("Готово! Карты в output/", "success", 1.3)
    except Exception as e:
        console.hud_alert("Ошибка: %s" % e, "error", 2.5)
    finally:
        console.hide_activity()


def build_shop(sender):
    console.show_activity("Собираю магазин…")
    try:
        forge.cmd_shop(cfg, forge.load_json("catalog.json"), Args())
        console.hud_alert("Готово! Магазин в output/shop/", "success", 1.3)
    except Exception as e:
        console.hud_alert("Ошибка: %s" % e, "error", 2.5)
    finally:
        console.hide_activity()


def show_card(sender):
    cs = cards()
    names = [c["name"] for c in cs]
    choice = dialogs.list_dialog("Какую карту показать?", names)
    if not choice:
        return
    card = cs[names.index(choice)]
    console.show_activity("Собираю…")
    try:
        img, _ = forge.render_card(card, cfg)
        os.makedirs(os.path.join(HERE, "output"), exist_ok=True)
        path = os.path.join(HERE, "output", card["id"] + ".png")
        img.save(path)
    except Exception as e:
        console.hide_activity()
        console.hud_alert("Ошибка: %s" % e, "error", 2.5)
        return
    console.hide_activity()
    console.quicklook(path)


def pick_image():
    if photos is None:
        console.hud_alert("Доступ к Фото недоступен", "error", 2)
        return None
    try:
        asset = photos.pick_asset()
        if asset is None:
            return None
        return asset.get_image()
    except AttributeError:
        try:
            return photos.pick_image()
        except Exception as e:
            console.hud_alert("Не удалось: %s" % e, "error", 2.5)
            return None


def add_icon(sender):
    cs = cards()
    names = [c["name"] for c in cs]
    choice = dialogs.list_dialog("Иконку для какой карты?", names)
    if not choice:
        return
    card = cs[names.index(choice)]
    img = pick_image()
    if img is None:
        return
    os.makedirs(os.path.join(HERE, "inbox"), exist_ok=True)
    dest = os.path.join(HERE, "inbox", card["id"] + ".png")
    img.save(dest)
    # проверяем прозрачность: Фото часто сохраняют без альфы
    alpha_min = img.convert("RGBA").getextrema()[3][0]
    if alpha_min == 255:
        console.hud_alert("Сохранено, но БЕЗ прозрачного фона!", "error", 2.5)
    else:
        console.hud_alert("Иконка «%s» сохранена" % card["name"], "success", 1.5)


# ─────────────────────────────────────────── интерфейс

BUTTONS = [
    ("🔨  Собрать все карты", build_all, "#7a5230"),
    ("🏷  Собрать магазин", build_shop, "#5e7c6e"),
    ("👁  Показать карту", show_card, "#3e5c6e"),
    ("🖼  Добавить иконку", add_icon, "#6e4a7a"),
]


class ForgeApp(ui.View):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.name = "Card Forge"
        self.background_color = "#efe7d6"

        self.title = ui.Label()
        self.title.text = "Card Forge"
        self.title.font = ("HelveticaNeue-Bold", 30)
        self.title.text_color = "#2e2218"
        self.title.alignment = ui.ALIGN_CENTER
        self.add_subview(self.title)

        self.hint = ui.Label()
        self.hint.text = "Собери карты одним касанием"
        self.hint.font = ("HelveticaNeue", 15)
        self.hint.text_color = "#7a5230"
        self.hint.alignment = ui.ALIGN_CENTER
        self.add_subview(self.hint)

        self.buttons = []
        for title, action, color in BUTTONS:
            b = ui.Button(title=title)
            b.background_color = color
            b.tint_color = "white"
            b.font = ("HelveticaNeue-Bold", 19)
            b.corner_radius = 14
            b.action = action
            self.add_subview(b)
            self.buttons.append(b)

    def layout(self):
        m = 22
        w = self.width - 2 * m
        self.title.frame = (m, 60, w, 40)
        self.hint.frame = (m, 102, w, 24)
        h, gap = 66, 18
        total = len(self.buttons) * (h + gap) - gap
        y0 = max(150, (self.height - total) / 2)
        for i, b in enumerate(self.buttons):
            b.frame = (m, y0 + i * (h + gap), w, h)


if __name__ == "__main__":
    ForgeApp().present("fullscreen")
