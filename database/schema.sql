-- FACEIT Bot Database Schema
-- Simple schema for basic functionality

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    user_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    faceit_player_id VARCHAR(255),
    faceit_nickname VARCHAR(255),
    linked_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- User subscriptions
CREATE TABLE IF NOT EXISTS user_subscriptions (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    tier VARCHAR(50) DEFAULT 'FREE',
    requests_used INTEGER DEFAULT 0,
    requests_limit INTEGER DEFAULT 20,
    expires_at TIMESTAMP,
    referred_by BIGINT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- User settings
CREATE TABLE IF NOT EXISTS user_settings (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    notifications_enabled BOOLEAN DEFAULT TRUE,
    language VARCHAR(10) DEFAULT 'ru',
    timezone VARCHAR(50) DEFAULT 'Europe/Moscow',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id);
CREATE INDEX IF NOT EXISTS idx_users_faceit_player_id ON users(faceit_player_id);
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_user_id ON user_subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_settings_user_id ON user_settings(user_id);

-- Create a trigger to update the updated_at column
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Add triggers to all tables
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_subscriptions_updated_at BEFORE UPDATE ON user_subscriptions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_settings_updated_at BEFORE UPDATE ON user_settings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert default subscriptions for existing users
INSERT INTO user_subscriptions (user_id, tier, requests_used, requests_limit)
SELECT user_id, 'FREE', 0, 20 
FROM users 
WHERE user_id NOT IN (SELECT user_id FROM user_subscriptions)
ON CONFLICT DO NOTHING;

-- Insert default settings for existing users  
INSERT INTO user_settings (user_id)
SELECT user_id
FROM users 
WHERE user_id NOT IN (SELECT user_id FROM user_settings)
ON CONFLICT DO NOTHING;