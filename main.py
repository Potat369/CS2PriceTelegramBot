import asyncio
import itertools
import logging
import os
import sqlite3
import sys
from typing import List

import dotenv
import requests
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
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

dp = Dispatcher()
session = requests.Session()

weapon_categories = {
    "Knifes": [
        "Bayonet",
        "Bowie Knife",
        "Butterfly Knife",
        "Classic Knife",
        "Falchon Knife",
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
        "Dual Barettas",
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
    return string.lower().replace(" ", "-")


def update_skins():
    pages_to_parse = []
    skins_to_add = []
    for category in weapon_categories:
        for weapon in weapon_categories[category]:
            url = f"https://csgoskins.gg/weapons/{to_url(weapon)}"

            main_page_res = session.get(url)
            print(main_page_res.status_code)

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
                    page_res = session.get(f"{url}?page={number}")

                    if page_res.status_code is requests.codes.ok:
                        pages_to_parse.append(page_res.text)

            for page in pages_to_parse:
                page_soup = BeautifulSoup(page, "html.parser")
                skin_containers = page_soup.find_all(
                    "div",
                    class_="w-full sm:w-1/2 md:w-1/2 lg:w-1/3 xl:w-1/3 2xl:w-1/4 p-4 flex-none",
                )
                for skin_container in skin_containers:
                    print(skin_container)
                    skin_title = skin_container.find(
                        "span", class_="block text-lg leading-6 truncate mt-3"
                    )
                    skin_image = skin_container.find("img")
                    skins_to_add.append((skin_title, skin_image))

            db.executemany(
                f"INSERT INTO {to_db_name(weapon)}(skin_name, image_url) VALUES(?, ?) ON CONFLICT(skin_name) DO NOTHING;",
                skins_to_add,
            )
            pages_to_parse = []
            skins_to_add = []


def update_price(weapon: str, skin: str):
    pass


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
    print(list(itertools.chain.from_iterable(weapon_categories.values())))
    await message.answer(text="Unknown weapon")


@dp.message(ChatState.skin)
async def skin_handler(message, state):
    skin = message.text
    data = await state.get_data()
    weapon = data.get("weapon")

    res = db.execute(
        f"SELECT * FROM {to_db_name(weapon)} WHERE skin_name = ?;", (skin,)
    )
    if res == None:
        await message.answer(text="Unknown skin")
    else:
        pass


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
    # Session
    session.headers.update(
        {
            "User-Agent": UserAgent().random,
        }
    )

    # Env
    dotenv.load_dotenv()
    TOKEN = os.getenv("TOKEN")
    if TOKEN == None:
        print("TOKEN not found")
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
    # Bot
    db.commit()
    update_skins()

    bot = Bot(token=TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
