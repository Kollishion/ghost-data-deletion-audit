CREATE TABLE customer_profiles (
    resource_id TEXT PRIMARY KEY,
    user_id TEXT,
    email TEXT,
    origin_system TEXT,
    account_status TEXT
);
INSERT INTO customer_profiles VALUES
    ('account_7103', 'user_9908', 'elvi.sable@fablemail.test', 'account_service', 'active');
