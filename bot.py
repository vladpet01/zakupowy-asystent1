# bot.py — Полный бот по "Структура меню и сценариев 1 (защищено)"
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
application = ApplicationBuilder().token(BOT_TOKEN).build()


import re
import json
import sqlite3
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    ApplicationBuilder, Application, ContextTypes, CommandHandler,
    MessageHandler, CallbackQueryHandler, ConversationHandler, filters,
    JobQueue
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =========================
# 1) Конфиг и константы
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Не найден BOT_TOKEN. Установите переменную окружения BOT_TOKEN с токеном от BotFather.")

DB_PATH = os.getenv("DB_PATH", "zakupowy.db")

# Состояния разговоров
(
    MAIN_MENU,
    ENTER_LIST,
    AFTER_LIST_ACTION,
    CONFIRM_SAVE,
    ENTER_LIST_NAME,
    PLAN_OR_NOT,
    ENTER_PLAN_DATETIME,
    CATEGORIES_PICK,
    EDIT_LIST_ENTER,
    DEALS_RESULT,
    LANG_SELECT
) = range(11)

REGIONAL_SEARCH_LANG = "pl"
DEFAULT_UI_LANG = "ru"

# Категории (код: (emoji, RU, PL, keywords_ru, keywords_pl))
CATEGORIES = {
    "FROZEN":    ("🧊", "Заморозка", "Mrożonki", ["замор", "лед", "пельмен", "морож"], ["mroż", "lód", "pierogi", "lody"]),
    "PANTRY":    ("🥫", "Длительного хранения", "Produkty suche", ["круп", "консерв", "макарон", "рис"], ["kasza", "konserw", "makaron", "ryż"]),
    "MEAT":      ("🥩", "Мясо", "Mięso", ["мяс", "свинин", "говядин", "кур"], ["mięso", "wieprz", "wołow", "kurcz"]),
    "DAIRY":     ("🥛", "Молочка", "Nabiał", ["молок", "сыр", "йогурт", "смет"], ["mleko", "ser", "jogurt", "śmiet"]),
    "BAKERY":    ("🍞", "Выпечка", "Pieczywo", ["хлеб", "булк", "батон", "багет"], ["chleb", "bułka", "bagiet"])
}

# Словарь нормализации (RU/EN->PL)
LEXICON_TO_PL = {
    "молоко": "mleko", "хлеб": "chleb", "сыр": "ser", "йогурт": "jogurt", "яйца": "jajka",
    "свинина": "wieprzowina", "говядина": "wołowina", "курица": "kurczak", "масло": "masło",
    "corn": "kukurydza", "milk": "mleko", "bread": "chleb", "cheese": "ser", "yogurt": "jogurt",
    "kurczak": "kurczak", "ser": "ser", "mleko": "mleko", "chleb": "chleb", "jogurt": "jogurt",
    "вода": "woda", "сок": "sok", "кола": "cola", "пепси": "pepsi", "кофе": "kawa",
    "чай": "herbata", "сахар": "cukier", "соль": "sól", "перец": "pieprz", "мука": "mąka",
    "масло": "olej", "томат": "pomidor", "огурец": "ogórek", "картофель": "ziemniak",
    "лук": "cebula", "чеснок": "czosnek", "яблоко": "jabłko", "банан": "banan",
    "апельсин": "pomarańcza", "лимон": "cytryna", "виноград": "winogrono",
    "клубника": "truskawka", "малина": "malina", "говядина": "wołowina",
    "курица": "kurczak", "индейка": "indyk", "рыба": "ryba", "лосось": "łosoś",
    "тунец": "tuńczyk", "креветки": "krewetki", "сосиски": "kiełbasa",
    "колбаса": "kiełbasa", "ветчина": "szynka", "бекон": "boczek", "яйцо": "jajko",
    "молоко": "mleko", "кефир": "kefir", "творог": "twaróg", "сметана": "śmietana",
    "йогурт": "jogurt", "мороженое": "lody", "сыр": "ser", "макароны": "makaron",
    "рис": "ryż", "гречка": "kasza gryczana", "овсянка": "płatki owsiane",
    "мука": "mąka", "сахар": "cukier", "соль": "sól", "перец": "pieprz",
    "масло": "olej", "уксус": "ocet", "кетчуп": "keczup", "майонез": "majonez",
    "горчица": "musztarda", "хлеб": "chleb", "булка": "bułka", "багет": "bagietka",
    "печенье": "ciastko", "шоколад": "czekolada", "конфеты": "cukierki",
    "мед": "miód", "варенье": "dżem", "орехи": "orzechy", "чипсы": "chipsy",
    "пиво": "piwo", "вино": "wino", "водка": "wódka", "виски": "whisky",
    "сок": "sok", "вода": "woda", "газировка": "napój gazowany",
    "кофе": "kawa", "чай": "herbata", "какао": "kakao"
}

