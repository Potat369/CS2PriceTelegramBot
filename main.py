from os import getenv

from dotenv import load_dotenv


def main():
    load_dotenv()
    TOKEN = getenv("TOKEN")
    if TOKEN == None:
        print("Token not found")
        return


if __name__ == "__main__":
    main()
