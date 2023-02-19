"""
rarbgapi - RARBG command line interface for scraping the rarbg.to torrent search engine
                  Outputs a torrent magnet.
"""
import argparse
import asyncio
import datetime
import json
import logging
import os
import re
import sys
from sys import platform
import time
import zipfile
from functools import partial
from http.cookies import SimpleCookie
from pathlib import Path

import requests
import wget
from bs4 import BeautifulSoup
import ref_rarbgapi as ref
from requests.utils import quote
from tqdm import tqdm

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')

# Configure local directory
HOME_DIRECTORY = os.environ.get("RARBGAPI_HOME", str(Path.home()))
logging.debug("HOME_DIRECTORY: %s", HOME_DIRECTORY)
PROGRAM_HOME = os.path.join(HOME_DIRECTORY, ".rarbgapi")
os.makedirs(PROGRAM_HOME, exist_ok=True)
logging.debug("PROGRAM_HOME: %s", PROGRAM_HOME)
COOKIES_PATH = os.path.join(PROGRAM_HOME, "cookies.json")
logging.debug("COOKIES_PATH: %s", COOKIES_PATH)


def get_args():
    """Function to get arguments"""
    orderkeys = ["data", "filename", "leechers", "seeders", "size", ""]
    sortkeys = ["title", "date", "size", "seeders", "leechers", ""]
    parser = argparse.ArgumentParser(
        __doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("search",
                        help="Search term")
    parser.add_argument("--category", "-c",
                        choices=ref.CATEGORY2CODE.keys(),
                        default="")
    parser.add_argument("--limit", "-l",
                        type=int,
                        default="inf",
                        help="Limit number of torrent magnet links")
    parser.add_argument("--domain",
                        default="rarbgunblocked.org",
                        help="Domain to search, you could put an alternative mirror domain here")
    parser.add_argument("--order", "-r",
                        choices=orderkeys,
                        default="data",
                        help="Order results (before query) by this key. empty string means no sort")
    parser.add_argument("--descending",
                        action="store_true",
                        help="Order in descending order (only available for --order)")
    parser.add_argument("--interactive", "-i",
                        action="store_true",
                        default=None,
                        help="Force interactive mode, show interctive menu of torrents")
    parser.add_argument("--download_torrents", "-d",
                        action="store_true",
                        default=None,
                        help="Open torrent files in browser (which will download them)"
                        )
    parser.add_argument("--magnet", "-m",
                        action="store_true",
                        help="Output magnet links")
    parser.add_argument("--sort", "-s",
                        choices=sortkeys,
                        default="",
                        help="Sort results (after scraping) by this key. empty string means no sort")
    parser.add_argument("--block_size", "-B",
                        type=lambda x: x.upper(),
                        metavar="SIZE",
                        default=None,
                        choices=list(ref.SIZE_UNITS.keys()),
                        help="Display torrent sizes in SIZE unit. Choices are: " +
                        str(set(list(ref.SIZE_UNITS.keys()))),
                        )
    parser.add_argument("--no_cache", "-nc", action="store_true",
                        help="Don't use cached results from previous searches")
    parser.add_argument("--no_cookie", "-nk",
                        action="store_true",
                        help="Don't use CAPTCHA cookie from previous runs (will need to resolve a new CAPTCHA)")
    args = parser.parse_args()

    # if args.interactive is None:
        # args.interactive = sys.stdout.isatty()  # automatically decide based on if tty

    if not args.limit >= 1:
        print("--limit must be greater than 1", file=sys.stderr)
        exit(1)
    if args.descending and not args.order:
        print("--descending requires --order", file=sys.stderr)
        exit(1)
    return args

def get_user_input_interactive(torrent_dicts):
    header = " ".join(["SN".ljust(4), "TORRENT NAME".ljust(80), "SEEDS".ljust(6), "LEECHES".ljust(6), "SIZE".center(12), "UPLOADER"])
    choices = []
    for i in range(len(torrent_dicts)):
        torrent_name = str(torrent_dicts[i]["title"])
        torrent_size = str(torrent_dicts[i]["size"])
        torrent_seeds = str(torrent_dicts[i]["seeders"])
        torrent_leeches = str(torrent_dicts[i]["leechers"])
        torrent_uploader = str(torrent_dicts[i]["uploader"])
        choices.append(
            {
                "value": int(i),
                "name": " ".join(
                    [
                        str(i + 1).ljust(4),
                        torrent_name.ljust(80),
                        torrent_seeds.ljust(6),
                        torrent_leeches.ljust(6),
                        torrent_size.center(12),
                        torrent_uploader,
                    ]
                ),
            }
        )
    choices.append({"value": "next", "name": "next page >>"})

    from prompt_toolkit import styles
    import questionary

    prompt_style = styles.Style(
        [
            ("qmark", "fg:#5F819D bold"),
            ("question", "fg:#289c64 bold"),
            ("answer", "fg:#48b5b5 bold"),
            ("pointer", "fg:#48b5b5 bold"),
            ("highlighted", "fg:#07d1e8"),
            ("selected", "fg:#48b5b5 bold"),
            ("separator", "fg:#6C6C6C"),
            ("instruction", "fg:#77a371"),
            ("text", ""),
            ("disabled", "fg:#858585 italic"),
        ]
    )
    answer = questionary.select(header + "\nSelect torrents", choices=choices, style=prompt_style).ask()
    return answer

def args_to_fname(args):
    """Function that sanitizes args into a filename"""
    # copy and sanitize
    args_list = {"limit", "category", "order", "search", "descending"}
    args_dict = {k: str(v).replace('"', "").replace(",", "") for k, v in sorted(vars(args).items()) if k in args_list}
    filename = json.dumps(args_dict, indent=None, separators=(",", "="), ensure_ascii=False)[1:-1].replace('"', "")
    return filename

def download_tesseract(chdir="."):
    os.chdir(chdir)

    # download for each platform if statement
    if platform == "win32":
        tesseract_zip = wget.download("https://github.com/FarisHijazi/rarbgcli/releases/download/v0.0.7/Tesseract-OCR.zip", "Tesseract-OCR.zip")
        # extract the zip file
        with zipfile.ZipFile(tesseract_zip, "r") as zip_ref:
            zip_ref.extractall()  # you can specify the destination folder path here
        # delete the zip file downloaded above
        os.remove(tesseract_zip)
    elif platform in ["linux", "linux2"]:
        os.system("sudo apt-get install tesseract-ocr")
    elif platform == "posix":
        # TODO: Ensure system has brew installed
        os.system("brew install tesseract")
    else:
        raise SystemError("Unsupported platform")

def cookies_txt_to_dict(cookies_txt: str) -> dict:
    # SimpleCookie.load = lambda self, data: self.__init__(data.split(';'))
    cookie = SimpleCookie()
    cookie.load(cookies_txt)
    return {k: v.value for k, v in cookie.items()}

def cookies_dict_to_txt(cookies_dict: dict) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies_dict.items())

