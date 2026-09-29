-- Mavuno MySQL 8.4 baseline schema.
-- Execute only against an empty application database, then stamp Alembic at
-- revision 0001_identity_baseline when applying this file manually.

SET NAMES utf8mb4;
SET time_zone = '+00:00';

CREATE TABLE roles (
    name VARCHAR(32) NOT NULL,
    description VARCHAR(255) NOT NULL,
    CONSTRAINT pk_roles PRIMARY KEY (name)
) ENGINE = InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

INSERT INTO roles (name, description) VALUES
    ('farmer', 'Lists produce and coordinates fulfilment'),
    ('buyer', 'Discovers and purchases produce'),
    ('administrator', 'Administers the Mavuno platform'),
    ('support', 'Supports users and investigates operational issues');

CREATE TABLE users (
    id BINARY(16) NOT NULL,
    email VARCHAR(320) NULL,
    phone_e164 VARCHAR(16) NULL,
    password_hash VARCHAR(255) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    token_version INT UNSIGNED NOT NULL DEFAULT 0,
    email_verified_at DATETIME(6) NULL,
    phone_verified_at DATETIME(6) NULL,
    last_login_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_users PRIMARY KEY (id),
    CONSTRAINT uq_users_email UNIQUE (email),
    CONSTRAINT uq_users_phone_e164 UNIQUE (phone_e164),
    CONSTRAINT ck_users_identifier_required CHECK (email IS NOT NULL OR phone_e164 IS NOT NULL),
    CONSTRAINT ck_users_status_allowed CHECK (
        status IN ('pending', 'active', 'suspended', 'disabled')
    ),
    INDEX ix_users_status (status)
) ENGINE = InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE user_roles (
    user_id BINARY(16) NOT NULL,
    role_name VARCHAR(32) NOT NULL,
    assigned_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_user_roles PRIMARY KEY (user_id, role_name),
    CONSTRAINT fk_user_roles_user_id_users FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT fk_user_roles_role_name_roles FOREIGN KEY (role_name)
        REFERENCES roles (name) ON DELETE RESTRICT
) ENGINE = InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE profiles (
    user_id BINARY(16) NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    avatar_object_key VARCHAR(512) NULL,
    locale VARCHAR(16) NOT NULL DEFAULT 'en-KE',
    bio TEXT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_profiles PRIMARY KEY (user_id),
    CONSTRAINT fk_profiles_user_id_users FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE farmer_profiles (
    user_id BINARY(16) NOT NULL,
    farm_name VARCHAR(160) NULL,
    county VARCHAR(80) NULL,
    verification_status VARCHAR(16) NOT NULL DEFAULT 'unverified',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_farmer_profiles PRIMARY KEY (user_id),
    CONSTRAINT fk_farmer_profiles_user_id_users FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT ck_farmer_profiles_verification_status_allowed CHECK (
        verification_status IN ('unverified', 'pending', 'verified', 'rejected')
    )
) ENGINE = InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE buyer_profiles (
    user_id BINARY(16) NOT NULL,
    organization_name VARCHAR(160) NULL,
    buyer_type VARCHAR(16) NOT NULL DEFAULT 'individual',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_buyer_profiles PRIMARY KEY (user_id),
    CONSTRAINT fk_buyer_profiles_user_id_users FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT ck_buyer_profiles_buyer_type_allowed CHECK (
        buyer_type IN ('individual', 'business', 'institution')
    )
) ENGINE = InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE addresses (
    id BINARY(16) NOT NULL,
    user_id BINARY(16) NOT NULL,
    label VARCHAR(80) NOT NULL,
    line_1 VARCHAR(255) NOT NULL,
    line_2 VARCHAR(255) NULL,
    locality VARCHAR(120) NOT NULL,
    county VARCHAR(80) NOT NULL,
    postal_code VARCHAR(20) NULL,
    country_code VARCHAR(2) NOT NULL DEFAULT 'KE',
    latitude DECIMAL(10, 7) NULL,
    longitude DECIMAL(10, 7) NULL,
    delivery_notes VARCHAR(500) NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_addresses PRIMARY KEY (id),
    CONSTRAINT fk_addresses_user_id_users FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT ck_addresses_latitude_range CHECK (latitude BETWEEN -90 AND 90),
    CONSTRAINT ck_addresses_longitude_range CHECK (longitude BETWEEN -180 AND 180),
    INDEX ix_addresses_user_id (user_id)
) ENGINE = InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE device_installations (
    id BINARY(16) NOT NULL,
    user_id BINARY(16) NOT NULL,
    installation_id BINARY(16) NOT NULL,
    platform VARCHAR(16) NOT NULL,
    push_token_ciphertext VARBINARY(1024) NULL,
    push_token_hash BINARY(32) NULL,
    last_seen_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    revoked_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_device_installations PRIMARY KEY (id),
    CONSTRAINT uq_device_installations_installation_id UNIQUE (installation_id),
    CONSTRAINT uq_device_installations_push_token_hash UNIQUE (push_token_hash),
    CONSTRAINT fk_device_installations_user_id_users FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT ck_device_installations_platform_allowed CHECK (
        platform IN ('android', 'ios', 'web')
    ),
    INDEX ix_device_installations_user_id (user_id)
) ENGINE = InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE refresh_tokens (
    id BINARY(16) NOT NULL,
    user_id BINARY(16) NOT NULL,
    device_installation_id BINARY(16) NULL,
    family_id BINARY(16) NOT NULL,
    token_hash BINARY(32) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    rotated_at DATETIME(6) NULL,
    revoked_at DATETIME(6) NULL,
    replaced_by_id BINARY(16) NULL,
    CONSTRAINT pk_refresh_tokens PRIMARY KEY (id),
    CONSTRAINT uq_refresh_tokens_token_hash UNIQUE (token_hash),
    CONSTRAINT fk_refresh_tokens_user_id_users FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT fk_refresh_tokens_device_installation_id_device_installations
        FOREIGN KEY (device_installation_id) REFERENCES device_installations (id) ON DELETE SET NULL,
    CONSTRAINT fk_refresh_tokens_replaced_by_id_refresh_tokens FOREIGN KEY (replaced_by_id)
        REFERENCES refresh_tokens (id) ON DELETE SET NULL,
    INDEX ix_refresh_tokens_user_id (user_id),
    INDEX ix_refresh_tokens_family_id (family_id),
    INDEX ix_refresh_tokens_expires_at (expires_at)
) ENGINE = InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