# UI словарь (RU/PL/EN)
UI = {
    "ru": {
        "greet": "Привет! Выберите действие:",
        "menu": ["📝 Напиши список", "📦 Поиск по категориям", "🛍 Акции / Скидки", "📂 Списки", "ℹ️ Помощь", "🌐 Сменить язык"],
        "send_list": "Отправьте список продуктов в любом формате:",
        "after_list": "Список принят. Что сделать?",
        "best": "🔍 Показать лучшие варианты",
        "save": "💾 Сохранить",
        "delete": "🗑 Удалить",
        "confirm_save": "Готово. Сохранить список или удалить?",
        "enter_name": "Как назвать этот список?",
        "saved": "✅ Список «{name}» сохранён.",
        "plan_prompt": "📅 Запланировать покупки или ⏳ Не сейчас?",
        "plan": "📅 Запланировать", "not_now": "⏳ Не сейчас",
        "enter_date": "Укажите дату и время (формат YYYY-MM-DD HH:MM), локальное время:",
        "plan_ok": "✅ Список «{name}» запланирован на {dt}.",
        "saved_no_plan": "✅ Список «{name}» сохранён без планирования.",
        "deleted": "🗑 Удалено.",
        "help": "ℹ️ Я помогу выбрать лучшие цены по списку, категориям или показать актуальные акции.\nНапишите список на любом языке — я переведу и найду на польском, а результат верну на языке интерфейса с оригиналом в скобках.",
        "lists_title": "📂 Ваши списки:",
        "no_lists": "Пока нет сохранённых списков.",
        "active": "🛒 Активные",
        "planned": "📅 Запланированные",
        "view": "🔍 Лучшие варианты", "edit": "✏️ Изменить", "remove": "🗑 Удалить", "replan": "📅 Запланировать",
        "enter_new_list": "Отправьте новый список для обновления «{name}»:",
        "updated": "✅ Список «{name}» обновлён.",
        "plan_changed": "✅ План для «{name}» обновлён: {dt}",
        "reminder": "📅 Сегодня у вас запланирован список «{name}». Хотите посмотреть лучшие цены?",
        "yes_show": "🔍 Показать лучшие варианты", "back": "🔙 Назад в меню",
        "lang_prompt": "Выберите язык интерфейса:",
        "lang_set": "✅ Язык интерфейса: {lang}",
        "top_deals": "🛍 Топ-{n} акций сегодня:",
        "show_all_deals": "📂 Показать все акции",
        "filter_category": "🔍 Фильтр по категории",
        "done": "✅ Готово",
        "pick_categories": "Выберите категории, затем нажмите «✅ Готово»:",
        "results_header": "Результаты:",
        "best_store_all": "Лучше всего купить всё в {store}",
        "best_combo": "Оптимально по магазинам: {combo}",
        "nothing_found": "Не найдено актуальных предложений.",
        "invalid_dt": "❌ Неверный формат. Пример: 2025-09-05 10:00",
        "saved_as": "Как назвать результат?",
        "saved_result_ok": "✅ Результат «{name}» сохранён.",
        "deals_result": "🛍 Найдено {count} акций. Что сделать с результатом?",
        "expired": "⏰ Истёкший",
        "change_lang": "🌐 Сменить язык",
        "lang_ru": "🇷🇺 Русский",
        "lang_pl": "🇵🇱 Polski", 
        "lang_en": "🇺🇸 English",
        "back_to_menu": "🔙 Назад в меню"
    },
    "pl": {
        "greet": "Cześć! Wybierz działanie:",
        "menu": ["📝 Napisz listę", "📦 Wyszukiwanie po kategoriach", "🛍 Promocje", "📂 Listy", "ℹ️ Pomoc", "🌐 Zmień język"],
        "send_list": "Wyślij listę produktów w dowolnym formacie:",
        "after_list": "Lista przyjęta. Co zrobić?",
        "best": "🔍 Najlepsze oferty",
        "save": "💾 Zapisz",
        "delete": "🗑 Usuń",
        "confirm_save": "Gotowe. Zapisać listę czy usunąć?",
        "enter_name": "Jak nazwać tę listę?",
        "saved": "✅ Lista «{name}» zapisana.",
        "plan_prompt": "📅 Zaplanować zakupy czy ⏳ Nie teraz?",
        "plan": "📅 Zaplanuj", "not_now": "⏳ Nie teraz",
        "enter_date": "Podaj datę i godzinę (YYYY-MM-DD HH:MM), czas lokalny:",
        "plan_ok": "✅ Lista «{name}» zaplanowana na {dt}.",
        "saved_no_plan": "✅ Lista «{name}» zapisana bez planowania.",
        "deleted": "🗑 Usunięto.",
        "help": "ℹ️ Pomogę wybrać najlepsze ceny według listy, kategorii albo pokażę aktualne promocje.",
        "lists_title": "📂 Twoje listy:",
        "no_lists": "Brak zapisanych list.",
        "active": "🛒 Aktywne",
        "planned": "📅 Zaplanowane",
        "view": "🔍 Najlepsze oferty", "edit": "✏️ Edytuj", "remove": "🗑 Usuń", "replan": "📅 Zaplanuj",
        "enter_new_list": "Wyślij nową listę do aktualizacji «{name}»:",
        "updated": "✅ Lista «{name}» zaktualizowana.",
        "plan_changed": "✅ Plan dla «{name}» ustawiono: {dt}",
        "reminder": "📅 Dziś masz zaplanowaną listę «{name}». Pokazać najlepsze ceny?",
        "yes_show": "🔍 Pokaż najlepsze oferty", "back": "🔙 Menu",
        "lang_prompt": "Wybierz język interfejsu:",
        "lang_set": "✅ Język interfejsu: {lang}",
        "top_deals": "🛍 Top-{n} promocji dziś:",
        "show_all_deals": "📂 Pokaż wszystkie promocje",
        "filter_category": "🔍 Filtr kategorii",
        "done": "✅ Gotowe",
        "pick_categories": "Wybierz kategorie, potem «✅ Gotowe»:",
        "results_header": "Wyniki:",
        "best_store_all": "Najlepiej kupić wszystko w {store}",
        "best_combo": "Optymalnie po sklepach: {combo}",
        "nothing_found": "Nie znaleziono aktualnych ofert.",
        "invalid_dt": "❌ Zły format. Np.: 2025-09-05 10:00",
        "saved_as": "Jak nazwać wynik?",
        "saved_result_ok": "✅ Zapisano wynik «{name}».",
        "deals_result": "🛍 Znaleziono {count} promocji. Co zrobić z wynikiem?",
        "expired": "⏰ Wygasły",
        "change_lang": "🌐 Zmień język",
        "lang_ru": "🇷🇺 Rosyjski",
        "lang_pl": "🇵🇱 Polski", 
        "lang_en": "🇺🇸 Angielski",
        "back_to_menu": "🔙 Powrót do menu"
    },
    "en": {
        "greet": "Hi! Choose an action:",
        "menu": ["📝 Write a list", "📦 Category search", "🛍 Deals", "📂 Lists", "ℹ️ Help", "🌐 Change language"],
        "send_list": "Send a product list in any format:",
        "after_list": "List received. What do you want to do?",
        "best": "🔍 Show best offers",
        "save": "💾 Save",
        "delete": "🗑 Delete",
        "confirm_save": "Done. Save the list or delete?",
        "enter_name": "What name for this list?",
        "saved": "✅ List “{name}” saved.",
        "plan_prompt": "📅 Plan purchases or ⏳ Not now?",
        "plan": "📅 Plan", "not_now": "⏳ Not now",
        "enter_date": "Enter date & time (YYYY-MM-DD HH:MM), local time:",
        "plan_ok": "✅ List “{name}” planned for {dt}.",
        "saved_no_plan": "✅ List “{name}” saved without planning.",
        "deleted": "🗑 Deleted.",
        "help": "ℹ️ I can find best prices for your list, categories, or show current deals.",
        "lists_title": "📂 Your lists:",
        "no_lists": "No saved lists yet.",
        "active": "🛒 Active",
        "planned": "📅 Planned",
        "view": "🔍 Best offers", "edit": "✏️ Edit", "remove": "🗑 Delete", "replan": "📅 Plan",
        "enter_new_list": "Send a new list to update “{name}”:",
        "updated": "✅ List “{name}” updated.",
        "plan_changed": "✅ Plan for “{name}” set: {dt}",
        "reminder": "📅 Today you planned list “{name}”. Want best prices now?",
        "yes_show": "🔍 Show best offers", "back": "🔙 Back to menu",
        "lang_prompt": "Choose interface language:",
        "lang_set": "✅ Interface language: {lang}",
        "top_deals": "🛍 Top-{n} deals today:",
        "show_all_deals": "📂 Show all deals",
        "filter_category": "🔍 Filter by category",
        "done": "✅ Done",
        "pick_categories": "Pick categories, then press “✅ Done”:",
        "results_header": "Results:",
        "best_store_all": "Best to buy all in {store}",
        "best_combo": "Optimal by stores: {combo}",
        "nothing_found": "No current offers found.",
        "invalid_dt": "❌ Invalid format. Example: 2025-09-05 10:00",
        "saved_as": "Name this result?",
        "saved_result_ok": "✅ Result “{name}” saved.",
        "deals_result": "🛍 Found {count} deals. What to do with result?",
        "expired": "⏰ Expired",
        "change_lang": "🌐 Change language",
        "lang_ru": "🇷🇺 Russian",
        "lang_pl": "🇵🇱 Polish", 
        "lang_en": "🇺🇸 English",
        "back_to_menu": "🔙 Back to menu"
    }
}

