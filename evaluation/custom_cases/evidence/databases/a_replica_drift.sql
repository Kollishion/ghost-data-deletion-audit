-- point-in-time database snapshot: custom synthetic test data
CREATE TABLE customer_profiles (
    resource_id TEXT PRIMARY KEY,
    user_id TEXT,
    email TEXT,
    origin_system TEXT,
    account_status TEXT
);
CREATE TABLE failover_customer_profiles (
    resource_id TEXT PRIMARY KEY,
    user_id TEXT,
    email TEXT,
    origin_system TEXT,
    account_status TEXT
);
INSERT INTO failover_customer_profiles VALUES
    ('account_7101', 'user_9901', 'mira.vellin@fablemail.test', 'account_service', 'active');
