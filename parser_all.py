#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import re
import time
import requests
import sys
import os
import argparse
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
TIMEOUT = 10
DELAY_BETWEEN_SITES = 1
DELAY_BETWEEN_PAGES = 0.3

STATIC_PAGES = [
    '/contacts', '/contact', '/kontakty', '/contact-us', '/feedback',
    '/obratnaya-svyaz', '/svyaz', '/write-us', '/support',
    '/about', '/about-us', '/o-nas', '/company', '/kompaniya',
    '/info', '/help', '/ask', '/questions', '/kontaktnaya-informatsiya',
    '/rekvizity', '/requisites', '/where', '/adresa', '/offices',
    '/representatives', '/map', '/kontaktnaya-stranitsa', '/contact-page',
    '/callback', '/zadat-vopros', '/suggest', '/form', '/order', '/consult',
    '/get-in-touch', '/en/contacts', '/en/contact', '/en/about', '/eng/contacts',
    '/contact/', '/contacts/', '/about/', '/company/contacts', '/site/contacts',
    '/page/contacts', '/contact_us', '/contactus', '/kontakt', '/kontakti',
    '/contatti', '/contato', '/connexion', '/kontaktai'
]

EMAIL_REGEX = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
PHONE_PATTERN = re.compile(r'(\+7|8)?[\s\-]*\(?(\d{3})\)?[\s\-]*(\d{3})[\s\-]*(\d{2})[\s\-]*(\d{2})')
TG_PATTERNS = [r'(?:https?://)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]+)']
WA_PATTERNS = [r'(?:https?://)?(?:wa\.me|api\.whatsapp\.com)/[^\s"\'>]+']
VK_PATTERNS = [r'(?:https?://)?(?:vk\.com|vkontakte\.ru)/([a-zA-Z0-9_.]+)']

def parse_arguments():
    parser = argparse.ArgumentParser(description='Сбор контактов с сайтов компаний')
    parser.add_argument('input_csv', help='Входной CSV файл с колонкой site')
    parser.add_argument('output_csv', help='Выходной CSV файл')
    parser.add_argument('site_column', nargs='?', default='site', help='Название колонки с URL сайта')
    parser.add_argument('--test', action='store_true', help='Тестовый режим (только 1 контакт на сайт)')
    parser.add_argument('--delay', type=int, default=1, help='Задержка между сайтами (сек)')
    return parser.parse_args()

def clean_phone(phone_str):
    digits = re.sub(r'\D', '', phone_str)
    if len(digits) == 11 and digits.startswith('8'):
        digits = '+7' + digits[1:]
    elif len(digits) == 10:
        digits = '+7' + digits
    elif len(digits) == 11 and digits.startswith('7'):
        digits = '+' + digits
    return digits

def extract_phones_from_text(text):
    phones = set()
    for match in PHONE_PATTERN.finditer(text):
        cleaned = clean_phone(match.group(0))
        if len(cleaned) >= 10:
            phones.add(cleaned)
    return list(phones)

def extract_phones_from_links(soup):
    phones = set()
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('tel:'):
            cleaned = clean_phone(href[4:].strip())
            if len(cleaned) >= 10:
                phones.add(cleaned)
    return list(phones)

def extract_social_links(soup):
    result = {'telegram': '', 'whatsapp': '', 'vk': ''}
    all_links = set()
    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        if href and not href.startswith('#'):
            all_links.add(href)
    for link in all_links:
        link_lower = link.lower()
        if not result['telegram']:
            for pat in TG_PATTERNS:
                if re.search(pat, link_lower):
                    result['telegram'] = link
                    break
        if not result['whatsapp']:
            for pat in WA_PATTERNS:
                if re.search(pat, link_lower):
                    result['whatsapp'] = link
                    break
        if not result['vk']:
            for pat in VK_PATTERNS:
                if re.search(pat, link_lower):
                    result['vk'] = link
                    break
    return result

def extract_emails_from_html(html):
    emails = set()
    soup = BeautifulSoup(html, 'lxml')
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('mailto:'):
            email = href[7:].split('?')[0]
            emails.add(email)
    for email in re.findall(EMAIL_REGEX, soup.get_text(), re.IGNORECASE):
        emails.add(email)
    return list(emails)