# =========================
# 2) База данных (SQLite)
# =========================

def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            chat_id INTEGER,
            lang_ui TEXT,
            region_lang TEXT
        )""")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            items_json TEXT,
            created_at TEXT,
            planned_for TEXT,
            status TEXT
        )""")

def upsert_user(user_id: int, chat_id: int, lang_ui: str = DEFAULT_UI_LANG, region_lang: str = REGIONAL_SEARCH_LANG):
    with db() as conn:
        cur = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if cur.fetchone():
            conn.execute("UPDATE users SET chat_id=?, lang_ui=?, region_lang=? WHERE user_id=?",
                         (chat_id, lang_ui, region_lang, user_id))
        else:
            conn.execute("INSERT INTO users (user_id, chat_id, lang_ui, region_lang) VALUES (?,?,?,?)",
                         (user_id, chat_id, lang_ui, region_lang))

def set_user_lang(user_id: int, lang_ui: str):
    with db() as conn:
        conn.execute("UPDATE users SET lang_ui=? WHERE user_id=?", (lang_ui, user_id))

def get_user(user_id: int) -> Optional[sqlite3.Row]:
    with db() as conn:
        cur = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        return cur.fetchone()

def add_list(user_id: int, name: str, items: List[str], planned_for: Optional[str], status: str = "active") -> int:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO lists (user_id, name, items_json, created_at, planned_for, status) VALUES (?,?,?,?,?,?)",
            (user_id, name, json.dumps(items, ensure_ascii=False), datetime.now().strftime("%Y-%m-%d %H:%M"),
             planned_for, status)
        )
        return cur.lastrowid