def parse_size(size: str):
    number, unit = [string.strip() for string in size.strip().split()]
    return int(float(number) * ref.SIZE_UNITS[unit])


def format_size(size: int, block_size=None):
    """automatically format the size to the most appropriate unit"""
    if block_size is None:
        for unit in reversed(list(ref.SIZE_UNITS.keys())):
            if size >= ref.SIZE_UNITS[unit]:
                return f"{size / ref.SIZE_UNITS[unit]:.2f} {unit}"
    else:
        return f"{size / ref.SIZE_UNITS[block_size]:.2f} {block_size}"

def unique_dicts(dicts):
    seen = set()
    deduped = []
    for dictionary in dicts:
        values_tuple = tuple(dictionary.items())
        if values_tuple not in seen:
            seen.add(values_tuple)
            deduped.append(dictionary)
    return deduped

def solveCaptcha(threat_defence_url):
    
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager

    import pytesseract
    from PIL import Image
    from io import BytesIO

    def img2txt():
        logging.info("Attempting Img2Txt Conversion")
        try:
            clk_here_button = driver.find_element_by_link_text("Click here")
            clk_here_button.click()
            time.sleep(10)
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "solve_string")))
        except Exception as img2txt_e:
            logging.error("Error while img2txt: %s", img2txt_e)
        finally:
            element = driver.find_elements_by_css_selector("img")[1]
            location = element.location
            size = element.size
            png = driver.get_screenshot_as_png()
            x = location["x"]
            y = location["y"]
            width = location["x"] + size["width"]
            height = location["y"] + size["height"]
            im = Image.open(BytesIO(png))
            im = im.crop((int(x), int(y), int(width), int(height)))
            logging.info("Returning Img2Txt")
            return pytesseract.image_to_string(im)

    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--headless")
    options.add_argument("--log-level=3")
    options.add_argument("--disable-logging")
    options.add_argument("--output=" + ("NUL" if sys.platform == "win32" else "/dev/null"))

    driver = webdriver.Chrome(ChromeDriverManager(
        path=PROGRAM_HOME).install(), 
        options=options, 
        service_log_path=("NUL" if sys.platform == "win32" else "/dev/null"))
    
    logging.debug("Successfully loaded chrome driver")
    driver.implicitly_wait(10)
    driver.get(threat_defence_url)

    if platform == "win32":
        pytesseract.pytesseract.tesseract_cmd = os.path.join(PROGRAM_HOME, "Tesseract-OCR", "tesseract")
    try:
        solution = img2txt()
    except pytesseract.TesseractNotFoundError:
        logging.warning("Tesseract not found. Attempting to download tesseract ...")
        download_tesseract(PROGRAM_HOME)
        solution = img2txt()

    text_field = driver.find_element_by_id("solve_string")
    text_field.send_keys(solution)
    try:
        text_field.send_keys(Keys.RETURN)
    except Exception as submit_solution_e:
        print(submit_solution_e)

    time.sleep(3)
    cookies = {c["name"]: c["value"] for c in (driver.get_cookies())}
    driver.close()
    return cookies

