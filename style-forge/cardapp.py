# -*- coding: utf-8 -*-
"""
Card Forge — редактор карт с интерфейсом для iPhone (Pythonista).

Открой в Pythonista и нажми ▶️ Run.
  • Список карт со светлой/тёмной темой (кнопка «Тема»).
  • Карты с иконкой помечены 🔒 и защищены от случайного удаления.
    Карты без иконки можно удалить свайпом влево.
  • «＋» — новая карта.
  • Тап по карте → окно-редактор: название, описание, стоимость (0–10),
    иконка (тап → галерея), и «Сохранить».
"""
import os
import sys
import json
import time

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
CATALOG = os.path.join(HERE, "catalog.json")

TYPES = ["attack", "skill", "power", "item"]
TYPE_LABELS = ["Атака", "Навык", "Сила", "Предмет"]

# только светлая тема
TH = {
    "bg": "#efe7d6", "panel": "#fbf6ea", "text": "#2e2218", "sub": "#8a745a",
    "accent": "#b06d2e", "field_bg": "#ffffff", "field_text": "#2e2218", "border": "#d8c8a8",
}


# ─────────────────────────────────────────── данные

def load_data():
    with open(CATALOG, encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    with open(CATALOG, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


DATA = load_data()


def has_icon(card):
    return os.path.exists(os.path.join(HERE, "inbox", card["id"] + ".png"))


def new_id():
    return "card_%d" % int(time.time() * 1000 % 1000000000)


def ui_image(path):
    try:
        with open(path, "rb") as f:
            return ui.Image.from_data(f.read())
    except Exception:
        return None


def row_thumb(card):
    for p in (os.path.join(HERE, "inbox", card["id"] + ".png"),
              os.path.join(HERE, "output", card["id"] + ".png")):
        if os.path.exists(p):
            return ui_image(p)
    return None


def pick_image():
    if photos is None:
        console.hud_alert("Доступ к Фото недоступен", "error", 2)
        return None
    try:
        asset = photos.pick_asset()
        return asset.get_image() if asset else None
    except AttributeError:
        try:
            return photos.pick_image()
        except Exception as e:
            console.hud_alert("Не удалось: %s" % e, "error", 2.5)
            return None


def rebuild_card_image(card):
    try:
        img, _ = forge.render_card(card, cfg)
        os.makedirs(os.path.join(HERE, "output"), exist_ok=True)
        img.save(os.path.join(HERE, "output", card["id"] + ".png"))
    except Exception:
        pass


# ─────────────────────────────────────────── редактор карты

class EditorView(ui.View):
    def __init__(self, card, is_new, on_saved, nav):
        super().__init__()
        self.card = card
        self.is_new = is_new
        self.on_saved = on_saved
        self.nav = nav
        self.cost = int(card.get("cost", 1))
        self.name = card.get("name", "") or "Новая карта"
        self.background_color = TH["bg"]
        self.right_button_items = [ui.ButtonItem(title="Сохранить", action=self.save)]

        self.scroll = ui.ScrollView()
        self.scroll.background_color = TH["bg"]
        self.add_subview(self.scroll)

        # иконка
        self.icon_btn = ui.Button()
        self.icon_btn.corner_radius = 16
        self.icon_btn.background_color = TH["field_bg"]
        self.icon_btn.border_width = 1
        self.icon_btn.border_color = TH["border"]
        self.icon_btn.tint_color = TH["sub"]
        self.icon_btn.title = "Нажми, чтобы выбрать иконку"
        self.icon_btn.action = self.choose_icon
        ic = os.path.join(HERE, "inbox", card["id"] + ".png")
        if os.path.exists(ic):
            self.icon_btn.background_image = ui_image(ic)
            self.icon_btn.title = ""
        self.scroll.add_subview(self.icon_btn)

        self.name_field = self._field(card.get("name", ""), "Название")
        self.desc_view = ui.TextView()
        self.desc_view.text = card.get("text", "")
        self.desc_view.font = ("HelveticaNeue", 17)
        self.desc_view.background_color = TH["field_bg"]
        self.desc_view.text_color = TH["field_text"]
        self.desc_view.corner_radius = 12
        self.scroll.add_subview(self.desc_view)

        self.cost_btn = ui.Button()
        self.cost_btn.title = "Стоимость:  %d" % self.cost
        self.cost_btn.font = ("HelveticaNeue-Bold", 17)
        self.cost_btn.background_color = TH["field_bg"]
        self.cost_btn.tint_color = TH["text"]
        self.cost_btn.corner_radius = 12
        self.cost_btn.action = self.choose_cost
        self.scroll.add_subview(self.cost_btn)

        self.price = card.get("price")
        self.price_btn = ui.Button()
        self.price_btn.title = self._price_title()
        self.price_btn.font = ("HelveticaNeue-Bold", 17)
        self.price_btn.background_color = TH["field_bg"]
        self.price_btn.tint_color = TH["text"]
        self.price_btn.corner_radius = 12
        self.price_btn.action = self.choose_price
        self.scroll.add_subview(self.price_btn)

        self.type_seg = ui.SegmentedControl()
        self.type_seg.segments = TYPE_LABELS
        self.type_seg.selected_index = TYPES.index(card.get("type", "attack")) if card.get("type", "attack") in TYPES else 0
        self.type_seg.tint_color = TH["accent"]
        self.scroll.add_subview(self.type_seg)

        self.labels = []
        for t in ("Название", "Описание", "Стоимость", "Тип", "Цена (в магазине)"):
            lb = ui.Label()
            lb.text = t.upper()
            lb.font = ("HelveticaNeue-Bold", 12)
            lb.text_color = TH["sub"]
            self.scroll.add_subview(lb)
            self.labels.append(lb)

        self.preview_btn = ui.Button()
        self.preview_btn.title = "👁  Посмотреть карту"
        self.preview_btn.font = ("HelveticaNeue-Bold", 18)
        self.preview_btn.background_color = TH["field_bg"]
        self.preview_btn.tint_color = TH["text"]
        self.preview_btn.border_width = 1
        self.preview_btn.border_color = TH["border"]
        self.preview_btn.corner_radius = 14
        self.preview_btn.action = self.preview
        self.scroll.add_subview(self.preview_btn)

        self.save_btn = ui.Button()
        self.save_btn.title = "Сохранить карту"
        self.save_btn.font = ("HelveticaNeue-Bold", 19)
        self.save_btn.background_color = TH["accent"]
        self.save_btn.tint_color = "#ffffff"
        self.save_btn.corner_radius = 14
        self.save_btn.action = self.save
        self.scroll.add_subview(self.save_btn)

        self.delete_btn = None
        if not is_new:
            self.delete_btn = ui.Button()
            self.delete_btn.title = "🗑  Удалить карту"
            self.delete_btn.font = ("HelveticaNeue-Bold", 17)
            self.delete_btn.tint_color = "#c0392b"
            self.delete_btn.background_color = TH["field_bg"]
            self.delete_btn.border_width = 1
            self.delete_btn.border_color = "#c0392b"
            self.delete_btn.corner_radius = 14
            self.delete_btn.action = self.delete
            self.scroll.add_subview(self.delete_btn)

    def _field(self, value, placeholder):
        f = ui.TextField()
        f.text = value
        f.placeholder = placeholder
        f.font = ("HelveticaNeue", 18)
        f.background_color = TH["field_bg"]
        f.text_color = TH["field_text"]
        f.bordered = False
        f.corner_radius = 12
        f.clip_to_bounds = True
        self.scroll.add_subview(f)
        return f

    def layout(self):
        m = 18
        w = self.width - 2 * m
        self.scroll.frame = self.bounds
        y = 16
        side = min(w, 200)
        self.icon_btn.frame = ((self.width - side) / 2, y, side, side)
        y += side + 22
        rows = [
            (self.labels[0], self.name_field, 48),
            (self.labels[1], self.desc_view, 110),
            (self.labels[2], self.cost_btn, 50),
            (self.labels[3], self.type_seg, 40),
            (self.labels[4], self.price_btn, 50),
        ]
        for lb, field, h in rows:
            lb.frame = (m, y, w, 16)
            y += 20
            field.frame = (m, y, w, h)
            y += h + 16
        self.preview_btn.frame = (m, y + 6, w, 52)
        y += 66
        self.save_btn.frame = (m, y, w, 56)
        y += 76
        if self.delete_btn:
            self.delete_btn.frame = (m, y, w, 50)
            y += 64
        self.scroll.content_size = (self.width, y)

    def _price_title(self):
        return "Цена:  %d ◎" % self.price if self.price is not None else "Цена:  нет"

    def choose_price(self, sender):
        cur = str(self.price) if self.price is not None else ""
        try:
            v = dialogs.input_alert("Цена в магазине", "Число монет (пусто = без цены)", cur, "OK")
        except KeyboardInterrupt:
            return
        v = (v or "").strip()
        if v == "":
            self.price = None
        else:
            try:
                self.price = max(0, int(v))
            except ValueError:
                console.hud_alert("Нужно число", "error", 1.5)
                return
        self.price_btn.title = self._price_title()

    def current_card(self):
        c = dict(self.card)
        c["name"] = self.name_field.text.strip() or "Без названия"
        c["text"] = self.desc_view.text.strip()
        c["cost"] = self.cost
        c["type"] = TYPES[self.type_seg.selected_index]
        if self.price is not None:
            c["price"] = self.price
        else:
            c.pop("price", None)
        if not c.get("art"):
            c["art"] = c["name"]
        return c

    def preview(self, sender):
        c = self.current_card()
        console.show_activity("Собираю…")
        try:
            if c.get("price") is not None:
                img, _ = forge.shop_card(c, cfg)      # с ценником
            else:
                img, _ = forge.render_card(c, cfg)
            os.makedirs(os.path.join(HERE, "output"), exist_ok=True)
            path = os.path.join(HERE, "output", c["id"] + "__preview.png")
            img.save(path)
        except Exception as e:
            console.hide_activity()
            console.hud_alert("Ошибка: %s" % e, "error", 2.5)
            return
        console.hide_activity()
        console.quicklook(path)

    def choose_cost(self, sender):
        v = dialogs.list_dialog("Стоимость", [str(i) for i in range(0, 11)])
        if v is not None:
            self.cost = int(v)
            self.cost_btn.title = "Стоимость:  %d" % self.cost

    def choose_icon(self, sender):
        img = pick_image()
        if img is None:
            return
        os.makedirs(os.path.join(HERE, "inbox"), exist_ok=True)
        dest = os.path.join(HERE, "inbox", self.card["id"] + ".png")
        try:
            img.save(dest)
        except Exception as e:
            console.hud_alert("Не сохранилось: %s" % e, "error", 2.5)
            return
        self.icon_btn.background_image = ui_image(dest)
        self.icon_btn.title = ""
        if img.convert("RGBA").getextrema()[3][0] == 255:
            console.hud_alert("Иконка БЕЗ прозрачного фона!", "error", 2.5)
        else:
            console.hud_alert("Иконка добавлена", "success", 1.2)

    def delete(self, sender):
        icon = os.path.join(HERE, "inbox", self.card["id"] + ".png")
        extra = "  (с иконкой)" if os.path.exists(icon) else ""
        try:
            console.alert("Удалить карту?", (self.card.get("name") or "Без названия") + extra, "Удалить")
        except KeyboardInterrupt:
            return
        ids = [c["id"] for c in DATA["cards"]]
        if self.card["id"] in ids:
            del DATA["cards"][ids.index(self.card["id"])]
            save_data(DATA)
        for p in (os.path.join(HERE, "output", self.card["id"] + ".png"),
                  os.path.join(HERE, "output", "shop", self.card["id"] + ".png"),
                  os.path.join(HERE, "output", self.card["id"] + "__preview.png"),
                  icon):
            try:
                os.remove(p)
            except OSError:
                pass
        console.hud_alert("Удалено", "success", 1.0)
        self.on_saved()
        self.nav.pop_view()

    def save(self, sender):
        self.card["name"] = self.name_field.text.strip() or "Без названия"
        self.card["text"] = self.desc_view.text.strip()
        self.card["cost"] = self.cost
        self.card["type"] = TYPES[self.type_seg.selected_index]
        if self.price is not None:
            self.card["price"] = self.price
        else:
            self.card.pop("price", None)
        if not self.card.get("art"):
            self.card["art"] = self.card["name"]
        ids = [c["id"] for c in DATA["cards"]]
        if self.card["id"] in ids:
            DATA["cards"][ids.index(self.card["id"])] = self.card
        else:
            DATA["cards"].append(self.card)
        save_data(DATA)
        rebuild_card_image(self.card)
        console.hud_alert("Сохранено", "success", 1.0)
        self.on_saved()
        self.nav.pop_view()


# ─────────────────────────────────────────── список карт

class ListView(ui.View):
    def __init__(self):
        super().__init__()
        self.name = "Карты"
        self.nav = None
        self.tv = ui.TableView()
        self.tv.data_source = self
        self.tv.delegate = self
        self.tv.row_height = 64
        self.add_subview(self.tv)
        self.right_button_items = [
            ui.ButtonItem(title="＋", action=self.new_card),
        ]
        self.left_button_items = [ui.ButtonItem(title="Закрыть", action=lambda s: self.nav.close())]
        self.apply_theme()

    def layout(self):
        self.tv.frame = self.bounds

    def apply_theme(self):
        self.background_color = TH["bg"]
        self.tv.background_color = TH["bg"]
        self.tv.separator_color = TH["border"]
        if self.nav:
            self.nav.background_color = TH["bg"]
            self.nav.tint_color = TH["accent"]
        self.tv.reload()

    def new_card(self, sender):
        card = {"id": new_id(), "name": "", "type": "attack", "cost": 1, "text": "", "art": ""}
        self.open_editor(card, True)

    def open_editor(self, card, is_new):
        ed = EditorView(card, is_new, self.reload_list, self.nav)
        ed.name = "Новая карта" if is_new else "Карта"
        self.nav.push_view(ed)

    def reload_list(self):
        self.tv.reload()

    # data source / delegate
    def tableview_number_of_rows(self, tv, section):
        return len(DATA["cards"])

    def tableview_cell_for_row(self, tv, section, row):
        card = DATA["cards"][row]
        cell = ui.TableViewCell()
        lock = "🔒 " if has_icon(card) else ""
        cell.text_label.text = "%s%s   ·   %d⚡" % (lock, card.get("name") or "Без названия", card.get("cost", 0))
        cell.text_label.text_color = TH["text"]
        cell.background_color = TH["panel"]
        cell.selected_background_view = ui.View()
        cell.selected_background_view.background_color = TH["field_bg"]
        cell.accessory_type = "disclosure_indicator"
        img = row_thumb(card)
        if img:
            cell.image_view.image = img
        return cell

    def tableview_did_select(self, tv, section, row):
        tv.selected_row = -1
        self.open_editor(DATA["cards"][row], False)

    def tableview_can_delete(self, tv, section, row):
        return not has_icon(DATA["cards"][row])  # карты с иконкой не удаляются

    def tableview_delete(self, tv, section, row):
        card = DATA["cards"][row]
        del DATA["cards"][row]
        save_data(DATA)
        for p in (os.path.join(HERE, "output", card["id"] + ".png"),
                  os.path.join(HERE, "output", "shop", card["id"] + ".png")):
            try:
                os.remove(p)
            except OSError:
                pass
        tv.reload()


def main():
    lst = ListView()
    nav = ui.NavigationView(lst)
    lst.nav = nav
    lst.apply_theme()
    nav.name = "Card Forge"
    nav.present("fullscreen")


if __name__ == "__main__":
    main()
