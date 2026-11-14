import check_env
from memorydock_core.config import Settings

URI = "mongodb+srv://md_x:secretpw@cluster0.example.com/?x=1"  # pragma: allowlist secret
STATUS = {
    "authInfo": {
        "authenticatedUsers": [{"user": "md_admin", "db": "admin"}],
        "authenticatedUserRoles": [
            {"role": "readWriteAnyDatabase", "db": "admin"},
            {"role": "dbAdminAnyDatabase", "db": "admin"},
        ],
    }
}


class FakeAdmin:
    def __init__(self, fail=None):
        self.fail = fail

    def command(self, cmd):
        if self.fail:
            raise self.fail
        return {"ok": 1} if cmd == "ping" else STATUS


class FakeClient:
    def __init__(self, fail=None):
        self.admin = FakeAdmin(fail)
        self.closed = False

    def close(self):
        self.closed = True


def settings(**kw):
    return Settings(_env_file=None, **kw)


def test_all_present_and_reachable_passes():
    s = settings(
        mongodb_uri=URI,
        mongodb_uri_worker=URI,
        mongodb_uri_admin=URI,
        mongodb_db="memorydock_dev_x",
    )
    results = check_env.run(s, lambda uri: FakeClient())
    assert all(r.ok for r in results)
    assert str(results[0]) == (
        "PASS admin: user md_admin; roles dbAdminAnyDatabase@admin, readWriteAnyDatabase@admin"
    )


def test_missing_uris_and_db_fail_by_name():
    lines = [str(r) for r in check_env.run(settings(), lambda uri: FakeClient())]
    assert lines == [
        "FAIL admin: MONGODB_URI_ADMIN is not set",
        "FAIL gateway: MONGODB_URI is not set",
        "FAIL worker: MONGODB_URI_WORKER is not set",
        "FAIL database: MONGODB_DB is not set",
    ]


def test_connection_error_never_prints_the_uri():
    err = RuntimeError(f"could not reach {URI}")
    result = check_env.check_one("admin", URI, lambda uri: FakeClient(err))
    assert not result.ok
    assert "secretpw" not in str(result) and "<uri>" in str(result)


def test_client_closed_even_on_failure():
    client = FakeClient(RuntimeError("boom"))
    check_env.check_one("admin", URI, lambda uri: client)
    assert client.closed


def test_describe_auth_with_no_users():
    assert check_env.describe_auth({}) == "user none; roles none"