def deal_with_threat_defence_manual(threat_defence_url):
    logging.warning(
        f"""
    rarbg CAPTCHA must be solved, please follow the instructions bellow (only needs to be done once in a while):

    1. On any PC, open the link in a web browser: "{threat_defence_url}"
    2. solve and submit the CAPTCHA you should be redirected to a torrent page
    3. open the console (press F12 -> Console) and paste the following code:

        console.log(document.cookie)

    4. copy the output. it will look something like: "tcc; gaDts48g=q8hppt; gaDts48g=q85p9t; ...."
    5. paste the output in the terminal here

    >>>
    """
    )
    cookies = input().strip().strip("'").strip('"')
    cookies = cookies_txt_to_dict(cookies)

    return cookies

def deal_with_threat_defence(threat_defence_url):
    try:
        return solveCaptcha(threat_defence_url)
    except Exception as captcha_exeption:
        logging.warning("CAPTCHA solver failed")
        if not sys.stdout.isatty():
            raise RuntimeWarning (
                "Failed to solve captcha automatically, please rerun this command (without a pipe `|`) and solve it manually. This process only needs to be done once"
            ) from captcha_exeption

        print("Failed to solve captcha, please solve manually", captcha_exeption)
        return deal_with_threat_defence_manual(threat_defence_url)

def load_cookies(no_cookie):
    """Function that checks if cookie exists and returns it"""
    # read cookies from json file
    cookies = {}
    # make empty cookie if cookie doesn't already exist
    if not os.path.exists(COOKIES_PATH):
        with open(COOKIES_PATH, "w", encoding="UTF-8") as cookie_json:
            json.dump({}, cookie_json)

    if not no_cookie:
        with open(COOKIES_PATH, "r", encoding="UTF-8") as cookie_json:
            cookies = json.load(cookie_json)
    return cookies

def get_page_html(target_url, cookies):
    while True:
        response = requests.get(target_url, headers=ref.DEFAULT_HEADER, cookies=cookies)
        logging.info("Opening page: %s", response.url)
        if "threat_defence.php" not in response.url:
            logging.debug("Defence not detected")
            break
        logging.info("Defence detected")
        cookies = deal_with_threat_defence(response.url)
        # save cookies to json file
        with open(COOKIES_PATH, "w") as f:
            json.dump(cookies, f)

    data = response.text.encode("utf-8")
    return response, data, cookies

