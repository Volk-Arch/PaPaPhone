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
