"""
Throwaway Postgres cluster for integration tests.

Uses PG_TEST_URL / PG_TEST_MIGRATE_URL if set (CI or an existing scratch DB),
otherwise initdb's a private cluster in a temp dir on a free port with the
same role layout as the Nova Games DB (mush_owner owns the schema, mush gets
DML only, SCRAM auth). Never touches any other Postgres.
"""
import os
import shutil
import socket
import subprocess
import tempfile
import time


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class PgCluster:
    def __init__(self):
        self.dir = None
        self.port = None
        self.url = os.environ.get("PG_TEST_URL")
        self.migrate_url = os.environ.get("PG_TEST_MIGRATE_URL", self.url)

    @staticmethod
    def available() -> bool:
        return bool(os.environ.get("PG_TEST_URL")) or (shutil.which("initdb") and shutil.which("pg_ctl")) is not None

    def start(self):
        if self.url:
            return self
        self.dir = tempfile.mkdtemp(prefix="wpm-pg-")
        data = os.path.join(self.dir, "data")
        pwfile = os.path.join(self.dir, "pw")
        with open(pwfile, "w") as f:
            f.write("superpw\n")
        subprocess.run(["initdb", "-D", data, "-U", "postgres", "--auth=scram-sha-256", f"--pwfile={pwfile}",
                        "-E", "UTF8", "--no-instructions"], check=True, capture_output=True)
        self.port = _free_port()
        subprocess.run(["pg_ctl", "-D", data, "-l", os.path.join(self.dir, "log"), "-w", "-o",
                        f"-p {self.port} -k {self.dir} -c listen_addresses=127.0.0.1", "start"],
                       check=True, capture_output=True)
        env = dict(os.environ, PGPASSWORD="superpw")
        try:
            self._provision(env)
        except Exception:
            self.stop()
            raise
        return self

    def _provision(self, env):
        subprocess.run(["psql", "-h", "127.0.0.1", "-p", str(self.port), "-U", "postgres", "-d", "postgres",
                        "-v", "ON_ERROR_STOP=1",
                        "-c", "CREATE ROLE mush_owner LOGIN PASSWORD 'ownerpw' NOSUPERUSER NOCREATEDB NOCREATEROLE",
                        "-c", "CREATE ROLE mush LOGIN PASSWORD 'apppw' NOSUPERUSER NOCREATEDB NOCREATEROLE",
                        "-c", "CREATE DATABASE games OWNER postgres"], check=True, capture_output=True, env=env)
        sql2 = """
        REVOKE ALL ON SCHEMA public FROM PUBLIC;
        CREATE SCHEMA mush AUTHORIZATION mush_owner;
        GRANT USAGE ON SCHEMA mush TO mush;
        ALTER ROLE mush SET search_path = mush;
        ALTER ROLE mush_owner SET search_path = mush;
        ALTER DEFAULT PRIVILEGES FOR ROLE mush_owner IN SCHEMA mush
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mush;
        ALTER DEFAULT PRIVILEGES FOR ROLE mush_owner IN SCHEMA mush
            GRANT USAGE, SELECT ON SEQUENCES TO mush;
        """
        subprocess.run(["psql", "-h", "127.0.0.1", "-p", str(self.port), "-U", "postgres", "-d", "games",
                        "-v", "ON_ERROR_STOP=1", "-c", sql2], check=True, capture_output=True, env=env)
        self.url = f"postgresql://mush:apppw@127.0.0.1:{self.port}/games"
        self.migrate_url = f"postgresql://mush_owner:ownerpw@127.0.0.1:{self.port}/games"

    def stop(self):
        if self.dir:
            subprocess.run(["pg_ctl", "-D", os.path.join(self.dir, "data"), "-m", "immediate", "stop"],
                           capture_output=True)
            for _ in range(20):
                try:
                    shutil.rmtree(self.dir)
                    break
                except OSError:
                    time.sleep(0.1)
