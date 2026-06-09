#parser_all.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import re
import time
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

# ------------------ НАСТРОЙКИ ------------------
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
TIMEOUT = 10
DELAY_BETWEEN_SITES = 1      # секунд между разными сайтами
DELAY_BETWEEN_PAGES = 0.3    # секунд между страницами одного сайта

# Базовый список страниц для проверки (можно дополнять)
STATIC_PAGES = [
    '',  # главная
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

# Регулярные выражения
EMAIL_REGEX = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
PHONE_PATTERN = re.compile(r'(\+7|8)?[\s\-]*\(?(\d{3})\)?[\s\-]*(\d{3})[\s\-]*(\d{2})[\s\-]*(\d{2})')
TG_PATTERNS = [r'(?:https?://)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]+)']
WA_PATTERNS = [r'(?:https?://)?(?:wa\.me|api\.whatsapp\.com)/[^\s"\'>]+']
VK_PATTERNS = [r'(?:https?://)?(?:vk\.com|vkontakte\.ru)/([a-zA-Z0-9_.]+)']
# ----------------------------------------------

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
        raw = match.group(0)
        cleaned = clean_phone(raw)
        if len(cleaned) >= 10:
            phones.add(cleaned)
    return list(phones)

def extract_phones_from_links(soup):
    phones = set()
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('tel:'):
            phone = href[4:].strip()
            cleaned = clean_phone(phone)
            if len(cleaned) >= 10:
                phones.add(cleaned)
    return list(phones)

def extract_social_links(soup, base_url):
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

def extract_emails_from_html(html, base_url):
    emails = set()
    soup = BeautifulSoup(html, 'lxml')
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('mailto:'):
            email = href[7:].split('?')[0]
            emails.add(email)
    text = soup.get_text()
    found = re.findall(EMAIL_REGEX, text, re.IGNORECASE)
    for email in found:
        emails.add(email)
    return list(emails)

def get_page_follow_redirects(url):
    """
    Выполняет GET-запрос с автоматическим следованием редиректам.
    Возвращает (html, status_code, final_url).
    html = None при ошибке или не-HTML.
    status_code – итоговый HTTP-статус после всех редиректов.
    final_url – URL, на который в итоге попали.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        final_url = resp.url
        status = resp.status_code
        if status != 200:
            return None, status, final_url
        if 'text/html' not in resp.headers.get('Content-Type', ''):
            return None, status, final_url
        return resp.text, status, final_url
    except Exception as e:
        print(f"  Ошибка запроса {url}: {e}")
        return None, None, url

def find_contact_links_from_main(main_html, base_domain):
    soup = BeautifulSoup(main_html, 'lxml')
    keywords = ['контакт', 'обратн', 'связ', 'support', 'contact', 'about', 'о нас', 'feedback', 'help', 'ask', 'question', 'адрес', 'реквизит']
    contact_paths = set()
    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.get_text().lower()
        if any(kw in text for kw in keywords) or any(kw in href.lower() for kw in keywords):
            full_url = urljoin(base_domain, href)
            parsed = urlparse(full_url)
            path = parsed.path
            if path and path not in ['/', '']:
                contact_paths.add(path)
    return list(contact_paths)

def find_contacts_on_site(base_url):
    contacts = {
        'emails': set(),
        'phones': set(),
        'telegram': '',
        'whatsapp': '',
        'vk': ''
    }
    
    # ---- Запрос главной страницы с обработкой редиректов ----
    print(f"    Запрашиваем: {base_url}")
    html_main, status_main, final_main_url = get_page_follow_redirects(base_url)
    
    # Проверяем итоговый статус: только 200 нас устраивает
    if status_main != 200:
        print(f"    Итоговый статус {status_main}. Пропускаем сайт.")
        return contacts
    
    # Определяем базовый домен из финального URL (после редиректов)
    parsed_final = urlparse(final_main_url)
    base_domain = f"{parsed_final.scheme}://{parsed_final.netloc}"
    print(f"    Финальный домен: {base_domain}")
    
    # Парсим главную страницу
    soup_main = BeautifulSoup(html_main, 'lxml')
    contacts['emails'].update(extract_emails_from_html(html_main, final_main_url))
    contacts['phones'].update(extract_phones_from_text(soup_main.get_text()))
    contacts['phones'].update(extract_phones_from_links(soup_main))
    soc = extract_social_links(soup_main, final_main_url)
    if not contacts['telegram'] and soc['telegram']:
        contacts['telegram'] = soc['telegram']
    if not contacts['whatsapp'] and soc['whatsapp']:
        contacts['whatsapp'] = soc['whatsapp']
    if not contacts['vk'] and soc['vk']:
        contacts['vk'] = soc['vk']
    
    # Динамический сбор контактных страниц
    dynamic_paths = find_contact_links_from_main(html_main, base_domain)
    all_paths = set(STATIC_PAGES)
    all_paths.update(dynamic_paths)
    all_paths.discard('')  # главную уже обработали
    
    # ---- Проверка дополнительных страниц (относительно base_domain) ----
    for path in all_paths:
        url = urljoin(base_domain, path)
        print(f"    Проверяем {url}")
        html, status, _ = get_page_follow_redirects(url)
        if status != 200 or html is None:
            continue
        soup = BeautifulSoup(html, 'lxml')
        contacts['emails'].update(extract_emails_from_html(html, url))
        contacts['phones'].update(extract_phones_from_text(soup.get_text()))
        contacts['phones'].update(extract_phones_from_links(soup))
        soc = extract_social_links(soup, url)
        if not contacts['telegram'] and soc['telegram']:
            contacts['telegram'] = soc['telegram']
        if not contacts['whatsapp'] and soc['whatsapp']:
            contacts['whatsapp'] = soc['whatsapp']
        if not contacts['vk'] and soc['vk']:
            contacts['vk'] = soc['vk']
        time.sleep(DELAY_BETWEEN_PAGES)
    
    contacts['emails'] = ', '.join(contacts['emails']) if contacts['emails'] else ''
    contacts['phones'] = ', '.join(contacts['phones']) if contacts['phones'] else ''
    return contacts

def process_sites_from_csv(input_csv, output_csv, site_column='site'):
    rows = []
    with open(input_csv, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames + ['emails', 'phones', 'telegram', 'whatsapp', 'vk']
        for row in reader:
            site = row.get(site_column, '').strip()
            if not site:
                for fld in ['emails', 'phones', 'telegram', 'whatsapp', 'vk']:
                    row[fld] = ''
                rows.append(row)
                continue
            print(f"Обработка: {site}")
            contacts = find_contacts_on_site(site)
            row['emails'] = contacts['emails']
            row['phones'] = contacts['phones']
            row['telegram'] = contacts['telegram']
            row['whatsapp'] = contacts['whatsapp']
            row['vk'] = contacts['vk']
            rows.append(row)
            time.sleep(DELAY_BETWEEN_SITES)
    
    with open(output_csv, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Готово. Результат в {output_csv}")

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        print("Использование: python contact_extractor.py input.csv output.csv [site_column]")
        print("Пример: python contact_extractor.py companies.csv companies_contacts.csv site")
        sys.exit(1)
    input_csv = sys.argv[1]
    output_csv = sys.argv[2]
    site_col = sys.argv[3] if len(sys.argv) > 3 else 'site'
    process_sites_from_csv(input_csv, output_csv, site_col)
