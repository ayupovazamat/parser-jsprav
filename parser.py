#pareser.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import time
import base64
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
DELAY = 30  # секунд между запросами страниц
OUTPUT_CSV = 'jsprav.ru.csv'

def decode_base64(data):
    """Декодирует base64-строку (иногда с лишними символами)"""
    try:
        # Добавляем padding если нужно
        missing_padding = len(data) % 4
        if missing_padding:
            data += '=' * (4 - missing_padding)
        return base64.b64decode(data).decode('utf-8')
    except Exception:
        return None

def get_page(url):
    """Загружает HTML страницы, возвращает текст или None при ошибке"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        if resp.status_code != 200:
            print(f"Статус {resp.status_code} для {url}, пропускаем")
            return None
        # Проверяем, что вернулся HTML
        if 'text/html' not in resp.headers.get('Content-Type', ''):
            return None
        return resp.text
    except Exception as e:
        print(f"Ошибка загрузки {url}: {e}")
        return None

def parse_page(html, base_url):
    """
    Извлекает из HTML все блоки company-info-c.
    Возвращает список словарей с ключами 'name' и 'site'.
    """
    soup = BeautifulSoup(html, 'lxml')
    blocks = soup.select('div.company-info-c')
    if not blocks:
        print("Блоки div.company-info-c не найдены, возможно страница без компаний или изменилась структура.")
        return []

    companies = []
    for block in blocks:
        # Название компании
        name_span = block.select_one('span.company-info-name-org')
        name = name_span.get_text(strip=True) if name_span else ''

        # Сайт: ищем a.company-info-site-open, извлекаем data-link (base64) или data-text-after
        site = ''
        site_link = block.select_one('a.company-info-site-open')
        if site_link:
            # Приоритет: атрибут data-link (base64)
            data_link = site_link.get('data-link')
            if data_link:
                decoded = decode_base64(data_link)
                if decoded:
                    site = decoded
            # Если data-link нет или не декодировался, пробуем data-text-after
            if not site:
                data_text = site_link.get('data-text-after')
                if data_text and not data_text.startswith('...'):
                    site = data_text.strip()
            # Если ничего не нашли, пробуем href
            if not site:
                href = site_link.get('href')
                if href and href.startswith('/redirect/'):
                    # Можно попробовать распарсить, но лучше не усложнять
                    pass
                elif href and href.startswith('http'):
                    site = href
        # Сохраняем, если есть хотя бы название
        if name:
            companies.append({'name': name, 'site': site})
        else:
            # Если название пустое, но есть сайт – тоже сохраним
            if site:
                companies.append({'name': '', 'site': site})
    return companies

def get_next_page_url(current_url, current_page):
    """
    Формирует URL следующей страницы для jsprav.ru.
    Если текущий URL не содержит 'page-', добавляет 'page-2/'.
    Иначе заменяет 'page-N' на 'page-(N+1)'.
    """
    if '/page-' in current_url:
        # Заменяем последнее вхождение page-N на page-(N+1)
        import re
        new_url = re.sub(r'/page-\d+/', f'/page-{current_page+1}/', current_url)
        return new_url
    else:
        # Добавляем page-2 в конец, учитывая слеш
        base = current_url.rstrip('/')
        return f"{base}/page-2/"

def save_to_csv(companies, filename):
    """Сохраняет список компаний в CSV"""
    if not companies:
        print("Нет данных для сохранения.")
        return
    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['name', 'site'])
        writer.writeheader()
        writer.writerows(companies)
    print(f"Сохранено {len(companies)} записей в {filename}")

def main(start_url):
    all_companies = []
    url = start_url
    page_num = 1

    while url:
        print(f"Загрузка страницы {page_num}: {url}")
        html = get_page(url)
        if not html:
            print("Не удалось загрузить страницу. Завершаем.")
            break

        companies = parse_page(html, url)
        if not companies:
            print(f"На странице {page_num} нет компаний. Возможно, достигнут конец каталога.")
            break

        print(f"Найдено компаний на странице: {len(companies)}")
        all_companies.extend(companies)

        # Формируем URL следующей страницы
        next_url = get_next_page_url(url, page_num)
        # Проверяем, не совпадает ли с текущим
        if next_url == url:
            break
        url = next_url
        page_num += 1

        # Ждём перед следующим запросом
        print(f"Ожидание {DELAY} секунд перед следующей страницей...")
        time.sleep(DELAY)

    # Сохраняем результат
    if all_companies:
        save_to_csv(all_companies, OUTPUT_CSV)
    else:
        print("Ни одной компании не найдено.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Использование: python parser.py <URL начальной страницы>")
        print("Пример: python parser.py 'https://ufa.jsprav.ru/uslugi-po-iuridicheskomu-soprovozhdeniiu-sdelok-s-nedvizhimostiu/'")
        sys.exit(1)
    start_url = sys.argv[1]
    main(start_url)
