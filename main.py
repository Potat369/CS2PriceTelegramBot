import asyncio
import itertools
import logging
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import appdirs
import dotenv
import requests
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import BaseStorage
from aiogram.types import (
    InlineKeyboardMarkup,
    InputFile,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import (
    InlineKeyboardBuilder,
    KeyboardBuilder,
    ReplyKeyboardBuilder,
)
from bs4 import BeautifulSoup


class ChatState(StatesGroup):
    weapon = State()
    skin = State()


SECONDS_BETWEEN_SCRAPES = 600
db = sqlite3.connect("db.sqlite3")
logger = logging.getLogger(__name__)
dp = Dispatcher()
datetime_format = "%d-%b-%Y (%H:%M:%S.%f)"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "accept-encoding": "gzip, deflate",
}

weapon_categories = {
    "Knifes": [
        "Bayonet",
        "Bowie Knife",
        "Butterfly Knife",
        "Classic Knife",
        "Falchion Knife",
        "Flip Knife",
        "Gut Knife",
        "Huntsman Knife",
        "Karambit",
        "Kukri Knife",
        "M9 Bayonet",
        "Navaja Knife",
        "Nomad Knife",
        "Paracord Knife",
        "Shadow Daggers",
        "Skeleton Knife",
        "Stiletto Knife",
        "Talon Knife",
        "Ursus Knife",
    ],
    "Gloves": [
        "Bloodhound Gloves",
        "Broken Fang Gloves",
        "Driver Gloves",
        "Hand Wraps",
        "Hydra Gloves",
        "Moto Gloves",
        "Specialist Gloves",
        "Sport Gloves",
    ],
    "Assault Rifles": [
        "AK-47",
        "M4A1-S",
        "M4A4",
        "AUG",
        "FAMAS",
        "Galil AR",
        "SG 553",
    ],
    "Sniper Rifles": [
        "AWP",
        "G3SG1",
        "SCAR-20",
        "SSG 08",
    ],
    "Pistols": [
        "CZ75-Auto",
        "Desert Eagle",
        "Dual Berettas",
        "Five-SeveN",
        "Glock-18",
        "P2000",
        "P250",
        "R8 Revolver",
        "Tec-9",
        "USP-S",
        "Zeus x27",
    ],
    "SMGs": [
        "MAC-10",
        "MP5-SD",
        "MP7",
        "MP9",
        "PP-Bizon",
        "UMP-45",
    ],
    "Shotguns": [
        "MAG-7",
        "Nova",
        "Sawed-Off",
        "XM1014",
    ],
    "Machine Guns": [
        "M249",
        "Negev",
    ],
}

weapons = list(itertools.chain.from_iterable(weapon_categories.values()))


def create_keyboard(
    items: List[str], text: str, last_choice: str | None = None
) -> ReplyKeyboardMarkup:
    length = len(items)
    buttons = []

    for i in range(0, length - 1, 2):
        buttons.append(
            [KeyboardButton(text=items[i]), KeyboardButton(text=items[i + 1])]
        )

    if length % 2 == 1:
        buttons.append([KeyboardButton(text=items[-1])])

    if last_choice is not None:
        buttons.append([KeyboardButton(text=last_choice)])

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=False,
        input_field_placeholder=text,
    )


category_kb = create_keyboard(
    list(weapon_categories.keys()), "Choose a category", "Contacts"
)


def to_db_name(string: str) -> str:
    return string.lower().replace(" ", "_").replace("-", "_")


def to_url(string: str) -> str:
    return "".join(re.findall("[a-z|0-9|-]+", string.lower().replace(" ", "-")))


def price_to_float(price: Optional[str]) -> Optional[float]:
    if price == None:
        return None
    return price.strip().replace(",", "")[1:]


async def run_after(seconds, function, *args):
    await asyncio.sleep(seconds)
    await function(*args)


async def update_skins(last_update_file: Path):
    logger.info("Started updating skins")
    pages_to_parse = []
    skins_to_add = []
    for category in weapon_categories:
        for weapon in weapon_categories[category]:
            url = f"https://csgoskins.gg/weapons/{to_url(weapon)}"

            main_page_res = requests.get(url, headers=headers, stream=True)
            await asyncio.sleep(0.5)
            logger.debug(f"{main_page_res.status_code} {url}")

            if main_page_res.status_code is not requests.codes.ok:
                logger.error(f"Failed to parse: {main_page_res.status_code}")
                return

            main_page = main_page_res.text
            pages_to_parse.append(main_page)
            main_page_soup = BeautifulSoup(main_page, "html.parser")

            pages_container = main_page_soup.select_one("div.w-full.mt-8.p-4")
            if pages_container != None:
                pages = pages_container.select_one(
                    "div.text-sm.text-gray-400 > span:nth-child(2)"
                )
                for number in range(2, int(pages.text) + 1):
                    page_url = f"{url}?page={number}"
                    page_res = requests.get(page_url, headers=headers, stream=True)

                    await asyncio.sleep(0.5)

                    logger.debug(f"{page_res.status_code} {page_url}")

                    if page_res.status_code is requests.codes.ok:
                        pages_to_parse.append(page_res.text)
                    else:
                        logger.error(f"Failed to parse: {page_res.status_code}")
                        return

            for page in pages_to_parse:
                page_soup = BeautifulSoup(page, "html.parser")

                skin_containers = page_soup.select("div.flex-none.w-full")
                for skin_container in skin_containers:
                    skin_title = skin_container.select_one("span.block.text-lg").text
                    skin_image = skin_container.select_one("img")["src"]
                    skin_prices = skin_container.select("div.top-\\[395px\\] > a")
                    skins_to_add.append(
                        (
                            skin_title,
                            skin_image,
                            price_to_float(
                                skin_prices[0].text if len(skin_prices) >= 1 else None
                            ),
                            price_to_float(
                                skin_prices[1].text if len(skin_prices) >= 2 else None
                            ),
                        )
                    )

            db.executemany(
                f"INSERT INTO {to_db_name(weapon)}(skin_name, image_url, min_price, max_price) VALUES(?, ?, ?, ?) ON CONFLICT(skin_name) DO UPDATE SET min_price = excluded.min_price, max_price = excluded.max_price;",
                skins_to_add,
            )
            db.commit()
            pages_to_parse = []
            skins_to_add = []
    last_update_file.write_text(datetime.now().strftime(datetime_format))
    logger.info("Finished updating skins")
    asyncio.create_task(
        run_after(SECONDS_BETWEEN_SCRAPES, update_skins, last_update_file)
    )


