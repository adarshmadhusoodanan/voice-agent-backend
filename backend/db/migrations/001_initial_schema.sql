-- Migration: 001_initial_schema
-- Creates the core tables for Mykare Voice AI

CREATE TABLE IF NOT EXISTS users (
    phone       TEXT PRIMARY KEY,
    name        TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS appointments (
    id          TEXT PRIMARY KEY,
    phone       TEXT NOT NULL,
    name        TEXT,
    date        TEXT NOT NULL,
    time        TEXT NOT NULL,
    status      TEXT DEFAULT 'booked',
    created_at  TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (phone) REFERENCES users(phone)
);

-- Prevents double-booking while allowing a cancelled slot to be re-booked.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_active_slot
    ON appointments(date, time) WHERE status = 'booked';
