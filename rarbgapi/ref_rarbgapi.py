"""Python module containing dictionaries for reference. DO NOT MODIFY"""

CATEGORY2CODE = {
    "movies": ['48', '17', '44', '45', '47', '50', '51', '52', '42', '46'],
    "xxx": ["4"],
    "music": ['23', '24', '25', '26'],
    "tvshows": ['18', '41', '49'],
    "software": ['33', '34', '43'],
    "games": ['27', '28', '29', '30', '31', '32', '40', '53'],
    "": "",
}

CODE2CATEGORY = {}
for key, values in CATEGORY2CODE.items():
    for value in values:
        CODE2CATEGORY[value] = key

SIZE_UNITS = {"B": 1, "KB": 10**3, "MB": 10**6, "GB": 10**9,
              "TB": 10**12, "PB": 10**15, "EB": 10**18, "ZB": 10**21, "YB": 10**24}

DEFAULT_HEADER = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.122 Safari/537.36"}

TARGET_URL = "https://{domain}/torrents.php?search={search}&order={order}&category={category}&page={page}&by={by}"
