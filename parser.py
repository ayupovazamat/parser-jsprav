#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import time
import base64
import requests
import sys
import os
import argparse
import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
DELAY = 30

def is_valid_url(url):
    """Проверяет, является ли строка корректным URL"""
    pattern = re.compile(r'^https?://[^\s/$.?#].[^\s]*$', re.IGNORECASE)
    return pattern.match(url) is not None

def parse_arguments():
    parser = argparse.ArgumentParser(description='Парсер компаний с jsprav.ru')
    parser.add_argument('input_file', help='Файл со ссылками на категории')
    parser.add_argument('output_file', nargs='?', default='jsprav.ru.csv', help='Выходной CSV файл')
    parser.add_argument('--test', action='store_true', help='Тестовый режим (только по 1 компании с категории)')
    parser.add_argument('--delay', type=int, default=30, help='Задержка между страницами (сек)')
    return parser.parse_args()

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

def parse_page(html, source_url):
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
            companies.append({
                'name': name, 
                'site': site,
                'source_url': source_url
            })
        elif site:
            companies.append({
                'name': '', 
                'site': site,
                'source_url': source_url
            })
    return companies

def get_next_page_url(current_url, current_page):
    if '/page-' in current_url:
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
    
    output_dir = os.path.dirname(filename)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    mode = 'a' if os.path.exists(filename) and seen_sites else 'w'
    with open(filename, mode, newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['name', 'site', 'source_url'])
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

def process_category_url(start_url, seen_sites, test_mode=False, delay=30):
    all_companies = []
    url = start_url
    page_num = 1
    while url:
        print(f"Загрузка страницы {page_num}: {url}")
        html = get_page(url)
        if not html:
            break
        companies = parse_page(html, start_url)
        if not companies:
            print(f"На странице {page_num} нет компаний. Конец каталога.")
            break
        print(f"Найдено компаний на странице: {len(companies)}")
        
        if test_mode:
            companies = companies[:1]
            print(f"Тестовый режим: взята 1 компания")
            all_companies.extend(companies)
            break
        else:
            all_companies.extend(companies)
        
        next_url = get_next_page_url(url, page_num)
        if next_url == url:
            break
        url = next_url
        page_num += 1
        print(f"Ожидание {delay} секунд...")
        time.sleep(delay)
    return all_companies

def main():
    args = parse_arguments()
    
    if not os.path.exists(args.input_file):
        print(f"Ошибка: Файл {args.input_file} не найден!")
        sys.exit(1)
    
    seen_sites = set()
    try:
        with open(args.output_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('site'):
                    seen_sites.add(row['site'])
    except FileNotFoundError:
        pass
    
    # Читаем URL категорий из файла, фильтруя только валидные URL
    urls = []
    with open(args.input_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if is_valid_url(line):
                urls.append(line)
            else:
                print(f"Предупреждение: пропущена некорректная строка: {line}")
    
    if not urls:
        print("Ошибка: Файл не содержит корректных URL!")
        sys.exit(1)
    
    print(f"Найдено {len(urls)} корректных URL категорий для обработки:")
    for u in urls:
        print(f"  - {u}")
    
    if args.test:
        print(f"\n⚠️ ТЕСТОВЫЙ РЕЖИМ: по 1 компании с категории ⚠️\n")
    
    for url in urls:
        print(f"\n=== Обработка категории: {url} ===")
        companies = process_category_url(url, seen_sites, args.test, args.delay)
        if companies:
            seen_sites = save_to_csv(companies, args.output_file, seen_sites)
        else:
            print(f"В категории {url} не найдено компаний")
    
    try:
        with open(args.output_file, 'r', encoding='utf-8-sig') as f:
            total = sum(1 for _ in f) - 1
        print(f"\nГотово. Всего собрано компаний: {total}. Результат в {args.output_file}")
    except:
        print(f"\nГотово. Результат в {args.output_file}")

if __name__ == "__main__":
    main()