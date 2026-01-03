import requests
from bs4 import BeautifulSoup
import time
import re
from datetime import datetime
import json
import os


CHECK_FILE = 'flru_last_projects.json'
log_time = lambda: datetime.now().strftime('%H:%M:%S')

TELEGRAM_TOKEN = "8377039422:AAGyRkbIFZrrelhKIC8_hRMRSGOlvEIQK7Y"
TELEGRAM_CHAT_ID = 440532768


def log(message):
    print(f"[{log_time()}] {message}")


def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, data=data, timeout=10)
        if r.status_code != 200:
            log(f"⚠️ Ошибка Telegram: {r.status_code} {r.text[:200]}")
        else:
            log("📨 Сообщение отправлено в Telegram")
    except Exception as e:
        log(f"❌ Ошибка запроса к Telegram: {e}")


def load_last_projects():
    log("📂 Загрузка списка проверенных проектов...")
    if os.path.exists(CHECK_FILE):
        try:
            with open(CHECK_FILE, 'r', encoding='utf-8') as f:
                projects = set(json.load(f))
            log(f"✅ Загружено {len(projects)} старых ссылок")
            return projects
        except Exception as e:
            log(f"❌ Ошибка загрузки файла: {e}")
            return set()
    log("📂 Файл ссылок не найден, начинаем с чистого листа")
    return set()


def save_projects(projects):
    try:
        with open(CHECK_FILE, 'w', encoding='utf-8') as f:
            json.dump(list(projects), f, ensure_ascii=False, indent=2)
        log(f"💾 Сохранено {len(projects)} ссылок в {CHECK_FILE}")
    except Exception as e:
        log(f"❌ Ошибка сохранения: {e}")


def parse_flru_projects():
    log("🌐 Запрос ко ВСЕМ страницам https://www.fl.ru/projects/?kind=1")
    base_url = 'https://www.fl.ru/projects/?kind=1&page='
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    all_projects = []
    seen_links = load_last_projects()
    total_checked = 0
    page_num = 1
    
    while True:
        log(f"📄 Парсим страницу {page_num}...")
        url = f"{base_url}{page_num}"
        
        try:
            response = requests.get(url, headers=headers, timeout=15)
            
            # Если страница пуста (404 или очень короткая) — останавливаемся
            if response.status_code != 200 or len(response.content) < 5000:
                log(f"📄 Страница {page_num} пуста или недоступна (статус: {response.status_code}) — останавливаемся")
                break
                
            soup = BeautifulSoup(response.content, 'html.parser')
            # Ищем блоки проектов по новой структуре
            posts = (soup.find_all('div', {'data-id': re.compile(r'qa-lenta-.*')}) or 
                     soup.find_all('div', class_=re.compile(r'b-post')))
            
            if not posts:
                log(f"📄 Страница {page_num}: проектов не найдено — останавливаемся")
                break
            
            log(f"📋 Страница {page_num}: найдено {len(posts)} проектов")
            
            page_projects = []
            page_checked = 0
            
            for i, item in enumerate(posts, 1):
                # Заголовок в h2
                title_elem = item.find('h2', class_='b-post__title') or item.find('h2', class_=re.compile(r'text-h5'))
                link_elem = title_elem.find('a') if title_elem else None
                
                # Описание - несколько вариантов селекторов
                desc_elem = (item.find('div', class_='b-post__txt') or 
                             item.find('div', class_=re.compile(r'text-5')) or 
                             item.find('div', class_='b-post__body') or
                             item.find('div', string=re.compile(r'.{20,}')))

                if not link_elem or not desc_elem:
                    continue
                    
                page_checked += 1
                total_checked += 1
                title = link_elem.get_text(strip=True)
                description_full = desc_elem.get_text(strip=True)
                description = description_full.lower()
                link = 'https://www.fl.ru' + link_elem.get('href')
                
                # Логирование (немного ограниченное, чтобы логи cron не пухли)
                if page_num == 1 and i <= 10:
                    log(f"🔍 [1-{i}/{len(posts)}] '{title[:50]}...'")
                elif total_checked % 30 == 0:
                    log(f"🔍 [{total_checked} всего] '{title[:50]}...'")
                
                # Ищем ключевые слова (amoCRM, Bitrix24, 1C и др.)
                if (
                    link not in seen_links and 
                    re.search(r'amocrm|amo crm|amo-crm|bitrix24?|1c|amo|битрикс', description, re.IGNORECASE)
                ):
                    log(f"🎉 НАЙДЕН! Страница {page_num}, проект {i}: '{title[:50]}...' → {link}")
                    page_projects.append({
                        'title': title,
                        'link': link,
                        'description': description_full[:400],
                        'time': datetime.now().strftime('%H:%M %d.%m.%Y'),
                        'page': page_num
                    })
                    seen_links.add(link)
            
            all_projects.extend(page_projects)
            log(f"📊 Страница {page_num}: проверено {page_checked}, новых: {len(page_projects)}")
            
            # Если проектов мало — вероятно последняя страница
            if len(posts) < 20:
                log(f"📄 Страница {page_num} почти пуста — останавливаемся")
                break
                
            page_num += 1
            time.sleep(1)  # Задержка 1 сек между страницами (антибан)
            
        except requests.exceptions.RequestException as e:
            log(f"🌐 Ошибка страницы {page_num}: {e}")
            break
    
    log(f"📊 ВСЕГО: проверено {total_checked} проектов на {page_num-1} страницах, новых: {len(all_projects)}")
    save_projects(seen_links)
    return all_projects


def main():
    print("🚀 Запуск парсера FL.ru (разовый запуск)")
    start_time = datetime.now()
    
    new_projects = parse_flru_projects()
    
    if new_projects:
        # Собираем одно или несколько сообщений, чтобы не спамить
        chunks = []
        for p in new_projects:
            part = (
                f"📋 <b>{p['title']}</b>\n"
                f"🔗 <a href=\"{p['link']}\">Ссылка</a> (стр. {p['page']})\n"
                f"💬 {p['description']}\n"
                f"⏰ {p['time']}\n"
                "───────────────\n"
            )
            chunks.append(part)
        
        current = ""
        for part in chunks:
            if len(current) + len(part) > 3800:  # запас до лимита 4096
                send_telegram(current)
                current = ""
                time.sleep(1)
            current += part
        if current:
            send_telegram(current)
        
        log(f"✅ Найдено {len(new_projects)} новых проектов и отправлено в Telegram")
    else:
        elapsed = (datetime.now() - start_time).total_seconds()
        log(f"✅ Новых заказов нет (запуск занял {elapsed:.1f}с)")


if __name__ == "__main__":
    main()