def open_url(url):
    if platform == "win32":
        os.startfile(url)
    elif platform in ["linux", "linux2"]:
        os.system("xdg-open " + url)
    # TODO: Update check macOS conditions for posix
    else:  # if mac os
        os.system("open " + url)

def extract_torrent_file(anchor, domain="rarbgunblocked.org"):
    return (
        "https://"
        + domain
        + anchor.get("href").replace("torrent/", "download.php?id=")
        + "&f="
        + quote(anchor.contents[0] + "-[rarbg.to].torrent")
        + "&tpageurl="
        + quote(anchor.get("href").strip())
    )
        
async def open_torrentfiles(urls):
    for url in tqdm(urls, "downloading", total=len(urls)):
        open_url(url)
        if len(urls) > 5:
            await asyncio.sleep(0.5)


def extract_magnet(anchor):
    # real:
    #     https://rarbgaccess.org/download.php?id=...&h=120&f=...-[rarbg.to].torrent
    #     https://rarbgaccess.org/download.php?id=...&      f=...-[rarbg.com].torrent
    # https://www.rarbgaccess.org/download.php?id=...&h=120&f=...-[rarbg.to].torrent
    # matches anything containing "over/*.jpg" *: anything
    regex = r"over\/(.*)\.jpg\\"
    trackers = "http%3A%2F%2Ftracker.trackerfix.com%3A80%2Fannounce&tr=udp%3A%2F%2F9.rarbg.me%3A2710&tr=udp%3A%2F%2F9.rarbg.to%3A2710"
    try:
        hash = re.search(regex, str(anchor))[1]
        title = quote(anchor.get("title"))
        return f"magnet:?xt=urn:btih:{hash}&dn={title}&tr={trackers}"
    except Exception:
        return ""

