import sqlite3
import os
import time

DB_NAME = "tamagochi.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Таблица пользователей с поддержкой уровней, XP и локаций
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            pet_name TEXT,
            pet_gender TEXT,
            pet_type TEXT,
            egg_type TEXT,
            diamonds INTEGER DEFAULT 15,
            level INTEGER DEFAULT 1,
            xp INTEGER DEFAULT 0,
            location TEXT DEFAULT 'city',
            current_task INTEGER DEFAULT 0,
            inventory TEXT DEFAULT '',
            last_daily INTEGER DEFAULT 0,
            daily_streak INTEGER DEFAULT 0
        )
    ''')
    
    # Таблица для динамических показателей питомца
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pet_stats (
            user_id INTEGER PRIMARY KEY,
            hunger INTEGER DEFAULT 100,
            mood INTEGER DEFAULT 100,
            energy INTEGER DEFAULT 100,
            health INTEGER DEFAULT 100,
            last_update INTEGER DEFAULT 0
        )
    ''')
    
    conn.commit()
    conn.close()

def create_user(user_id, username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)', (user_id, username))
    cursor.execute('INSERT OR IGNORE INTO pet_stats (user_id, last_update) VALUES (?, ?)', (user_id, int(time.time())))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def update_user_pet_info(user_id, pet_name, pet_gender, pet_type, egg_type):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users 
        SET pet_name = ?, pet_gender = ?, pet_type = ?, egg_type = ? 
        WHERE user_id = ?
    ''', (pet_name, pet_gender, pet_type, egg_type, user_id))
    conn.commit()
    conn.close()

def get_stats(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM pet_stats WHERE user_id = ?', (user_id,))
    stats = cursor.fetchone()
    conn.close()
    return dict(stats) if stats else {"hunger": 100, "mood": 100, "energy": 100, "health": 100}

def update_stat(user_id, stat_name, amount):
    user_cols = ['diamonds', 'level', 'xp', 'location', 'current_task']
    stat_cols = ['hunger', 'mood', 'energy', 'health']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if stat_name in user_cols:
        if stat_name in ['diamonds', 'level', 'xp', 'current_task']:
            cursor.execute(f'UPDATE users SET {stat_name} = ? WHERE user_id = ?', (amount, user_id))
        else:
            cursor.execute(f'UPDATE users SET {stat_name} = ? WHERE user_id = ?', (str(amount), user_id))
    elif stat_name in stat_cols:
        current = get_stats(user_id).get(stat_name, 100)
        new_val = max(0, min(100, current + amount if isinstance(amount, int) and stat_name != 'set' else amount))
        cursor.execute(f'UPDATE pet_stats SET {stat_name} = ?, last_update = ? WHERE user_id = ?', (new_val, int(time.time()), user_id))
        
    conn.commit()
    conn.close()

def add_diamonds(user_id, amount):
    user = get_user(user_id)
    if user:
        new_diamonds = max(0, user['diamonds'] + amount)
        update_stat(user_id, 'diamonds', new_diamonds)

def remove_diamonds(user_id, amount):
    user = get_user(user_id)
    if user and user['diamonds'] >= amount:
        new_diamonds = user['diamonds'] - amount
        update_stat(user_id, 'diamonds', new_diamonds)
        return True
    return False

def transfer_diamonds(sender_id, receiver_id, amount):
    if amount <= 0:
        return False, "❌ Сумма перевода должна быть больше 0!"
    
    sender = get_user(sender_id)
    if not sender or sender['diamonds'] < amount:
        return False, "❌ Недостаточно алмазов для перевода!"
        
    receiver = get_user(receiver_id)
    if not receiver:
        return False, "❌ Игрок с таким ID не зарегистрирован в боте!"
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE users SET diamonds = diamonds - ? WHERE user_id = ?', (amount, sender_id))
        cursor.execute('UPDATE users SET diamonds = diamonds + ? WHERE user_id = ?', (amount, receiver_id))
        conn.commit()
        return True, f"✅ Вы успешно подарили {amount}💎 игроку с ID `{receiver_id}`!"
    except Exception as e:
        conn.rollback()
        return False, "❌ Произошла ошибка при выполнении транзакции."
    finally:
        conn.close()

def add_item_to_inventory(user_id, item_name):
    user = get_user(user_id)
    if not user: return
    current_inv = user.get('inventory', '')
    if current_inv:
        new_inv = f"{current_inv},{item_name}"
    else:
        new_inv = item_name
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET inventory = ? WHERE user_id = ?', (new_inv, user_id))
    conn.commit()
    conn.close()

def next_task(user_id):
    user = get_user(user_id)
    if user:
        update_stat(user_id, 'current_task', user['current_task'] + 1)

def get_top_users(limit=10):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, diamonds, level FROM users ORDER BY diamonds DESC LIMIT ?', (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_all_stats(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT last_update FROM pet_stats WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    if not row: return
    
    last_update = row[0]
    now = int(time.time())
    diff = now - last_update
    
    if diff > 60:
        intervals = diff // 60
        cursor.execute('''
            UPDATE pet_stats 
            SET hunger = MAX(0, hunger - ?), 
                mood = MAX(0, mood - ?), 
                energy = MAX(0, energy - ?),
                last_update = ? 
            WHERE user_id = ?
        ''', (intervals * 2, intervals * 1, intervals * 1, now, user_id))
        conn.commit()
    conn.close()
