import re
from pathlib import Path

import pytest
from memorydock_core.config import MissingSetting, Settings
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]
FAKE_URI = "mongodb+srv://u:pw@host"  # pragma: allowlist secret


def make(**kwargs):
    return Settings(_env_file=None, **kwargs)


def test_defaults_are_dev_with_nothing_set():
    s = make()
    assert s.env == "dev"
    assert s.mongodb_uri_admin is None


@pytest.mark.parametrize(
    "db", ["memorydock_dev_someone", "memorydock_test_ab12", "memorydock_verify"]
)
def test_dev_accepts_developer_databases(db):
    assert make(mongodb_db=db).mongodb_db == db


@pytest.mark.parametrize("db", ["memorydock", "memorydock_dev", "other", "memorydock_prod"])
def test_dev_refuses_shared_and_unknown_databases(db):
    with pytest.raises(ValidationError):
        make(mongodb_db=db)


def test_prod_requires_the_shared_database():
    assert make(env="prod", mongodb_db="memorydock").mongodb_db == "memorydock"
    with pytest.raises(ValidationError):
        make(env="prod", mongodb_db="memorydock_dev_someone")


def test_unknown_env_is_rejected():
    with pytest.raises(ValidationError):
        make(env="staging")


def test_require_secret_names_the_variable_not_the_value():
    s = make(mongodb_uri_admin=FAKE_URI)
    assert s.require_secret("mongodb_uri_admin") == FAKE_URI
    with pytest.raises(MissingSetting, match=r"^MONGODB_URI_WORKER is not set$"):
        s.require_secret("mongodb_uri_worker")
    assert "pw" not in repr(s)


def test_empty_secret_counts_as_missing():
    with pytest.raises(MissingSetting):
        make(mongodb_uri="").require_secret("mongodb_uri")


def test_require_db():
    with pytest.raises(MissingSetting, match="MONGODB_DB"):
        make().require_db()


def test_env_example_matches_settings_both_ways():
    text = (ROOT / ".env.example").read_text()
    documented = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", text, flags=re.M))
    read_by_code = {name.upper() for name in Settings.model_fields}
    assert documented == read_by_code


def test_every_env_example_line_has_a_comment():
    for line in (ROOT / ".env.example").read_text().splitlines():
        if re.match(r"^[A-Z]", line):
            assert "#" in line, line
