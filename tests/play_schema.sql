-- Schema `play`: cross-game play sessions and events. Applied by remote.sh provision_db as the superuser,
-- after the per-app roles exist. Idempotent. Each game writes its own rows (row-level security on `writer`);
-- Nova's game reporter reads everything through the read-only LAN role `play_reader`.
--
-- A session is FINISHED when ended_at is set. A session whose last_seen_at is older than the reader's idle
-- threshold and ended_at is NULL was abandoned (app quit, tab closed). Otherwise it is in progress.
DO $$BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='play_owner') THEN CREATE ROLE play_owner NOLOGIN; END IF; END$$;
ALTER ROLE play_owner WITH NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

CREATE SCHEMA IF NOT EXISTS play AUTHORIZATION play_owner;
REVOKE ALL ON SCHEMA play FROM PUBLIC;

CREATE TABLE IF NOT EXISTS play.sessions (
  id           uuid        PRIMARY KEY,
  game         text        NOT NULL CHECK (game ~ '^[a-z0-9][a-z0-9_-]{0,31}$'),
  client       text        NOT NULL CHECK (client ~ '^[a-z0-9][a-z0-9_.-]{0,31}$'),
  player       text        NOT NULL CHECK (char_length(player) BETWEEN 1 AND 64),
  writer       name        NOT NULL DEFAULT current_user,
  started_at   timestamptz NOT NULL,
  last_seen_at timestamptz NOT NULL,
  ended_at     timestamptz,
  outcome      text        CHECK (char_length(outcome) <= 64),
  score        double precision CHECK (score IS NULL OR score BETWEEN -1e12 AND 1e12),
  actions      integer     NOT NULL DEFAULT 0 CHECK (actions BETWEEN 0 AND 10000000),
  summary      jsonb       NOT NULL DEFAULT '{}'::jsonb
               CHECK (jsonb_typeof(summary) = 'object' AND octet_length(summary::text) <= 65536),
  created_at   timestamptz NOT NULL DEFAULT now(),
  CHECK (last_seen_at >= started_at),
  CHECK (ended_at IS NULL OR ended_at >= started_at)
);
CREATE INDEX IF NOT EXISTS sessions_ended_idx ON play.sessions (ended_at);
CREATE INDEX IF NOT EXISTS sessions_open_seen_idx ON play.sessions (last_seen_at) WHERE ended_at IS NULL;
CREATE INDEX IF NOT EXISTS sessions_game_player_idx ON play.sessions (game, player, started_at DESC);

CREATE TABLE IF NOT EXISTS play.events (
  session_id uuid        NOT NULL REFERENCES play.sessions (id) ON DELETE CASCADE,
  seq        integer     NOT NULL CHECK (seq BETWEEN 0 AND 10000000),
  ts         timestamptz NOT NULL,
  kind       text        NOT NULL CHECK (kind ~ '^[a-z0-9][a-z0-9_.-]{0,47}$'),
  detail     jsonb       NOT NULL DEFAULT '{}'::jsonb
             CHECK (jsonb_typeof(detail) = 'object' AND octet_length(detail::text) <= 4096),
  writer     name        NOT NULL DEFAULT current_user,
  PRIMARY KEY (session_id, seq)
);

ALTER TABLE play.sessions OWNER TO play_owner;
ALTER TABLE play.events OWNER TO play_owner;
ALTER TABLE play.sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE play.events ENABLE ROW LEVEL SECURITY;

-- Writers: each game's DML role, plus blompie_mac (the standalone Blompie Mac app: play rows only, no schema). Insert and update only their own rows; no DELETE (history is kept).
GRANT USAGE ON SCHEMA play TO gtnw, cartest, blompie, mush, saves, blompie_mac;
REVOKE ALL ON play.sessions, play.events FROM gtnw, cartest, blompie, mush, saves, blompie_mac;
GRANT SELECT, INSERT, UPDATE ON play.sessions, play.events TO gtnw, cartest, blompie, mush, saves, blompie_mac;
DROP POLICY IF EXISTS own_rows ON play.sessions;
CREATE POLICY own_rows ON play.sessions FOR ALL TO gtnw, cartest, blompie, mush, saves, blompie_mac
  USING (writer = current_user) WITH CHECK (writer = current_user);
DROP POLICY IF EXISTS own_rows ON play.events;
CREATE POLICY own_rows ON play.events FOR ALL TO gtnw, cartest, blompie, mush, saves, blompie_mac
  USING (writer = current_user) WITH CHECK (writer = current_user);

-- Reader: Nova's game reporter. Read-only, play schema only.
DO $$BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='play_reader') THEN CREATE ROLE play_reader LOGIN; END IF; END$$;
GRANT CONNECT ON DATABASE games TO play_reader;
GRANT USAGE ON SCHEMA play TO play_reader;
REVOKE ALL ON play.sessions, play.events FROM play_reader;
GRANT SELECT ON play.sessions, play.events TO play_reader;
DROP POLICY IF EXISTS read_all ON play.sessions;
CREATE POLICY read_all ON play.sessions FOR SELECT TO play_reader USING (true);
DROP POLICY IF EXISTS read_all ON play.events;
CREATE POLICY read_all ON play.events FOR SELECT TO play_reader USING (true);
