#!/bin/bash

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для проверки успешности выполнения
check_error() {
    if [ $? -ne 0 ]; then
        echo -e "${RED}Ошибка: $1${NC}"
        exit 1
    fi
}

# Функция для вывода разделителя
print_separator() {
    echo -e "${BLUE}========================================${NC}"
}

# Функция для создания необходимых директорий
create_directories() {
    if [ ! -d "input" ]; then
        mkdir -p "input"
        echo -e "${GREEN}Создана директория: input/${NC}"
        echo -e "${YELLOW}Поместите файлы с ссылками (.txt) в папку input/${NC}"
    fi
    if [ ! -d "output" ]; then
        mkdir -p "output"
        echo -e "${GREEN}Создана директория: output/${NC}"
    fi
}

# Функция для поиска всех .txt файлов в папке input
find_input_files() {
    local files=()
    if [ -d "input" ]; then
        for file in input/*.txt; do
            if [ -f "$file" ] && [ -s "$file" ]; then
                files+=("$file")
            fi
        done
    fi
    echo "${files[@]}"
}

# Проверка наличия Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python3 не установлен. Установите python3.${NC}"
    exit 1
fi

# Создаём необходимые директории
create_directories

# Настройка параметров по умолчанию
OUTPUT_SITES="${OUTPUT_SITES:-output/jsprav.ru.csv}"
OUTPUT_CONTACTS="${OUTPUT_CONTACTS:-output/jsprav.ru_contacts.csv}"

# Обработка аргументов
if [ $# -eq 0 ]; then
    # Если параметры не заданы, ищем все .txt файлы в папке input
    echo -e "${YELLOW}Параметры не заданы. Ищем файлы с ссылками в папке input/...${NC}"
    
    INPUT_FILES=($(find_input_files))
    
    if [ ${#INPUT_FILES[@]} -eq 0 ]; then
        echo -e "${RED}Не найдено ни одного .txt файла в папке input/${NC}"
        echo -e "${YELLOW}Создайте файлы в папке input/ (например, input/categories.txt)${NC}"
        echo ""
        echo -e "${BLUE}Пример содержимого input/categories.txt:${NC}"
        echo "https://ufa.jsprav.ru/uslugi-po-iuridicheskomu-soprovozhdeniiu-sdelok-s-nedvizhimostiu/"
        echo "https://ufa.jsprav.ru/avtoservisyi-avtotehtsentryi/"
        exit 1
    fi
    
    echo -e "${GREEN}Найдены файлы:${NC}"
    for file in "${INPUT_FILES[@]}"; do
        echo "  - $file"
    done
    
    CATEGORIES_FILES=("${INPUT_FILES[@]}")
else
    # Если параметры заданы, ищем файлы сначала в input/, потом в текущей директории
    CATEGORIES_FILES=()
    for arg in "$@"; do
        if [ -f "input/$arg" ]; then
            CATEGORIES_FILES+=("input/$arg")
            echo -e "  Используем: input/$arg"
        elif [ -f "$arg" ]; then
            CATEGORIES_FILES+=("$arg")
            echo -e "  Используем: $arg"
        else
            echo -e "${RED}Файл $arg не найден!${NC}"
            exit 1
        fi
    done
fi

# Проверка наличия необходимых Python-модулей
echo -e "${GREEN}Проверка зависимостей Python...${NC}"
python3 -c "import requests, bs4, lxml" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}Устанавливаем необходимые библиотеки...${NC}"
    pip3 install requests beautifulsoup4 lxml
    check_error "Не удалось установить зависимости. Установите вручную: pip3 install requests beautifulsoup4 lxml"
fi

# Переменные
TEMP_CATEGORIES="/tmp/all_categories_$$.txt"

# Объединяем все файлы с категориями во временный файл
echo -e "${GREEN}Объединение файлов с категориями...${NC}"
> "$TEMP_CATEGORIES"
for file in "${CATEGORIES_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo -e "${RED}Файл $file не найден!${NC}"
        exit 1
    fi
    # Проверяем, что файл не пустой
    if [ ! -s "$file" ]; then
        echo -e "${YELLOW}Предупреждение: Файл $file пуст. Пропускаем.${NC}"
        continue
    fi
    cat "$file" >> "$TEMP_CATEGORIES"
    echo -e "  Добавлен: $file"
done

# Проверяем, что временный файл не пуст
if [ ! -s "$TEMP_CATEGORIES" ]; then
    echo -e "${RED}Нет данных для обработки. Все файлы пусты.${NC}"
    rm -f "$TEMP_CATEGORIES"
    exit 1
fi

# Удаляем пустые строки и дубликаты
sort -u "$TEMP_CATEGORIES" -o "$TEMP_CATEGORIES"
UNIQUE_COUNT=$(wc -l < "$TEMP_CATEGORIES")
echo -e "Всего уникальных категорий для обработки: ${GREEN}$UNIQUE_COUNT${NC}"

# Показываем первые 5 категорий для информации
if [ $UNIQUE_COUNT -gt 0 ]; then
    echo -e "${BLUE}Первые категории:${NC}"
    head -5 "$TEMP_CATEGORIES" | while read -r line; do
        echo "  - $line"
    done
    if [ $UNIQUE_COUNT -gt 5 ]; then
        echo "  ... и ещё $((UNIQUE_COUNT - 5))"
    fi
fi

# ================================================
# Шаг 1: Сбор списка компаний (название + сайт) со всех страниц каталога
# ================================================
print_separator
echo -e "${GREEN}=== Шаг 1: Парсинг каталога jsprav.ru ===${NC}"
echo "Файл с категориями: $TEMP_CATEGORIES"
echo "Выходной файл: $OUTPUT_SITES"

# Запуск первого парсера
python3 parser.py "$TEMP_CATEGORIES" "$OUTPUT_SITES"
PARSER_EXIT=$?

# Удаляем временный файл
rm -f "$TEMP_CATEGORIES"

if [ $PARSER_EXIT -ne 0 ]; then
    echo -e "${RED}Ошибка при выполнении parser.py${NC}"
    exit 1
fi

# Проверка, что файл создан и не пуст
if [ ! -f "$OUTPUT_SITES" ] || [ ! -s "$OUTPUT_SITES" ]; then
    echo -e "${YELLOW}Предупреждение: Файл $OUTPUT_SITES пуст или не создан.${NC}"
    echo "Возможно, не найдено ни одной компании."
    read -p "Продолжить сбор контактов? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi
else
    # Подсчёт строк (минус заголовок)
    COUNT=$(tail -n +2 "$OUTPUT_SITES" | wc -l)
    echo -e "${GREEN}Собрано $COUNT компаний из каталога.${NC}"
fi

# ================================================
# Шаг 2: Обогащение CSV контактами (email, телефон, соцсети)
# ================================================
print_separator
echo -e "${GREEN}=== Шаг 2: Сбор контактной информации с сайтов компаний ===${NC}"
echo "Входной файл: $OUTPUT_SITES"
echo "Выходной файл: $OUTPUT_CONTACTS"

# Запуск второго парсера
python3 parser_all.py "$OUTPUT_SITES" "$OUTPUT_CONTACTS" "site"
check_error "Ошибка при выполнении parser_all.py"

# Финальная статистика
if [ -f "$OUTPUT_CONTACTS" ]; then
    FINAL_COUNT=$(tail -n +2 "$OUTPUT_CONTACTS" | wc -l)
    print_separator
    echo -e "${GREEN}Готово!${NC}"
    echo -e "${GREEN}Итоговый файл с контактами:${NC} $OUTPUT_CONTACTS"
    echo -e "${GREEN}Всего записей:${NC} $FINAL_COUNT"
    echo -e "${GREEN}Колонки:${NC} name, site, emails, phones, telegram, whatsapp, vk"
    
    # Вывод небольшой статистики по найденным контактам
    if [ $FINAL_COUNT -gt 0 ]; then
        EMAIL_COUNT=$(awk -F',' 'NR>1 {gsub(/"/, "", $3); if($3!="") count++} END {print count+0}' "$OUTPUT_CONTACTS")
        PHONE_COUNT=$(awk -F',' 'NR>1 {gsub(/"/, "", $4); if($4!="") count++} END {print count+0}' "$OUTPUT_CONTACTS")
        TELEGRAM_COUNT=$(awk -F',' 'NR>1 {gsub(/"/, "", $5); if($5!="") count++} END {print count+0}' "$OUTPUT_CONTACTS")
        WHATSAPP_COUNT=$(awk -F',' 'NR>1 {gsub(/"/, "", $6); if($6!="") count++} END {print count+0}' "$OUTPUT_CONTACTS")
        VK_COUNT=$(awk -F',' 'NR>1 {gsub(/"/, "", $7); if($7!="") count++} END {print count+0}' "$OUTPUT_CONTACTS")
        
        echo -e "${BLUE}Статистика:${NC}"
        echo "  - Найдено email: $EMAIL_COUNT из $FINAL_COUNT"
        echo "  - Найдено телефонов: $PHONE_COUNT из $FINAL_COUNT"
        echo "  - Найдено Telegram: $TELEGRAM_COUNT из $FINAL_COUNT"
        echo "  - Найдено WhatsApp: $WHATSAPP_COUNT из $FINAL_COUNT"
        echo "  - Найдено VK: $VK_COUNT из $FINAL_COUNT"
    else
        echo -e "${YELLOW}Нет данных для статистики.${NC}"
    fi
else
    echo -e "${RED}Ошибка: итоговый файл не создан.${NC}"
    exit 1
fi

print_separator
echo -e "${GREEN}Скрипт успешно завершён!${NC}"
echo -e "${BLUE}Результаты сохранены в директории output/${NC}"
echo -e "${BLUE}Исходные файлы с ссылками должны быть в директории input/${NC}"
echo ""
echo -e "${YELLOW}Текущее содержимое папок:${NC}"
echo "input/:"
ls -la input/ 2>/dev/null || echo "  (пусто)"
echo ""
echo "output/:"
ls -la output/ 2>/dev/null || echo "  (пусто)"