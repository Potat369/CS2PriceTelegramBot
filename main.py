import os
import sqlite3

import dotenv
import requests
from bs4 import BeautifulSoup

weapon_groups = {"Assault Rifles": ["AK-47", "M4A1-S", "M4A4"]}
db = sqlite3.connect("db.sqlite3")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.2210.91"
}


def to_db_name(string: str) -> str:
    return string.lower().replace(" ", "_").replace("-", "_")


def to_url(string: str) -> str:
    return string.lower().replace(" ", "-")


def update_skins():
    pages_to_parse = []
    skins_to_add = []
    for group in weapon_groups:
        for weapon in weapon_groups[group]:
            url = f"https://csgoskins.gg/weapons/{to_url(weapon)}"

            main_page_res = requests.get(url, headers=headers)

            if main_page_res.status_code is not requests.codes.ok:
                return

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
                    page_res = requests.get(f"{url}?page={number}", headers=headers)

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
                    skins_to_add.append(skin_title.text)

            db.executemany(
                f"INSERT INTO {to_db_name(weapon)}(skin_name) VALUES(?) ON CONFLICT(skin_name) DO NOTHING;",
                [(skin,) for skin in skins_to_add],
            )
            db.commit()
            pages_to_parse = []
            skins_to_add = []


def update_price(weapon: str, skin: str):
    pass


def main():
    dotenv.load_dotenv()
    TOKEN = os.getenv("TOKEN")
    if TOKEN == None:
        print("Token not found")
        return
    db.execute("PRAGMA journal_mode = WAL;")
    for group in weapon_groups:
        for weapon in weapon_groups[group]:
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
                    battle_scarred_price REAL,
                    stattrack_factory_new_price REAL,
                    stattrack_minimal_wear_price REAL,
                    stattrack_field_tested_price REAL,
                    stattrack_well_worn_price REAL,
                    stattrack_battle_scarred_price REAL
                )
                """
            )
    db.commit()
    update_skins()
    update_price()


if __name__ == "__main__":
    main()
