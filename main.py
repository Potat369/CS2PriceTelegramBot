import asyncio
import itertools
import logging
import os
import sqlite3
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

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
from fake_useragent import UserAgent


class ChatState(StatesGroup):
    weapon = State()
    skin = State()


db = sqlite3.connect(
    "db.sqlite3",
)
logger = logging.getLogger(__name__)
dp = Dispatcher()

headers = {
    "User-Agent": UserAgent().random,
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
    "Assault Rifles": ["AK-47", "M4A1-S", "M4A4", "AUG", "FAMAS", "Galil AR", "SG 553"],
    "Sniper Rifles": ["AWP", "G3SG1", "SCAR-20", "SSG 08"],
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
    "SMGs": ["MAC-10", "MP5-SD", "MP7", "MP9", "PP-Bizon", "UMP-45"],
    "Shotguns": ["MAG-7", "Nova", "Sawed-Off", "XM1014"],
    "Machine Guns": ["M249", "Negev"],
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
    return (
        string.lower()
        .replace(" ", "-")
        .translate(str.maketrans("", "", string.punctuation))
    )


async def run_after(seconds, function, *args):
    await asyncio.sleep(seconds)
    await function(args)


async def update_skins(last_update_file: Path):
    logger.info("Started updating skins")
    pages_to_parse = []
    skins_to_add = []
    for category in weapon_categories:
        for weapon in weapon_categories[category]:
            url = f"https://csgoskins.gg/weapons/{to_url(weapon)}"

            main_page_res = requests.get(url, headers=headers)
            await asyncio.sleep(0.5)
            logger.debug(f"{main_page_res.status_code} {url}")

            if main_page_res.status_code is not requests.codes.ok:
                continue

            main_page = main_page_res.text
            pages_to_parse.append(main_page)
            main_page_soup = BeautifulSoup(main_page, "html.parser")

            pages_element = main_page_soup.find("div", class_="w-full mt-8 p-4")
            if pages_element != None:
                numbers_container = pages_element.find(
                    "div", class_="text-sm text-gray-400"
                )
                number_spans = numbers_container.find_all("span")
                for number_span in number_spans:
                    number = number_span.text
                    if number == "1":
                        continue
                    page_url = f"{url}?page={number}"
                    page_res = requests.get(page_url, headers=headers)

                    await asyncio.sleep(0.5)

                    logger.debug(f"{page_res.status_code} {page_url}")

                    if page_res.status_code is requests.codes.ok:
                        pages_to_parse.append(page_res.text)

            for page in pages_to_parse:
                page_soup = BeautifulSoup(page, "html.parser")
                skin_containers = page_soup.find_all(
                    "div",
                    class_="w-full sm:w-1/2 md:w-1/2 lg:w-1/3 xl:w-1/3 2xl:w-1/4 p-4 flex-none",
                )
                for skin_container in skin_containers:
                    skin_title = skin_container.find(
                        "span", class_="block text-lg leading-6 truncate mt-3"
                    )
                    skin_image = skin_container.find("img")
                    skins_to_add.append((skin_title.text, skin_image["src"]))

            db.executemany(
                f"INSERT INTO {to_db_name(weapon)}(skin_name, image_url) VALUES(?, ?) ON CONFLICT(skin_name) DO NOTHING;",
                skins_to_add,
            )
            db.commit()
            pages_to_parse = []
            skins_to_add = []
    last_update_file.write_text(datetime.now().strftime("%d-%b-%Y (%H:%M:%S.%f)"))
    logger.info("Finished updating skins")
    asyncio.create_task(run_after(43200, update_skins, last_update_file))


async def schedule_skins_update():
    data_dir = Path(appdirs.user_data_dir("CS2PriceBot", os.getlogin()))
    if not data_dir.exists():
        os.makedirs(data_dir)

    last_update_file = data_dir / "last_update"
    if last_update_file.is_file():
        time = datetime.strptime(last_update_file.read_text(), "%d-%b-%Y (%H:%M:%S.%f)")
        time_diff = datetime.now() - time
        if time_diff < timedelta(hours=12):
            time_before_next_run = (timedelta(hours=12) - time_diff).total_seconds()
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
        name, image_url, last_update, *prices = data
        await message.answer_photo(
            photo=image_url,
            caption=f"🎯 {weapon} | {skin}\n💰 Current prices for this item: {0} -- {1}.\n",
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
    # Warnings
    warnings.filterwarnings("ignore", category=RuntimeWarning)

    # Logger
    stdout_handler = logging.StreamHandler(stream=sys.stdout)
    fmt = logging.Formatter(
        "[%(asctime)s] [%(filename)s:%(lineno)s/%(levelname)s]: %(message)s"
    )

    stdout_handler.setFormatter(fmt)
    logger.addHandler(stdout_handler)
    logger.setLevel(logging.DEBUG)

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
                    last_update TIMESTAMP,
                    factory_new_price REAL,
                    minimal_wear_price REAL,
                    field_tested_price REAL,
                    well_worn_price REAL,
                    battle_scarred_price REAL
                )
                """
            )
    db.commit()

    # Schedule update
    await schedule_skins_update()
    logger.info("Starting bot")
    bot = Bot(token=TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
