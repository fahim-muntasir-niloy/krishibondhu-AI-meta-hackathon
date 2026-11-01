-- KrishiBondhu.AI app schema. Idempotent: `krishi-db migrate` runs it on every
-- deploy, as the login role (the owner of these tables).
--
-- Per-farmer isolation: the app connects as krishi_app (db.py), which row-level
-- security applies to. Each farmer-owned table has one policy: a row is visible
-- and writable only when its phone equals the transaction's `app.phone`. With
-- `app.phone` unset, current_setting(..., true) is NULL and nothing matches.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'krishi_app') THEN
        CREATE ROLE krishi_app NOLOGIN NOBYPASSRLS;
    END IF;
END
$$;
-- The login role switches to it (SET ROLE) on every pooled connection.
GRANT krishi_app TO CURRENT_USER;

-- ---------------------------------------------------------------------------
-- Farmers and what they own
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS farmers (
    phone       text PRIMARY KEY,               -- E.164, the identity (X-Phone-Number)
    name        text,
    area        text,                            -- village / union / upazila, free text
    district    text,                            -- "বগুড়া (Bogura)", as the web profile sends it
    division    text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS crop_cases (
    id          text PRIMARY KEY,
    phone       text NOT NULL REFERENCES farmers ON DELETE CASCADE,
    data        jsonb NOT NULL,                  -- the whole case (cases.py)
    updated_at  timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS crop_cases_phone ON crop_cases (phone, updated_at DESC);

CREATE TABLE IF NOT EXISTS images (
    name        text PRIMARY KEY,                -- <random hex>.jpg
    phone       text NOT NULL REFERENCES farmers ON DELETE CASCADE,
    thread_id   text,
    labels      jsonb NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS images_phone ON images (phone, created_at DESC);
-- Lesion share of the leaf, measured from SAM's masks (tools/segment.py); cases refer to it by image name.
ALTER TABLE images ADD COLUMN IF NOT EXISTS measurement jsonb;
-- Where the file is (Vercel Blob). NULL: an older photo, in MEDIA_DIR under its name.
ALTER TABLE images ADD COLUMN IF NOT EXISTS url text;
ALTER TABLE images ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'annotated';  -- annotated | upload | card

-- The sidebar's conversations. Their messages are the checkpointer's, under the same id.
CREATE TABLE IF NOT EXISTS threads (
    thread_id   text PRIMARY KEY,
    phone       text NOT NULL REFERENCES farmers ON DELETE CASCADE,
    title       text,
    pinned      boolean NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS threads_phone ON threads (phone, pinned DESC, updated_at DESC);

-- ---------------------------------------------------------------------------
-- Officers (seeded roster, public) and bookings with them
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS officers (
    id              text PRIMARY KEY,
    name_bn         text NOT NULL,
    designation_bn  text NOT NULL,
    designation_en  text NOT NULL,
    phone           text NOT NULL,
    division        text NOT NULL,               -- English, as in bd-locations.ts
    district        text NOT NULL,
    district_bn     text NOT NULL,
    office_bn       text NOT NULL,
    active          boolean NOT NULL DEFAULT true
);
CREATE INDEX IF NOT EXISTS officers_district ON officers (lower(district));

CREATE TABLE IF NOT EXISTS bookings (
    id              text PRIMARY KEY,
    phone           text NOT NULL REFERENCES farmers ON DELETE CASCADE,
    officer_id      text NOT NULL REFERENCES officers,
    case_id         text REFERENCES crop_cases ON DELETE SET NULL,
    thread_id       text,
    session_type    text NOT NULL CHECK (session_type IN ('phone_call', 'field_visit', 'office_visit')),
    starts_at       timestamptz NOT NULL,
    ends_at         timestamptz NOT NULL,
    status          text NOT NULL CHECK (status IN ('confirmed', 'cancelled', 'completed')),
    issue_summary   text NOT NULL,
    location        text NOT NULL DEFAULT '',
    activity        jsonb NOT NULL DEFAULT '[]',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS bookings_phone ON bookings (phone, starts_at);
-- One confirmed booking per officer per slot, across all farmers: enforced even
-- though RLS hides other farmers' bookings from the app.
CREATE UNIQUE INDEX IF NOT EXISTS bookings_officer_slot ON bookings (officer_id, starts_at) WHERE status = 'confirmed';

-- When an officer is busy, without saying with whom: lets a farmer see free
-- slots although RLS hides other farmers' bookings.
CREATE OR REPLACE FUNCTION officer_busy(p_officer text, p_from timestamptz, p_to timestamptz)
RETURNS SETOF timestamptz
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT starts_at FROM bookings
    WHERE officer_id = p_officer AND status = 'confirmed' AND starts_at >= p_from AND starts_at < p_to
$$;
REVOKE ALL ON FUNCTION officer_busy(text, timestamptz, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION officer_busy(text, timestamptz, timestamptz) TO krishi_app;

-- ---------------------------------------------------------------------------
-- Row-level security
-- ---------------------------------------------------------------------------
ALTER TABLE farmers    ENABLE ROW LEVEL SECURITY;
ALTER TABLE crop_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE images     ENABLE ROW LEVEL SECURITY;
ALTER TABLE threads    ENABLE ROW LEVEL SECURITY;
ALTER TABLE bookings   ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS own_rows ON farmers;
CREATE POLICY own_rows ON farmers TO krishi_app
    USING (phone = current_setting('app.phone', true))
    WITH CHECK (phone = current_setting('app.phone', true));
DROP POLICY IF EXISTS own_rows ON crop_cases;
CREATE POLICY own_rows ON crop_cases TO krishi_app
    USING (phone = current_setting('app.phone', true))
    WITH CHECK (phone = current_setting('app.phone', true));
DROP POLICY IF EXISTS own_rows ON images;
CREATE POLICY own_rows ON images TO krishi_app
    USING (phone = current_setting('app.phone', true))
    WITH CHECK (phone = current_setting('app.phone', true));
DROP POLICY IF EXISTS own_rows ON threads;
CREATE POLICY own_rows ON threads TO krishi_app
    USING (phone = current_setting('app.phone', true))
    WITH CHECK (phone = current_setting('app.phone', true));
DROP POLICY IF EXISTS own_rows ON bookings;
CREATE POLICY own_rows ON bookings TO krishi_app
    USING (phone = current_setting('app.phone', true))
    WITH CHECK (phone = current_setting('app.phone', true));

GRANT SELECT, INSERT, UPDATE, DELETE ON farmers, crop_cases, images, threads, bookings TO krishi_app;
GRANT SELECT ON officers TO krishi_app;
-- Conversation checkpoints (checkpointer.py) get no grant: the app role cannot read them.