def update_list_items(list_id: int, items: List[str]):
    with db() as conn:
        conn.execute("UPDATE lists SET items_json=? WHERE id=?", (json.dumps(items, ensure_ascii=False), list_id))

def update_list_plan(list_id: int, planned_for: Optional[str], status: str):
    with db() as conn:
        conn.execute("UPDATE lists SET planned_for=?, status=? WHERE id=?", (planned_for, status, list_id))

def delete_list(list_id: int):
    with db() as conn:
        conn.execute("DELETE FROM lists WHERE id=?", (list_id,))

def get_user_lists(user_id: int) -> Tuple[List[sqlite3.Row], List[sqlite3.Row]]:
    with db() as conn:
        act = conn.execute("SELECT * FROM lists WHERE user_id=? AND (status='active' OR status IS NULL) ORDER BY id DESC", (user_id,)).fetchall()
        plan = conn.execute("SELECT * FROM lists WHERE user_id=? AND status='planned' ORDER BY planned_for ASC", (user_id,)).fetchall()
        return act, plan

def get_list_by_id(list_id: int) -> Optional[sqlite3.Row]:
    with db() as conn:
        cur = conn.execute("SELECT * FROM lists WHERE id=?", (list_id,))
        return cur.fetchone()

def get_expired_lists() -> List[sqlite3.Row]:
    with db() as conn:
        return conn.execute(
            "SELECT * FROM lists WHERE status='planned' AND planned_for < datetime('now')"
        ).fetchall()

# =========================
# 3) Мультиязычность и утилиты
# =========================

def lang_of(update: Update) -> str:
    code = (update.effective_user.language_code or DEFAULT_UI_LANG).split("-")[0]
    return code if code in UI else DEFAULT_UI_LANG

