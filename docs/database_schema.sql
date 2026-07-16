-- WE_OWE Sprint 1 database design
-- The running application creates these tables through SQLAlchemy models.

CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_confirmed BOOLEAN NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL
);

CREATE TABLE groups (
    id INTEGER PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    description VARCHAR(500),
    owner_id INTEGER NOT NULL,
    created_at DATETIME NOT NULL,
    CONSTRAINT uq_owner_group_name UNIQUE (owner_id, name),
    FOREIGN KEY (owner_id) REFERENCES users(id)
);

CREATE TABLE memberships (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'member',
    joined_at DATETIME NOT NULL,
    CONSTRAINT uq_user_group UNIQUE (user_id, group_id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (group_id) REFERENCES groups(id)
);

CREATE TABLE invitations (
    id INTEGER PRIMARY KEY,
    group_id INTEGER NOT NULL,
    email VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'member',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    invited_by_id INTEGER,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (group_id) REFERENCES groups(id),
    FOREIGN KEY (invited_by_id) REFERENCES users(id)
);

CREATE TABLE expenses (
    id INTEGER PRIMARY KEY,
    group_id INTEGER NOT NULL,
    paid_by_id INTEGER NOT NULL,
    title VARCHAR(120) NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    category VARCHAR(50) NOT NULL,
    expense_date DATE NOT NULL,
    notes VARCHAR(500),
    receipt_filename VARCHAR(255),
    receipt_original_name VARCHAR(255),
    split_method VARCHAR(20) NOT NULL DEFAULT 'equal',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY (group_id) REFERENCES groups(id),
    FOREIGN KEY (paid_by_id) REFERENCES users(id)
);

CREATE TABLE expense_splits (
    id INTEGER PRIMARY KEY,
    expense_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    input_value NUMERIC(12, 4),
    CONSTRAINT uq_expense_split_user UNIQUE (expense_id, user_id),
    FOREIGN KEY (expense_id) REFERENCES expenses(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
