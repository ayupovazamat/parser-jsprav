#!/bin/bash

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

check_error() {
    if [ $? -ne 0 ]; then
        echo -e "${RED}Ошибка: $1${NC}"
        exit 1
    fi
}

print_separator() {
    echo -e "${BLUE}========================================${NC}"
}

create_directories() {
    if [ ! -d "input" ]; then
        mkdir -p "input"
        echo -e "${GREEN}Создана директория: input/${NC}"
    fi
    if [ ! -d "output" ]; then
        mkdir -p "output"
        echo -e "${GREEN}Создана директория: output/${NC}"
    fi
    if [ ! -d "output/test" ]; then
        mkdir -p "output/test"
        echo -e "${GREEN}Создана директория: output/test/${NC}"
    fi
}

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

# Парсинг аргументов
TEST_MODE=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --test)
            TEST_MODE=true
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# Проверка Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python3 не установлен.${NC}"
    exit 1
fi

create_directories

# Настройка выходных файлов
if [ "$TEST_MODE" = true ]; then
    OUTPUT_SITES="output/test/jsprav.ru.csv"
    OUTPUT_CONTACTS="output/test/jsprav.ru_contacts.csv"
    echo -e "${YELLOW}⚠️ ТЕСТОВЫЙ РЕЖИМ: результаты будут в output/test/ ⚠️${NC}"
else
    OUTPUT_SITES="output/jsprav.ru.csv"
    OUTPUT_CONTACTS="output/jsprav.ru_contacts.csv"
fi

# Поиск файлов в input/
INPUT_FILES=($(find_input_files))

if [ ${#INPUT_FILES[@]} -eq 0 ]; then
    echo -e "${RED}Не найдено .txt файлов в папке input/${NC}"
    exit 1
fi

echo -e "${GREEN}Найдены файлы:${NC}"
for file in "${INPUT_FILES[@]}"; do
    echo "  - $file"
done

# Проверка зависимостей Python
echo -e "${GREEN}Проверка зависимостей Python...${NC}"
python3 -c "import requests, bs4, lxml" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}Устанавливаем библиотеки...${NC}"
    pip3 install requests beautifulsoup4 lxml
fi

TEMP_CATEGORIES="/tmp/all_categories_$$.txt"

# Объединяем файлы с правильной обработкой строк
echo -e "${GREEN}Объединение файлов с категориями...${NC}"
> "$TEMP_CATEGORIES"

for file in "${INPUT_FILES[@]}"; do
    # Используем read с IFS= для сохранения пробелов и -r для защиты от экранирования
    # Обрабатываем даже строки без перевода в конце
    while IFS= read -r line || [ -n "$line" ]; do
        # Удаляем символы возврата каретки (Windows) и лишние пробелы
        clean_line=$(echo "$line" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        # Пропускаем пустые строки
        if [ -n "$clean_line" ]; then
            # Проверяем, что строка начинается с http:// или https://
            if [[ "$clean_line" =~ ^https?:// ]]; then
                echo "$clean_line" >> "$TEMP_CATEGORIES"
            else
                echo -e "${YELLOW}  Предупреждение: пропущена некорректная строка в $file: $clean_line${NC}"
            fi
        fi
    done < "$file"
    echo -e "  Обработан: $file"
done

# Проверяем, что временный файл не пуст
if [ ! -s "$TEMP_CATEGORIES" ]; then
    echo -e "${RED}Нет корректных URL для обработки!${NC}"
    rm -f "$TEMP_CATEGORIES"
    exit 1
fi

# Удаляем дубликаты и сортируем
sort -u "$TEMP_CATEGORIES" -o "$TEMP_CATEGORIES"
UNIQUE_COUNT=$(wc -l < "$TEMP_CATEGORIES")
echo -e "Всего уникальных категорий для обработки: ${GREEN}$UNIQUE_COUNT${NC}"

# Показываем все категории для информации
echo -e "${BLUE}Категории для обработки:${NC}"
cat "$TEMP_CATEGORIES" | while read -r line; do
    echo "  - $line"
done

# ================================================
# Шаг 1: Сбор списка компаний
# ================================================
print_separator
echo -e "${GREEN}=== Шаг 1: Парсинг каталога jsprav.ru ===${NC}"
echo "Выходной файл: $OUTPUT_SITES"

if [ "$TEST_MODE" = true ]; then
    python3 parser.py "$TEMP_CATEGORIES" "$OUTPUT_SITES" --test --delay 5
else
    python3 parser.py "$TEMP_CATEGORIES" "$OUTPUT_SITES" --delay 30
fi
PARSER_EXIT=$?

rm -f "$TEMP_CATEGORIES"

if [ $PARSER_EXIT -ne 0 ]; then
    echo -e "${RED}Ошибка при выполнении parser.py${NC}"
    exit 1
fi

# Проверка результата
if [ ! -f "$OUTPUT_SITES" ] || [ ! -s "$OUTPUT_SITES" ]; then
    echo -e "${YELLOW}Предупреждение: Файл $OUTPUT_SITES пуст или не создан.${NC}"
    read -p "Продолжить сбор контактов? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi
else
    COUNT=$(tail -n +2 "$OUTPUT_SITES" | wc -l)
    echo -e "${GREEN}Собрано $COUNT компаний из каталога.${NC}"
fi

# ================================================
# Шаг 2: Сбор контактной информации
# ================================================
print_separator
echo -e "${GREEN}=== Шаг 2: Сбор контактной информации с сайтов компаний ===${NC}"
echo "Входной файл: $OUTPUT_SITES"
echo "Выходной файл: $OUTPUT_CONTACTS"

if [ "$TEST_MODE" = true ]; then
    python3 parser_all.py "$OUTPUT_SITES" "$OUTPUT_CONTACTS" "site" --test --delay 0
else
    python3 parser_all.py "$OUTPUT_SITES" "$OUTPUT_CONTACTS" "site" --delay 1
fi
check_error "Ошибка при выполнении parser_all.py"

# Финальная статистика
if [ -f "$OUTPUT_CONTACTS" ]; then
    FINAL_COUNT=$(tail -n +2 "$OUTPUT_CONTACTS" | wc -l)
    print_separator
    echo -e "${GREEN}Готово!${NC}"
    echo -e "${GREEN}Итоговый файл с контактами:${NC} $OUTPUT_CONTACTS"
    echo -e "${GREEN}Всего записей:${NC} $FINAL_COUNT"
    echo -e "${GREEN}Колонки:${NC} name, site, source_url, emails, phones, telegram, whatsapp, vk"
    
    # Вывод статистики
    if [ $FINAL_COUNT -gt 0 ]; then
        EMAIL_COUNT=$(awk -F',' 'NR>1 {gsub(/"/, "", $4); if($4!="") count++} END {print count+0}' "$OUTPUT_CONTACTS")
        PHONE_COUNT=$(awk -F',' 'NR>1 {gsub(/"/, "", $5); if($5!="") count++} END {print count+0}' "$OUTPUT_CONTACTS")
        
        echo -e "${BLUE}Статистика:${NC}"
        echo "  - Найдено email: $EMAIL_COUNT из $FINAL_COUNT"
        echo "  - Найдено телефонов: $PHONE_COUNT из $FINAL_COUNT"
    fi
else
    echo -e "${RED}Ошибка: итоговый файл не создан.${NC}"
    exit 1
fi

print_separator
echo -e "${GREEN}Скрипт успешно завершён!${NC}"