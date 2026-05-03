CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

CREATE TABLE payers (
  id           SERIAL PRIMARY KEY,
  slug         VARCHAR(32)  NOT NULL UNIQUE,
  name         VARCHAR(128) NOT NULL,
  short_name   VARCHAR(32)  NOT NULL,
  color_hex    VARCHAR(7),
  portal_url   TEXT,
  is_active    BOOLEAN      NOT NULL DEFAULT true,
  created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

INSERT INTO payers (slug, name, short_name, color_hex, portal_url) VALUES
  ('uhc',   'UnitedHealthcare',       'UHC',   '#003087', 'https://www.uhcprovider.com/en/prior-auth-advance-notification.html'),
  ('aetna', 'Aetna',                  'Aetna', '#7b1a1a', 'https://www.aetna.com/health-care-professionals/precertification/precertification-lists.html'),
  ('bcbs',  'Blue Cross Blue Shield', 'BCBS',  '#009fdb', 'https://www.bcbs.com/providers');

CREATE TABLE cpt_codes (
  id           SERIAL PRIMARY KEY,
  code         VARCHAR(8)   NOT NULL UNIQUE,
  description  TEXT         NOT NULL,
  specialty    VARCHAR(128),
  category     VARCHAR(64),
  is_active    BOOLEAN      NOT NULL DEFAULT true,
  created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE plan_types (
  id    SERIAL PRIMARY KEY,
  slug  VARCHAR(32) NOT NULL UNIQUE,
  label VARCHAR(64) NOT NULL
);

INSERT INTO plan_types (slug, label) VALUES
  ('commercial', 'Commercial'),
  ('medicare',   'Medicare Advantage'),
  ('medicaid',   'Medicaid / Community Plan'),
  ('exchange',   'Exchange / Marketplace');

CREATE TABLE pa_rules (
  id                UUID        NOT NULL DEFAULT uuid_generate_v4() PRIMARY KEY,
  cpt_id            INT         NOT NULL REFERENCES cpt_codes(id) ON DELETE CASCADE,
  payer_id          INT         NOT NULL REFERENCES payers(id)    ON DELETE CASCADE,
  plan_type_id      INT         NOT NULL REFERENCES plan_types(id) ON DELETE CASCADE,
  state             CHAR(2),
  status            VARCHAR(16) NOT NULL CHECK (status IN ('required','not_required','conditional','na')),
  notes             TEXT,
  turnaround_days   VARCHAR(32),
  submission_portal VARCHAR(128),
  source_url        TEXT,
  source_type       VARCHAR(32),
  confidence        SMALLINT,
  is_active         BOOLEAN     NOT NULL DEFAULT true,
  scraped_at        TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (cpt_id, payer_id, plan_type_id, state)
);

CREATE TABLE pa_rule_changelog (
  id             SERIAL      PRIMARY KEY,
  pa_rule_id     UUID        NOT NULL REFERENCES pa_rules(id) ON DELETE CASCADE,
  changed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  changed_by     VARCHAR(64) NOT NULL DEFAULT 'scraper',
  old_status     VARCHAR(16),
  new_status     VARCHAR(16),
  old_notes      TEXT,
  new_notes      TEXT,
  old_turnaround VARCHAR(32),
  new_turnaround VARCHAR(32)
);

CREATE TABLE scraper_runs (
  id              SERIAL      PRIMARY KEY,
  payer_id        INT         REFERENCES payers(id),
  started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at    TIMESTAMPTZ,
  status          VARCHAR(16),
  codes_found     INT         DEFAULT 0,
  codes_added     INT         DEFAULT 0,
  codes_updated   INT         DEFAULT 0,
  codes_unchanged INT         DEFAULT 0,
  error_message   TEXT,
  source_url      TEXT
);

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_pa_rules_updated
  BEFORE UPDATE ON pa_rules FOR EACH ROW EXECUTE FUNCTION update_updated_at();
