CREATE TABLE customer_profiles (
    resource_id TEXT PRIMARY KEY,
    user_id TEXT,
    email TEXT,
    origin_system TEXT,
    account_status TEXT
);
INSERT INTO customer_profiles VALUES
    ('account_7102', 'user_9907', 'tarin.morrow@fablemail.test', 'account_service', 'active');
