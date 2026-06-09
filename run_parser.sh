#!/bin/bash

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Функция для проверки успешности выполнения
check_error() {
    if [ $? -ne 0 ]; then
        echo -e "${RED}Ошибка: $1${NC}"
        exit 1
    fi
}

# Проверка наличия Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python3 не установлен. Установите python3.${NC}"
    exit 1
fi

# Проверка аргументов
if [ $# -ne 1 ]; then
    echo -e "${YELLOW}Использование: $0 <URL каталога jsprav.ru>${NC}"
    echo "Пример: $0 'https://ufa.jsprav.ru/uslugi-po-iuridicheskomu-soprovozhdeniiu-sdelok-s-nedvizhimostiu/'"
    exit 1
fi

START_URL="$1"

# Проверка, что URL похож на jsprav.ru
if [[ ! "$START_URL" =~ jsprav\.ru ]]; then
    echo -e "${YELLOW}Внимание: URL не похож на jsprav.ru. Продолжаем...${NC}"
fi

# Проверка наличия необходимых Python-модулей
echo -e "${GREEN}Проверка зависимостей Python...${NC}"
python3 -c "import requests, bs4, lxml" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}Устанавливаем необходимые библиотеки...${NC}"
    pip3 install requests beautifulsoup4 lxml
    check_error "Не удалось установить зависимости. Установите вручную: pip3 install requests beautifulsoup4 lxml"
fi

# ================================================
# Шаг 1: Сбор списка компаний (название + сайт) со всех страниц каталога
# ================================================
echo -e "${GREEN}=== Шаг 1: Парсинг каталога jsprav.ru ===${NC}"
echo "Запуск parser.py с URL: $START_URL"
python3 parser.py "$START_URL"
check_error "Ошибка при выполнении parser.py"

# Проверка, что файл jsprav.ru.csv создан
if [ ! -f "jsprav.ru.csv" ]; then
    echo -e "${RED}Файл jsprav.ru.csv не был создан. Проверьте работу parser.py.${NC}"
    exit 1
fi

# Подсчёт строк (минус заголовок)
COUNT=$(tail -n +2 "jsprav.ru.csv" | wc -l)
echo -e "${GREEN}Собрано $COUNT компаний из каталога.${NC}"

# ================================================
# Шаг 2: Обогащение CSV контактами (email, телефон, соцсети)
# ================================================
echo -e "${GREEN}=== Шаг 2: Сбор контактной информации с сайтов компаний ===${NC}"
OUTPUT_CSV="jsprav.ru_contacts.csv"
echo "Входной файл: jsprav.ru.csv"
echo "Выходной файл: $OUTPUT_CSV"

# Запуск второго парсера. Предполагаем, что второй скрипт называется parser_all.py
# и ожидает аргументы: input.csv output.csv [site_column]
python3 parser_all.py "jsprav.ru.csv" "$OUTPUT_CSV" "site"
check_error "Ошибка при выполнении parser_all.py"

# Финальное сообщение
if [ -f "$OUTPUT_CSV" ]; then
    FINAL_COUNT=$(tail -n +2 "$OUTPUT_CSV" | wc -l)
    echo -e "${GREEN}Готово!${NC}"
    echo -e "Итоговый файл: ${GREEN}$OUTPUT_CSV${NC} (содержит $FINAL_COUNT записей)"
    echo -e "Колонки: name, site, emails, phones, telegram, whatsapp, vk"
else
    echo -e "${RED}Ошибка: итоговый файл не создан.${NC}"
    exit 1
fi