def get_page_follow_redirects(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if resp.status_code != 200 or 'text/html' not in resp.headers.get('Content-Type', ''):
            return None, resp.status_code, resp.url
        return resp.text, resp.status_code, resp.url
    except Exception as e:
        print(f"  Ошибка запроса {url}: {e}")
        return None, None, url

def find_contact_links_from_main(html, base_domain):
    soup = BeautifulSoup(html, 'lxml')
    keywords = ['контакт', 'обратн', 'связ', 'support', 'contact', 'about', 'о нас', 'feedback', 'help', 'ask', 'question', 'адрес', 'реквизит']
    paths = set()
    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.get_text().lower()
        if any(kw in text for kw in keywords) or any(kw in href.lower() for kw in keywords):
            full = urljoin(base_domain, href)
            path = urlparse(full).path
            if path and path not in ('/', ''):
                paths.add(path)
    return list(paths)

def has_any_social(contacts):
    return bool(contacts['telegram'] or contacts['whatsapp'] or contacts['vk'])

def format_contacts(contacts):
    return {
        'emails': ', '.join(contacts['emails']) if contacts['emails'] else '',
        'phones': ', '.join(contacts['phones']) if contacts['phones'] else '',
        'telegram': contacts['telegram'],
        'whatsapp': contacts['whatsapp'],
        'vk': contacts['vk']
    }

def find_contacts_on_site(base_url, test_mode=False):
    contacts = {
        'emails': set(),
        'phones': set(),
        'telegram': '',
        'whatsapp': '',
        'vk': ''
    }
    
    print(f"    Запрашиваем: {base_url}")
    html, status, final_url = get_page_follow_redirects(base_url)
    if status != 200:
        print(f"    Статус {status}. Пропускаем.")
        return format_contacts(contacts)

    base_domain = f"{urlparse(final_url).scheme}://{urlparse(final_url).netloc}"
    print(f"    Финальный домен: {base_domain}")

    soup = BeautifulSoup(html, 'lxml')
    contacts['emails'].update(extract_emails_from_html(html))
    contacts['phones'].update(extract_phones_from_text(soup.get_text()))
    contacts['phones'].update(extract_phones_from_links(soup))
    soc = extract_social_links(soup)
    for k in ('telegram', 'whatsapp', 'vk'):
        if not contacts[k] and soc[k]:
            contacts[k] = soc[k]

    if test_mode and (contacts['emails'] or contacts['phones']):
        print("    Тестовый режим: контакт найден на главной")
        return format_contacts(contacts)

    dynamic_paths = find_contact_links_from_main(html, base_domain)
    dynamic_paths = dynamic_paths[:7]
    checked_paths = set()

    for path in dynamic_paths:
        url = urljoin(base_domain, path)
        print(f"    Проверяем динамическую страницу: {url}")
        html2, status2, _ = get_page_follow_redirects(url)
        checked_paths.add(path)
        if status2 != 200 or not html2:
            continue
        soup2 = BeautifulSoup(html2, 'lxml')
        contacts['emails'].update(extract_emails_from_html(html2))
        contacts['phones'].update(extract_phones_from_text(soup2.get_text()))
        contacts['phones'].update(extract_phones_from_links(soup2))
        soc2 = extract_social_links(soup2)
        for k in ('telegram', 'whatsapp', 'vk'):
            if not contacts[k] and soc2[k]:
                contacts[k] = soc2[k]

        time.sleep(DELAY_BETWEEN_PAGES)
        
        if test_mode and (contacts['emails'] or contacts['phones']):
            print("    Тестовый режим: контакт найден на динамической странице")
            return format_contacts(contacts)

    short_static = [
        '/contacts', '/contact', '/kontakty', '/about', '/o-nas',
        '/contact-us', '/feedback', '/obratnaya-svyaz'
    ]
    remaining_paths = [path for path in short_static if path not in checked_paths]
    
    if remaining_paths:
        print(f"    Осталось проверить статические страницы: {remaining_paths}")
    
    for path in remaining_paths:
        url = urljoin(base_domain, path)
        print(f"    Проверяем статическую страницу: {url}")
        html2, status2, _ = get_page_follow_redirects(url)
        if status2 != 200 or not html2:
            continue
        soup2 = BeautifulSoup(html2, 'lxml')
        contacts['emails'].update(extract_emails_from_html(html2))
        contacts['phones'].update(extract_phones_from_text(soup2.get_text()))
        contacts['phones'].update(extract_phones_from_links(soup2))
        soc2 = extract_social_links(soup2)
        for k in ('telegram', 'whatsapp', 'vk'):
            if not contacts[k] and soc2[k]:
                contacts[k] = soc2[k]

        time.sleep(DELAY_BETWEEN_PAGES)
        
        if test_mode and (contacts['emails'] or contacts['phones']):
            print("    Тестовый режим: контакт найден на статической странице")
            return format_contacts(contacts)

    return format_contacts(contacts)

def load_existing(output_csv):
    existing = {}
    try:
        with open(output_csv, 'r', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                site = row.get('site', '').strip()
                if site:
                    existing[site] = row
    except FileNotFoundError:
        pass
    return existing

def process_sites_from_csv(input_csv, output_csv, site_column='site', test_mode=False, delay=1):
    output_dir = os.path.dirname(output_csv)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    if test_mode:
        print(f"\n⚠️ ТЕСТОВЫЙ РЕЖИМ: только по 1 контакту на сайт ⚠️\n")
    
    existing = load_existing(output_csv)
    new_rows = []
    
    with open(input_csv, 'r', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            site = row.get(site_column, '').strip()
            source_url = row.get('source_url', '')
            
            if not site or site in existing:
                if site:
                    print(f"Пропускаем (уже есть): {site}")
                continue
            
            print(f"Обработка: {site}")
            contacts = find_contacts_on_site(site, test_mode)
            
            new_row = {
                'name': row.get('name', ''),
                'site': site,
                'source_url': source_url,
                'emails': contacts['emails'],
                'phones': contacts['phones'],
                'telegram': contacts['telegram'],
                'whatsapp': contacts['whatsapp'],
                'vk': contacts['vk']
            }
            new_rows.append(new_row)
            existing[site] = new_row
            time.sleep(delay)
    
    all_rows = list(existing.values())
    fieldnames = ['name', 'site', 'source_url', 'emails', 'phones', 'telegram', 'whatsapp', 'vk']
    
    with open(output_csv, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
    
    print(f"Готово. Обработано новых сайтов: {len(new_rows)}. Результат в {output_csv}")

if __name__ == '__main__':
    args = parse_arguments()
    process_sites_from_csv(
        args.input_csv, 
        args.output_csv, 
        args.site_column, 
        args.test,
        args.delay
    )