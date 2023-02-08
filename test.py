import os
from copy import deepcopy
from multiprocessing import Pool
import time
import json
import re
from typing import List
from bs4 import BeautifulSoup, SoupStrainer
from tqdm import tqdm
from datetime import datetime, timedelta
import argparse
import requests

DEFAULT_USER_AGENT_STRING = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/87.0.4280.66 "
    "Safari/537.36"
)

def korean_character_ratio(text: str, ignore_whitespace: bool = True) -> float:
    if ignore_whitespace:
        text = "".join(text.split())

    korean_characters = len([c for c in text if ord("가") <= ord(c) <= ord("힣")])
    return korean_characters / len(text)

def drange(start: str, end: str, step: int = 1) -> List[str]:
    start_date = datetime.strptime(start, "%Y%m%d")
    end_date = datetime.strptime(end, "%Y%m%d")

    iters = (end_date - start_date).days // step
    return [
        (start_date + timedelta(days=d * step)).strftime("%Y%m%d")
        for d in range(iters + 1)
    ]


def remove_reporter_name(s: str):
    import re
    s = re.sub('^((\[.+\]|\(.+\))(\s?([가-힣 ]{2,} (기자|특파원),?)+\s*=?)+|(\[.+\]|\(.+\)))\s*', '', s)
    return s

def _prepare_nav_urls(category: [str], start_date: str, end_date: str, max_page: int) -> List[str]:
    return [
        f"https://news.naver.com/main/list.nhn?mode=LSD&mid=shm"
        f"&sid1={category}&date={date}&page={page}"
        for category in category
        for date in drange(start_date, end_date)
        for page in range(1, max_page + 1)
    ]


def extract_article_urls(document: str, _: bool) -> List[str]:
    document = document[document.find('<ul class="type06_headline">'):]

    # Extract article url containers.
    list1 = document[: document.find("</ul>")]
    list2 = document[document.find("</ul>") + 5:]
    list2 = list2[: list2.find("</ul>")]

    document = list1 + list2

    # Extract all article urls from the containers.
    article_urls = []
    while "<dt>" in document:
        document = document[document.find("<dt>"):]
        container = document[: document.find("</dt>")]

        if not container.strip():
            continue

        article_urls.append(re.search(r'<a href="(.*?)"', container).group(1))
        document = document[document.find("</dt>"):]

    return article_urls


def parse_article_content(document: str, include_reporter_name: bool) -> str:
    strainer = SoupStrainer("div", attrs={"id": "dic_area"})
    document = BeautifulSoup(document, "lxml", parse_only=strainer)
    content = document.find("div")

    # Skip invalid articles which do not contain news contents.
    if content is None:
        print("there is no body from GET- network error?")
        return None
        raise ValueError("there is no body from GET- network error?")

    # Remove unnecessary tags except `<br>` elements for preserving line-break
    # characters.
    for child in content.find_all():
        if child.name != "br":
            child.clear()

    content: str = content.get_text(separator="\n").strip()
    content = "\n".join([line.strip() for line in content.split('\n')])

    if len(content) == 0:
        print("there is no content after strips")
        return None
        raise ValueError("there is no content after strips")

    # Skip the contents which contain too many non-Korean characters.
    if korean_character_ratio(content) < 0.5:
        print("there are too few Korean characters in the content.")
        return None
        raise ValueError("there are too few Korean characters in the content.")

    # Normalize the contents by removing abnormal sentences.
    content = "\n".join(
        [
            line
            for line in content.splitlines()
            if len(line) > 0 and line[-1] == "."
        ]
    )

    # Remove reporter name part if set.
    if not include_reporter_name:
        splitted = content.split(sep='\n')
        content = "\n".join(splitted[1:])
        content = remove_reporter_name(splitted[0]) + content

    # Remove empty string
    if content == "":
        print("there is no news article content after parsing.")
        return None
        raise ValueError("there is no news article content after parsing.")

    return content


headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/98.0.4758.102"}


parser = argparse.ArgumentParser()
parser.add_argument("--day", dest='day', required=True, help="single day")
args = parser.parse_args()


###############
def request_and_parse_and_write_to_file(article_url):
    # extract articles
    req = requests.get(article_url, headers=headers)
    html = req.text
    # parse article content
    body = parse_article_content(html, False)

    # log
    if body is None:
        print(article_url)

    # make directory if not exists
    if not os.path.exists(f"{args.day}/"):
        os.makedirs(f"{args.day}/")
    # save to files
    with open(f"{args.day}/{time.time() * 100000}.txt", 'w') as t:
        if body is not None:
            t.write(body)
        else:
            print("body is None")


if __name__ == '__main__':
    # prepare urls
    # '101', '102', '103', '104',
    # '104' 세계 제외- 영어가 너무 많음.
    urls = _prepare_nav_urls(category=['101', '102', '103', '105'], start_date=args.day, end_date=args.day,
                             max_page=200)

    # article_set
    article_urls = set()

    # read from web: article urls
    for url in tqdm(urls):
        try:
            res = requests.get(url, headers=headers, timeout=1000)
            html = res.text
            article_urls.update(extract_article_urls(html, None))
        except:
            print("Request time out: 네이버 IP 차단")
    article_urls: List[str] = list(article_urls)
    print(f"article lens:{len(article_urls)}")
    # multi-processing
    print("start to get each article")


    # with Pool(processes=8) as pool:
    #     try:
    #         pool.map(request_and_parse_and_write_to_file, tqdm(article_urls), chunksize=None)
    #     except Exception as e:
    #         print(e)
    #     pool.close()
    #     pool.join()
    try:
        for url in article_urls:
            request_and_parse_and_write_to_file(url)
    except Exception as e:
        print(e)
