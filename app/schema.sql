CREATE TABLE IF NOT EXISTS Users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    language_preference TEXT DEFAULT 'en'
);

CREATE TABLE IF NOT EXISTS Favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    embedding TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, name),
    FOREIGN KEY (user_id) REFERENCES Users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS FavoritePapers (
    favorite_id INTEGER NOT NULL,
    paper_id TEXT NOT NULL,
    PRIMARY KEY (favorite_id, paper_id),
    FOREIGN KEY (favorite_id) REFERENCES Favorites (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS BrowsingHistory (
    user_id INTEGER NOT NULL,
    paper_id TEXT NOT NULL,
    date DATE NOT NULL,
    position INTEGER,
    PRIMARY KEY (user_id, date),
    FOREIGN KEY (user_id) REFERENCES Users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS UserFilters (
    user_id INTEGER PRIMARY KEY,
    categories TEXT,
    tags TEXT,
    sim_favorites TEXT,
    last_date TEXT,
    last_paper_id TEXT,
    last_position INTEGER,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES Users (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_favorites_user_id ON Favorites (user_id);
CREATE INDEX IF NOT EXISTS idx_history_user_date ON BrowsingHistory (user_id, date);
