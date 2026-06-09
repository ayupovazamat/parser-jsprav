#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import time
import base64
import requests
import sys
import os
from urllib.parse import urljoin
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
DELAY = 30

# Обработка параметров командной строки
if len(sys.argv) < 2:
    print("Использование: python parser.py <файл_со_ссылками.txt> [выходной_файл.csv]")
    print("Пример: python parser.py categories.txt output/jsprav.ru.csv")
    sys.exit(1)

INPUT_FILE = sys.argv[1]

# Если передан второй аргумент, используем его как имя выходного файла
if len(sys.argv) > 2:
    OUTPUT_CSV = sys.argv[2]
else:
    OUTPUT_CSV = 'jsprav.ru.csv'

# Создаём директорию для выходного файла, если нужно
output_dir = os.path.dirname(OUTPUT_CSV)
if output_dir and not os.path.exists(output_dir):
    os.makedirs(output_dir, exist_ok=True)

def decode_base64(data):
    try:
        missing_padding = len(data) % 4
        if missing_padding:
            data += '=' * (4 - missing_padding)
        return base64.b64decode(data).decode('utf-8')
    except Exception:
        return None

def get_page(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        if resp.status_code != 200:
            print(f"Статус {resp.status_code} для {url}, пропускаем")
            return None
        if 'text/html' not in resp.headers.get('Content-Type', ''):
            return None
        return resp.text
    except Exception as e:
        print(f"Ошибка загрузки {url}: {e}")
        return None

def parse_page(html):
    soup = BeautifulSoup(html, 'lxml')
    blocks = soup.select('div.company-info-c')
    if not blocks:
        return []
    companies = []
    for block in blocks:
        name_span = block.select_one('span.company-info-name-org')
        name = name_span.get_text(strip=True) if name_span else ''
        site = ''
        site_link = block.select_one('a.company-info-site-open')
        if site_link:
            data_link = site_link.get('data-link')
            if data_link:
                decoded = decode_base64(data_link)
                if decoded:
                    site = decoded
            if not site:
                data_text = site_link.get('data-text-after')
                if data_text and not data_text.startswith('...'):
                    site = data_text.strip()
            if not site:
                href = site_link.get('href')
                if href and href.startswith('http'):
                    site = href
        if name:
            companies.append({'name': name, 'site': site})
        elif site:
            companies.append({'name': '', 'site': site})
    return companies

def get_next_page_url(current_url, current_page):
    if '/page-' in current_url:
        import re
        new_url = re.sub(r'/page-\d+/', f'/page-{current_page+1}/', current_url)
        return new_url
    else:
        base = current_url.rstrip('/')
        return f"{base}/page-2/"

def save_to_csv(companies, filename, seen_sites=None):
    if not companies:
        return seen_sites
    if seen_sites is None:
        seen_sites = set()
        try:
            with open(filename, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('site'):
                        seen_sites.add(row['site'])
        except FileNotFoundError:
            pass
    mode = 'a' if os.path.exists(filename) and seen_sites else 'w'
    with open(filename, mode, newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['name', 'site'])
        if mode == 'w':
            writer.writeheader()
        added = 0
        for comp in companies:
            if comp['site'] and comp['site'] in seen_sites:
                continue
            writer.writerow(comp)
            if comp['site']:
                seen_sites.add(comp['site'])
                added += 1
        print(f"Добавлено {added} новых записей в {filename}")
    return seen_sites

def process_category_url(start_url, seen_sites):
    all_companies = []
    url = start_url
    page_num = 1
    while url:
        print(f"Загрузка страницы {page_num}: {url}")
        html = get_page(url)
        if not html:
            break
        companies = parse_page(html)
        if not companies:
            print(f"На странице {page_num} нет компаний. Конец каталога.")
            break
        print(f"Найдено компаний на странице: {len(companies)}")
        all_companies.extend(companies)
        next_url = get_next_page_url(url, page_num)
        if next_url == url:
            break
        url = next_url
        page_num += 1
        print(f"Ожидание {DELAY} секунд...")
        time.sleep(DELAY)
    return all_companies

def main():
    # Проверяем, что входной файл существует
    if not os.path.exists(INPUT_FILE):
        print(f"Ошибка: Файл {INPUT_FILE} не найден!")
        sys.exit(1)
    
    # Загружаем уже обработанные сайты
    seen_sites = set()
    try:
        with open(OUTPUT_CSV, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('site'):
                    seen_sites.add(row['site'])
    except FileNotFoundError:
        pass
    
    # Читаем URL категорий из файла
    with open(INPUT_FILE, 'r') as f:
        urls = [line.strip() for line in f if line.strip()]
    
    if not urls:
        print("Ошибка: Файл не содержит URL!")
        sys.exit(1)
    
    print(f"Найдено {len(urls)} URL категорий для обработки:")
    for u in urls:
        print(f"  - {u}")
    
    # Обрабатываем каждую категорию
    for url in urls:
        print(f"\n=== Обработка категории: {url} ===")
        companies = process_category_url(url, seen_sites)
        if companies:
            seen_sites = save_to_csv(companies, OUTPUT_CSV, seen_sites)
        else:
            print(f"В категории {url} не найдено компаний")
    
    # Финальная статистика
    try:
        with open(OUTPUT_CSV, 'r', encoding='utf-8-sig') as f:
            total = sum(1 for _ in f) - 1
        print(f"\nГотово. Всего собрано компаний: {total}. Результат в {OUTPUT_CSV}")
    except:
        print(f"\nГотово. Результат в {OUTPUT_CSV}")

if __name__ == "__main__":
    main()