async def schedule_skins_update():
    """Schedules update for skins

    If last_update file is not found assuming first-run and waiting until all skins are parsed
    """

    data_dir = Path(appdirs.user_data_dir("CS2PriceBot", os.getlogin()))
    data_dir.mkdir(parents=True, exist_ok=True)

    last_update_file = data_dir / "last_update"
    if last_update_file.is_file():
        time = datetime.strptime(last_update_file.read_text(), datetime_format)
        time_diff = datetime.now() - time
        if time_diff < timedelta(seconds=SECONDS_BETWEEN_SCRAPES):
            time_before_next_run = (
                timedelta(seconds=SECONDS_BETWEEN_SCRAPES) - time_diff
            ).total_seconds()
            asyncio.create_task(
                run_after(time_before_next_run, update_skins, last_update_file)
            )
        else:
            asyncio.create_task(update_skins(last_update_file))
    else:
        await update_skins(last_update_file)


@dp.message(CommandStart())
async def start_command_handler(message, state):
    await state.clear()
    await message.answer(
        text="Hello",
        reply_markup=category_kb,
    )


@dp.message(F.text == "Main Menu")
async def main_menu_handler(message, state):
    await state.clear()
    await message.answer(text="Main Menu", reply_markup=category_kb)


@dp.message(F.text == "Contacts")
async def contacts_handler(message):
    await message.answer(text="Bot was created by @potat369")


@dp.message(
    ChatState.weapon,
    F.text.in_(weapons),
)
async def weapon_handler(message, state):
    weapon = message.text
    await state.set_state(ChatState.skin)
    await state.update_data(weapon=weapon)

    res = db.execute(f"SELECT (skin_name) FROM {to_db_name(weapon)};")
    skins = res.fetchall()
    await message.answer(
        text=f"Select a skin for {weapon}",
        reply_markup=create_keyboard(
            [skin[0] for skin in skins],
            "Choose a skin",
            "Main Menu",
        ),
    )


@dp.message(ChatState.weapon)
async def unknown_weapon_handler(message):
    await message.answer(text="Unknown weapon")


@dp.message(ChatState.skin)
async def skin_handler(message, state):
    skin = message.text
    data = await state.get_data()
    weapon = data.get("weapon")

    res = db.execute(
        f"SELECT * FROM {to_db_name(weapon)} WHERE skin_name = ?;", (skin,)
    )
    data = res.fetchone()
    if data == None:
        await message.answer(text="Unknown skin")
    else:
        item_name, image_url, min_price, max_price = data
        if min_price != None and max_price != None:
            await message.answer_photo(
                photo=image_url,
                caption=f"🎯 {weapon} | {skin}\n💰 Current prices for this item: ${min_price:.2f} -- ${max_price:.2f}",
            )
        elif min_price != None:
            await message.answer_photo(
                photo=image_url,
                caption=f"🎯 {weapon} | {skin}\n💰 Current price for this item: ${min_price:.2f}",
            )
        else:
            await message.answer_photo(
                photo=image_url,
                caption=f"🎯 {weapon} | {skin}\n💰 No price data",
            )


@dp.message(F.text.in_(weapon_categories.keys()))
async def category_handler(message, state):
    category = message.text
    await state.set_state(ChatState.weapon)

    await message.answer(
        text=f'Select a weapon in category "{category}"',
        reply_markup=create_keyboard(
            weapon_categories[category], "Choose a weapon", "Main Menu"
        ),
    )


@dp.message()
async def unknown_category_handler(message):
    await message.answer(text="Unknown category")


async def main():
    # Logger
    logger.setLevel(logging.DEBUG)

    log_dir = Path(appdirs.user_log_dir("CS2PriceBot", os.getlogin()))
    log_dir.mkdir(parents=True, exist_ok=True)

    stdout_handler = logging.StreamHandler(stream=sys.stdout)
    file_handler = logging.FileHandler("latest.log")

    fmt = logging.Formatter(
        "[%(asctime)s] [%(filename)s:%(lineno)s/%(levelname)s]: %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    stdout_handler.setLevel(logging.INFO)
    file_handler.setLevel(logging.DEBUG)

    stdout_handler.setFormatter(fmt)
    file_handler.setFormatter(fmt)

    logger.addHandler(stdout_handler)
    logger.addHandler(file_handler)

    # Env
    dotenv.load_dotenv()
    TOKEN = os.getenv("TOKEN")
    if TOKEN == None:
        logger.critical("TOKEN was not found")
        return

    # DB
    db.execute("PRAGMA journal_mode = WAL;")
    for category in weapon_categories:
        for weapon in weapon_categories[category]:
            db.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {to_db_name(weapon)} (
                    skin_name STRING PRIMARY KEY,
                    image_url STRING,
                    min_price REAL,
                    max_price REAL
                )
                """
            )
    db.commit()

    # Schedule update
    await schedule_skins_update()

    # Bot
    logger.info("Starting bot")
    bot = Bot(token=TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