def search_for_torrent(search,
    category="",
    download_torrents=None,
    limit=float("inf"),
    domain="rarbgunblocked.org",
    order="",
    descending=False,
    interactive=False,
    magnet=False,
    sort="",
    no_cache=False,
    no_cookie=False,
    block_size="auto",
    _session_name="untitled",  # unique name based on args, used for caching
):
    """Function that gets torrent based on arguments"""
    cookies = load_cookies(no_cookie)

    def handle__cache(_session_name, no_cache):
        # == dealing with cache and history ==
        cache_fname = os.path.join(PROGRAM_HOME, "history", _session_name + ".json")
        os.makedirs(os.path.dirname(cache_fname), exist_ok=True)
        if os.path.exists(cache_fname) and not no_cache:
            try:
                with open(cache_fname, "r", encoding="UTF-8") as cache_file:
                    cache = json.load(cache_file)
            except Exception as e_txt:
                print("Error:", e_txt)
                os.remove(cache_fname)
                cache = []
        else:
            cache = []
        return cache, cache_fname
    
    def print_results(dicts, cache_fname):
        if sort:
            dicts.sort(key=lambda x: x[sort], reverse=True)
        if limit < float("inf"):
            dicts = dicts[: int(limit)]

        for d in dicts:
            if not d["magnet"]:
                logging.info("fetching magnet link for %s", d["title"])
                try:
                    html_subpage = requests.get(d["href"], cookies=cookies).text.encode("utf-8")
                    parsed_html_subpage = BeautifulSoup(html_subpage, "html.parser")
                    d["magnet"] = parsed_html_subpage.select_one('a[href^="magnet:"]').get("href")
                    d["torrent_file"] = parsed_html_subpage.select_one('a[href^="/download.php"]').get("href")
                except Exception as e:
                    print("Error:", e)

        logging.debug("unique(dicts): %s", unique_dicts(dicts))
        # reads file then merges with new dicts
        with open(cache_fname, "w", encoding="utf8") as f:
            json.dump(unique_dicts(dicts), f, indent=4)

        # open torrent urls in browser in the background (with delay between each one)
        if download_torrents is True or interactive and input(f"Open {len(dicts)} torrent files in browser for downloading? (Y/n) ").lower() != "n":
            torrent_urls = [d["torrent"] for d in dicts]
            magnet_urls = [d["magnet"] for d in dicts]
            asyncio.run(open_torrentfiles(torrent_urls + magnet_urls))

        if magnet:
            print("\n".join([t["magnet"] for t in dicts]))
        else:
            print(json.dumps(dicts, indent=4))

    def interactive_loop(dicts):
        while interactive:
            os.system("cls||clear")
            user_input = get_user_input_interactive(dicts)
            print("user_input", user_input)
            if user_input is None:  # next page
                print("\nNo item selected\n")
                pass
            elif user_input == "next":
                break
            else:  # indexes
                input_index = int(user_input)
                print_results([dicts[input_index]], cache_fname)

            user_input = input("[ENTER]: continue to go back, [b]: go (b)ack to results, [q]: to (q)uit: ")
            if user_input.lower() == "b":
                continue
            elif user_input.lower() == "q":
                exit(0)
            elif user_input == "":
                continue
        
    cache, cache_fname = handle__cache(_session_name, no_cookie)
    torrent_dicts_all = []
    page_num = 1

    while True:  # for all pages
        # target_url = "https://{domain}/torrents.php?search={search}&order={order}&category={category}&page={page}&by={by}"
        target_url_formatted = ref.TARGET_URL.format(
            domain=domain.strip(),
            search=quote(search),
            order=order,
            category=";".join(ref.CATEGORY2CODE[category]),
            page=page_num,
            by="DESC" if descending else "ASC",
        )
        response, html, cookies = get_page_html(target_url_formatted, cookies=cookies)

        with open(os.path.join(os.path.dirname(cache_fname), _session_name + f"_torrents_{page_num}.html"), "w", encoding="utf8") as response_cache:
            response_cache.write(response.text)
        
        if response.status_code != 200:
            logging.error("Status %s when accessing %s", response.status_code, target_url_formatted)
            break

        parsed_html = BeautifulSoup(html, "html.parser")
        torrents = parsed_html.select('tr.lista2 a[href^="/torrent/"][title]')

        logging.info("%s torrents found", len(torrents))
        if len(torrents) == 0:
            break
        magnets = list(map(extract_magnet, torrents))
        torrentfiles = list(map(partial(extract_torrent_file, domain=domain), torrents))

        # removes torrents and magnet links that have empty magnets, but maintained order
        torrents, magnets, torrentfiles = zip(*[[a, m, d] for (a, m, d) in zip(torrents, magnets, torrentfiles)])
        torrents, magnets, torrentfiles = list(torrents), list(magnets), list(torrentfiles)

        torrent_dicts_current:list = [
            {
                "title": torrent.get("title"),
                "torrent": torrentfile,
                "href": f"https://{domain}{torrent.get('href')}",
                "date": datetime.datetime.strptime(
                    str(torrent.findParent("tr").select_one("td:nth-child(3)").contents[0]), "%Y-%m-%d %H:%M:%S"
                ).timestamp(),
                "category": ref.CODE2CATEGORY.get(
                    torrent.findParent("tr").select_one("td:nth-child(1) img").get("src").split("/")[-1].replace("cat_new", "").replace(".gif", ""),
                    "UNKOWN",
                ),
                "size": format_size(parse_size(torrent.findParent("tr").select_one("td:nth-child(4)").contents[0]), block_size),
                "seeders": int(torrent.findParent("tr").select_one("td:nth-child(5) > font").contents[0]),
                "leechers": int(torrent.findParent("tr").select_one("td:nth-child(6)").contents[0]),
                "uploader": str(torrent.findParent("tr").select_one("td:nth-child(8)").contents[0]),
                "magnet": magnet,
            }
            for (torrent, magnet, torrentfile) in zip(torrents, magnets, torrentfiles)
        ]

        torrent_dicts_all += torrent_dicts_current

        cache = list(unique_dicts(torrent_dicts_all + cache))

        if interactive:
            interactive_loop(torrent_dicts_current)

        if len(list(filter(None, torrents))) >= limit:
            logging.info("Stopping: Reached limit %s", limit)
            break
        page_num += 1

    if not interactive:
        torrent_dicts_all = list(unique_dicts(torrent_dicts_all + cache))
        print_results(torrent_dicts_all, cache_fname)



def main():
    """Main function to get torrent"""
    args = get_args()
    logging.debug("Arguments: %s", vars(args))
    return search_for_torrent(**vars(args), _session_name=args_to_fname(args))


if __name__ == "__main__":
    main()