def get_ui_lang(update: Update) -> str:
    """Получить язык интерфейса пользователя из базы данных или использовать определенный язык"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    if user and user["lang_ui"]:
        return user["lang_ui"]
    return lang_of(update)

def t(lang: str, key: str, **kwargs) -> str:
    base = UI.get(lang, UI[DEFAULT_UI_LANG]).get(key, key)
    return base.format(**kwargs) if kwargs else base

def normalize_items(raw_text: str) -> List[str]:
    text = raw_text.replace("\n", ",").replace(";", ",")
    parts = re.split(r"[,\s]+", text.strip())
    return [p.strip().lower() for p in parts if p.strip()]

def to_polish_token(token: str) -> str:
    return LEXICON_TO_PL.get(token.lower(), token.lower())

def translate_list_to_pl(items: List[str]) -> List[str]:
    return [to_polish_token(x) for x in items]

def main_menu_kbd(lang: str) -> ReplyKeyboardMarkup:
    m = UI[lang]["menu"]
    return ReplyKeyboardMarkup(
        [[m[0], m[1]], [m[2], m[3]], [m[4], m[5]]],
        resize_keyboard=True
    )

def categories_kbd(lang: str) -> ReplyKeyboardMarkup:
    rows = []
    row = []
    for code, (emoji, ru, pl, _, _) in CATEGORIES.items():
        row.append(f"{emoji} {ru if lang=='ru' else pl if lang=='pl' else pl}")
        if len(row) == 2:
            rows.append(row)
            row = []
    if row: rows.append(row)
    rows.append([UI[lang]["done"]])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def lang_select_kbd() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([
        [UI["ru"]["lang_ru"], UI["pl"]["lang_pl"], UI["en"]["lang_en"]],
        [UI["ru"]["back_to_menu"]]
    ], resize_keyboard=True)

def parse_category_label_to_code(label: str, lang: str) -> Optional[str]:
    label = label.strip()
    for code, (emoji, ru, pl, _, _) in CATEGORIES.items():
        loc = ru if lang == "ru" else pl
        if label.startswith(emoji):
            return code
        if label == f"{emoji} {loc}":
            return code
    return None

# =========================
# 4) Парсеры акций
# =========================

def parse_price_to_float(text: str) -> Optional[float]:
    if not text:
        return None
    m = re.findall(r"[\d]+[.,]\d+|[\d]+", text.replace(" ", ""))
    if not m:
        return None
    try:
        return float(m[0].replace(",", "."))
    except:
        return None

def offer_dict(name_pl: str, price: Optional[float], store: str, url: str = "", discount: Optional[float] = None) -> Dict[str, Any]:
    return {
        "name_pl": name_pl,
        "price": price,
        "store": store,
        "url": url,
        "discount": discount,
        "availability": True,
        "category": infer_category(name_pl or "")
    }

def infer_category(name_pl_lower: str) -> Optional[str]:
    n = name_pl_lower.lower()
    for code, (_, _ru, _pl, kw_ru, kw_pl) in CATEGORIES.items():
        if any(k in n for k in kw_pl) or any(k in n for k in kw_ru):
            return code
    return None

def fetch_promotions_leclerc() -> List[Dict[str, Any]]:
    url = "https://rzeszow.leclerc.pl/promocje"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
    except Exception:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    offers: List[Dict[str, Any]] = []
    cards = soup.select(".product-card, .product, .product-tile, .productBox")
    for card in cards:
        name_el = card.select_one(".product-name, .name, .title, .productTitle")
        price_el = card.select_one(".product-price, .price, .value, .productPrice")
        name = (name_el.get_text(strip=True) if name_el else "").lower()
        if not name:
            continue
        price = parse_price_to_float(price_el.get_text(strip=True)) if price_el else None
        offers.append(offer_dict(name_pl=name, price=price, store="Leclerc", url=url))
    return offers

def fetch_promotions_auchan() -> List[Dict[str, Any]]:
    url = "https://www.auchan.pl/pl/sklepy/auchan-rzeszow-krasne"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
    except Exception:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    offers: List[Dict[str, Any]] = []
    cards = soup.select(".product-tile, .product, .promo, .productBox")
    for card in cards:
        name_el = card.select_one(".product-name, .name, .title, .productTitle")
        price_el = card.select_one(".product-price, .price, .value, .productPrice")
        name = (name_el.get_text(strip=True) if name_el else "").lower()
        if not name:
            continue
        price = parse_price_to_float(price_el.get_text(strip=True)) if price_el else None
        offers.append(offer_dict(name_pl=name, price=price, store="Auchan", url=url))
    return offers

def fetch_promotions_lidl() -> List[Dict[str, Any]]:
    url = "https://www.lidl.pl/oferty"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
    except Exception:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    offers: List[Dict[str, Any]] = []
    cards = soup.select(".product-box, .product, .tile, .productBox")
    for card in cards:
        name_el = card.select_one(".product-title, .title, .name, .productTitle")
        price_el = card.select_one(".product-price, .price, .value, .productPrice")
        name = (name_el.get_text(strip=True) if name_el else "").lower()
        if not name:
            continue
        price = parse_price_to_float(price_el.get_text(strip=True)) if price_el else None
        offers.append(offer_dict(name_pl=name, price=price, store="Lidl", url=url))
    return offers

async def get_all_promotions_async() -> List[Dict[str, Any]]:
    results = await asyncio.gather(
        asyncio.to_thread(fetch_promotions_leclerc),
        asyncio.to_thread(fetch_promotions_auchan),
        asyncio.to_thread(fetch_promotions_lidl),
        return_exceptions=True
    )
    offers: List[Dict[str, Any]] = []
    for res in results:
        if isinstance(res, Exception):
            continue
        offers.extend(res)
    cleaned = []
    for o in offers:
        if not o.get("name_pl"):
            continue
        o["name_pl"] = o["name_pl"].strip().lower()
        cleaned.append(o)
    return cleaned

# =========================
# 5) Matching / Best offers
# =========================

def best_offers_for_items(items_ui: List[str], offers: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    items_pl = translate_list_to_pl(items_ui)
    results = []
    store_count = {}
    for ui, pl in zip(items_ui, items_pl):
        matched = [o for o in offers if pl in o["name_pl"]]
        if not matched:
            results.append({"ui": ui, "pl": pl, "found": False})
            continue
        best = sorted([m for m in matched if m["price"] is not None], key=lambda x: x["price"])[:1]
        if not best:
            results.append({"ui": ui, "pl": pl, "found": False})
            continue
        b = best[0]
        results.append({
            "ui": ui, "pl": pl, "found": True,
            "price": b["price"], "store": b["store"], "url": b.get("url", "")
        })
        store_count[b["store"]] = store_count.get(b["store"], 0) + 1

    recommendation = {}
    if store_count:
        best_store = max(store_count.items(), key=lambda kv: kv[1])[0]
        recommendation = {"best_store": best_store}
    return results, recommendation

def format_best_offers(lang: str, results: List[Dict[str, Any]], recommendation: Dict[str, Any]) -> str:
    lines = [UI[lang]["results_header"]]
    for r in results:
        if not r["found"]:
            lines.append(f"❌ {r['ui']} [ {r['pl']} ] — {UI[lang]['nothing_found']}")
        else:
            price = f"{r['price']:.2f} zł" if r['price'] else "Цена не указана"
            lines.append(f"✅ {r['ui']} — {price} ({r['store']}) [ {r['pl']} ]")
    if recommendation.get("best_store"):
        lines.append("")
        lines.append(UI[lang]["best_store_all"].format(store=recommendation["best_store"]))
    return "\n".join(lines)

def format_category_results(lang: str, offers: List[Dict[str, Any]]) -> str:
    """Форматировать результаты поиска по категориям"""
    lines = [f"🛍 {UI[lang]['results_header']}"]
    
    # Группируем по магазинам
    by_store = {}
    for offer in offers:
        store = offer.get("store", "Unknown")
        if store not in by_store:
            by_store[store] = []
        by_store[store].append(offer)
    
    for store, store_offers in by_store.items():
        lines.append(f"\n🏪 **{store}**:")
        for offer in store_offers[:5]:
            price = f"{offer['price']:.2f} zł" if offer.get('price') else "Цена не указана"
            lines.append(f"• {offer['name_pl']} — {price}")
    
    if len(offers) > 15:
        lines.append(f"\n📊 Показано {min(15, len(offers))} из {len(offers)} предложений")
    
    return "\n".join(lines)

# =========================
# 6) Меню и сценарии
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_db()
    user = update.effective_user
    ui_lang = lang_of(update)
    upsert_user(user.id, update.effective_chat.id, ui_lang, REGIONAL_SEARCH_LANG)
    await update.message.reply_text(t(ui_lang, "greet"), reply_markup=main_menu_kbd(ui_lang))
    await schedule_all_jobs(context.application)
    return MAIN_MENU

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ui_lang = get_ui_lang(update)
    await update.message.reply_text(UI[ui_lang]["help"], reply_markup=main_menu_kbd(ui_lang))
    return MAIN_MENU

# ---- 📝 Напиши список

async def write_list_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ui_lang = get_ui_lang(update)
    await update.message.reply_text(t(ui_lang, "send_list"))
    return ENTER_LIST

async def receive_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ui_lang = get_ui_lang(update)
    text = update.message.text or ""
    items_ui = normalize_items(text)
    if not items_ui:
        await update.message.reply_text(UI[ui_lang]["send_list"])
        return ENTER_LIST
    context.user_data["temp_items_ui"] = items_ui
    kbd = ReplyKeyboardMarkup([[UI[ui_lang]["best"]], [UI[ui_lang]["save"], UI[ui_lang]["delete"]]], resize_keyboard=True)
    await update.message.reply_text(t(ui_lang, "after_list"), reply_markup=kbd)
    return AFTER_LIST_ACTION

async def after_list_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ui_lang = get_ui_lang(update)
    choice = update.message.text.strip()
    if choice.startswith("🔍"):
        items_ui = context.user_data.get("temp_items_ui", [])
        offers = await get_all_promotions_async()
        results, rec = best_offers_for_items(items_ui, offers)
        context.user_data["temp_result_payload"] = {"type": "best_offers", "items_ui": items_ui, "results": results}
        await update.message.reply_text(
            format_best_offers(ui_lang, results, rec),
            reply_markup=ReplyKeyboardMarkup([[UI[ui_lang]["save"], UI[ui_lang]["delete"]]], resize_keyboard=True)
        )
        return CONFIRM_SAVE
    elif choice.startswith("💾"):
        await update.message.reply_text(UI[ui_lang]["enter_name"])
        context.user_data["save_payload"] = {"type": "list_raw", "items_ui": context.user_data.get("temp_items_ui", [])}
        return ENTER_LIST_NAME
    else:
        context.user_data.pop("temp_items_ui", None)
        context.user_data.pop("temp_result_payload", None)
        await update.message.reply_text(UI[ui_lang]["deleted"], reply_markup=main_menu_kbd(ui_lang))
        return MAIN_MENU

async def confirm_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ui_lang = get_ui_lang(update)
    if update.message.text.startswith("💾"):
        await update.message.reply_text(UI[ui_lang]["enter_name"])
        payload = context.user_data.get("temp_result_payload")
        if not payload:
            payload = {"type": "list_raw", "items_ui": context.user_data.get("temp_items_ui", [])}
        context.user_data["save_payload"] = payload
        return ENTER_LIST_NAME
    else:
        context.user_data.pop("temp_result_payload", None)
        await update.message.reply_text(UI[ui_lang]["deleted"], reply_markup=main_menu_kbd(ui_lang))
        return MAIN_MENU

async def save_list_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ui_lang = get_ui_lang(update)
    name = (update.message.text or "").strip()
    if not name:
        await update.message.reply_text(UI[ui_lang]["enter_name"])
        return ENTER_LIST_NAME
    
    payload = context.user_data.get("save_payload", {})
    items_ui: List[str] = []

    if payload.get("type") == "best_offers":
        items_ui = payload.get("items_ui", [])
    elif payload.get("type") == "list_raw":
        items_ui = payload.get("items_ui", [])
    elif payload.get("type") == "deals_list":
        items_ui = payload.get("items_ui", [])
    else:
        items_ui = context.user_data.get("temp_items_ui", [])

    user_id = update.effective_user.id
    list_id = add_list(user_id, name, items_ui, planned_for=None, status="active")
    context.user_data["last_saved_list"] = {"id": list_id, "name": name}

    await update.message.reply_text(
        t(ui_lang, "saved").format(name=name),
        reply_markup=ReplyKeyboardMarkup([[UI[ui_lang]["plan"], UI[ui_lang]["not_now"]]], resize_keyboard=True)
    )
    return PLAN_OR_NOT

async def plan_or_not(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ui_lang = get_ui_lang(update)
    txt = update.message.text.strip()
    last = context.user_data.get("last_saved_list", {})
    if txt.startswith("📅"):
        await update.message.reply_text(UI[ui_lang]["enter_date"])
        return ENTER_PLAN_DATETIME
    else:
        await update.message.reply_text(
            t(ui_lang, "saved_no_plan").format(name=last.get("name", "")),
            reply_markup=main_menu_kbd(ui_lang)
        )
        return MAIN_MENU

async def enter_plan_dt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ui_lang = get_ui_lang(update)
    dt_str = (update.message.text or "").strip()
    try:
        plan_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
    except ValueError:
        await update.message.reply_text(UI[ui_lang]["invalid_dt"])
        return ENTER_PLAN_DATETIME
    
    last = context.user_data.get("last_saved_list", {})
    if not last:
        await update.message.reply_text(UI[ui_lang]["invalid_dt"], reply_markup=main_menu_kbd(ui_lang))
        return MAIN_MENU
    
    update_list_plan(last["id"], plan_dt.strftime("%Y-%m-%d %H:%M"), "planned")
    await schedule_job_for_list(context.application, update.effective_user.id, last["id"], plan_dt)
    
    await update.message.reply_text(
        t(ui_lang, "plan_ok").format(name=last["name"], dt=dt_str),
        reply_markup=main_menu_kbd(ui_lang)
    )
    return MAIN_MENU

# ---- 📦 Поиск по категориям

async def categories_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ui_lang = get_ui_lang(update)
    context.user_data["picked_categories"] = set()
    await update.message.reply_text(UI[ui_lang]["pick_categories"], reply_markup=categories_kbd(ui_lang))
    return CATEGORIES_PICK

async def categories_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ui_lang = get_ui_lang(update)
    text = update.message.text.strip()
    if text == UI[ui_lang]["done"]:
        picked_codes = context.user_data.get("picked_categories", set())
        if not picked_codes:
            await update.message.reply_text("Пожалуйста, выберите хотя бы одну категорию.", reply_markup=categories_kbd(ui_lang))
            return CATEGORIES_PICK
        
        offers = await get_all_promotions_async()
        filtered_offers = [o for o in offers if o.get("category") in picked_codes]
        
        if not filtered_offers:
            await update.message.reply_text(UI[ui_lang]["nothing_found"], reply_markup=main_menu_kbd(ui_lang))
            return MAIN_MENU
        
        results_text = format_category_results(ui_lang, filtered_offers)
        context.user_data["temp_result_payload"] = {
            "type": "deals_list",
            "items_ui": [f"Акции {', '.join(picked_codes)}"],
            "results": filtered_offers
        }
        
        await update.message.reply_text(
            results_text,
            reply_markup=ReplyKeyboardMarkup([[UI[ui_lang]["save"], UI[ui_lang]["delete"]]], resize_keyboard=True)
        )
        return CONFIRM_SAVE
    else:
        code = parse_category_label_to_code(text, ui_lang)
        if code:
            picked = context.user_data.get("picked_categories", set())
            if code in picked:
                picked.remove(code)
            else:
                picked.add(code)
            context.user_data["picked_categories"] = picked
            
        await update.message.reply_text(UI[ui_lang]["pick_categories"], reply_markup=categories_kbd(ui_lang))
        return CATEGORIES_PICK

# ---- 🛍 Акции / Скидки

async def deals_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ui_lang = get_ui_lang(update)
    await update.message.reply_text("🔍 Ищу актуальные акции...")
    
    offers = await get_all_promotions_async()
    if not offers:
        await update.message.reply_text(UI[ui_lang]["nothing_found"], reply_markup=main_menu_kbd(ui_lang))
        return MAIN_MENU
    
    # Показываем топ-10 акций
    top_offers = sorted([o for o in offers if o.get("price")], key=lambda x: x["price"])[:10]
    results_text = format_category_results(ui_lang, top_offers)
    
    context.user_data["temp_result_payload"] = {
        "type": "deals_list",
        "items_ui": [f"Топ акций {datetime.now().strftime('%Y-%m-%d')}"],
        "results": top_offers
    }
    
    await update.message.reply_text(
        results_text,
        reply_markup=ReplyKeyboardMarkup([[UI[ui_lang]["save"], UI[ui_lang]["delete"]]], resize_keyboard=True)
    )
    return CONFIRM_SAVE

# ---- 📂 Списки

async def lists_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ui_lang = get_ui_lang(update)
    user_id = update.effective_user.id
    active_lists, planned_lists = get_user_lists(user_id)
    
    if not active_lists and not planned_lists:
        await update.message.reply_text(UI[ui_lang]["no_lists"], reply_markup=main_menu_kbd(ui_lang))
        return MAIN_MENU
    
    text = f"{UI[ui_lang]['lists_title']}\n\n"
    
    if active_lists:
        text += f"🛒 {UI[ui_lang]['active']}:\n"
        for lst in active_lists:
            text += f"• {lst['name']} ({len(json.loads(lst['items_json']))} items)\n"
    
    if planned_lists:
        text += f"\n📅 {UI[ui_lang]['planned']}:\n"
        for lst in planned_lists:
            planned_date = datetime.strptime(lst['planned_for'], "%Y-%m-%d %H:%M").strftime("%d.%m.%Y %H:%M")
            text += f"• {lst['name']} - {planned_date}\n"
    
    await update.message.reply_text(text, reply_markup=main_menu_kbd(ui_lang))
    return MAIN_MENU

# ---- 🌐 Сменить язык

async def change_lang_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ui_lang = get_ui_lang(update)
    await update.message.reply_text(UI[ui_lang]["lang_prompt"], reply_markup=lang_select_kbd())
    return LANG_SELECT

async def lang_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    if text == UI["ru"]["lang_ru"]:
        set_user_lang(user_id, "ru")
        lang_code = "ru"
    elif text == UI["pl"]["lang_pl"]:
        set_user_lang(user_id, "pl")
        lang_code = "pl"
    elif text == UI["en"]["lang_en"]:
        set_user_lang(user_id, "en")
        lang_code = "en"
    else:
        await update.message.reply_text("Неверный выбор языка.", reply_markup=main_menu_kbd(get_ui_lang(update)))
        return MAIN_MENU
    
    await update.message.reply_text(
        UI[lang_code]["lang_set"].format(lang=lang_code),
        reply_markup=main_menu_kbd(lang_code)
    )
    return MAIN_MENU

# ---- Напоминания и планировщик

async def schedule_all_jobs(application: Application):
    """Запланировать все напоминания о списках"""
    with db() as conn:
        planned_lists = conn.execute(
            "SELECT * FROM lists WHERE status = 'planned' AND planned_for > datetime('now')"
        ).fetchall()
        
        for list_row in planned_lists:
            planned_dt = datetime.strptime(list_row["planned_for"], "%Y-%m-%d %H:%M")
            await schedule_job_for_list(application, list_row["user_id"], list_row["id"], planned_dt)

async def schedule_job_for_list(application: Application, user_id: int, list_id: int, planned_dt: datetime):
    """Запланировать напоминание для конкретного списка"""
    job_queue = application.job_queue
    if job_queue:
        # Удаляем старые задания для этого списка
        current_jobs = job_queue.get_jobs_by_name(f"reminder_{list_id}")
        for job in current_jobs:
            job.schedule_removal()
        
        # Создаем новое задание
        job_queue.run_once(
            send_reminder_callback,
            planned_dt,
            data={"user_id": user_id, "list_id": list_id},
            name=f"reminder_{list_id}"
        )

async def send_reminder_callback(context: ContextTypes.DEFAULT_TYPE):
    """Отправка напоминания о запланированном списке"""
    job = context.job
    user_id = job.data["user_id"]
    list_id = job.data["list_id"]
    
    list_data = get_list_by_id(list_id)
    if not list_data:
        return
    
    user = get_user(user_id)
    if not user:
        return
    
    lang = user["lang_ui"]
    keyboard = ReplyKeyboardMarkup([
        [UI[lang]["yes_show"]],
        [UI[lang]["back"]]
    ], resize_keyboard=True)
    
    try:
        await context.bot.send_message(
            chat_id=user["chat_id"],
            text=UI[lang]["reminder"].format(name=list_data["name"]),
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Ошибка отправки напоминания: {e}")

# =========================
# 7) Главная функция
# =========================

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            MAIN_MENU: [
                MessageHandler(filters.Regex("^📝"), write_list_entry),
                MessageHandler(filters.Regex("^📦"), categories_entry),
                MessageHandler(filters.Regex("^🛍"), deals_entry),
                MessageHandler(filters.Regex("^📂"), lists_entry),
                MessageHandler(filters.Regex("^ℹ️"), help_command),
                MessageHandler(filters.Regex("^🌐"), change_lang_entry),
            ],
            ENTER_LIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_list)],
            AFTER_LIST_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, after_list_action)],
            CONFIRM_SAVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_save)],
            ENTER_LIST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_list_name)],
            PLAN_OR_NOT: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_or_not)],
            ENTER_PLAN_DATETIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_plan_dt)],
            CATEGORIES_PICK: [MessageHandler(filters.TEXT & ~filters.COMMAND, categories_pick)],
            LANG_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, lang_select)],
        },
        fallbacks=[CommandHandler('start', start)],
    )
    
    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == '__main__':
    main()