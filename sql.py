import sqlite3
from threading import Lock

# Глобальная блокировка для всех операций с БД
db_lock = Lock()

def safe_db_execute(query, params=(), fetch=False):
    """Потокобезопасное выполнение SQL-запросов"""
    with db_lock:  # Блокируем доступ для других потоков
        try:
            with sqlite3.connect('kosher_bot.db', timeout=30) as conn:
                conn.execute("PRAGMA journal_mode=WAL")  # Включаем WAL-режим
                cursor = conn.cursor()
                cursor.execute(query, params)
                if fetch:
                    return cursor.fetchall()
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"Database error: {str(e)}")
            return False