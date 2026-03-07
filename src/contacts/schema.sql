-- Контакты для голосового телефона.
-- name — основное отображаемое имя, phone — номер, aliases — JSON-массив вариантов произношения для ASR.

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    aliases TEXT DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_contacts_name ON contacts(name);
CREATE INDEX IF NOT EXISTS idx_contacts_phone ON contacts(phone);

-- Тестовый контакт для проверки голосового поиска.
-- OR IGNORE: не дублируется если уже есть (PRIMARY KEY = 1).
INSERT OR IGNORE INTO contacts (id, name, phone, aliases)
VALUES (1, 'Тест', '+79161234567', '[]');
