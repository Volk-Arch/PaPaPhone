-- Контакты для голосового телефона.
-- name — отображаемое имя, phone — номер,
-- aliases — JSON-массив вариантов произношения для ASR,
-- is_emergency — экстренный контакт (обзвон + SMS при команде "спасите").

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    aliases TEXT DEFAULT '[]',
    is_emergency INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_contacts_name ON contacts(name);
CREATE INDEX IF NOT EXISTS idx_contacts_phone ON contacts(phone);

-- Журнал звонков
CREATE TABLE IF NOT EXISTS call_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL,
    direction TEXT NOT NULL,  -- 'in' или 'out'
    timestamp TEXT DEFAULT (datetime('now', 'localtime'))
);
