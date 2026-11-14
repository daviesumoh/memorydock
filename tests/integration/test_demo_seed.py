import demo_seed
from memorydock_core.config import Settings
from memorydock_core.db import sync_client

ARGS = ["--repo", "git@github.com:Owner/Demo-App.git", "--rosa", "Rosa@Example.com",
        "--theo", "theo@example.com", "--wren", "wren@example.com"]  # fmt: skip


def one(collection, query):
    doc = collection.find_one(query)
    assert doc is not None
    return doc


def test_seed_is_idempotent_and_shapes_the_demo(test_db_name):
    import atlas_setup

    assert atlas_setup.main(["--db", test_db_name, "--skip-search"]) == 0
    assert demo_seed.main(["--db", test_db_name, *ARGS]) == 0
    assert demo_seed.main(["--db", test_db_name, *ARGS]) == 0
    client = sync_client(Settings().require_secret("mongodb_uri_admin"), app_name="t")
    db = client[test_db_name]
    try:
        assert db.orgs.count_documents({}) == 2
        assert db.users.count_documents({}) == 3
        rosa, theo, wren = (
            one(db.users, {"email": f"{n}@example.com"}) for n in ("rosa", "theo", "wren")
        )
        assert rosa["tenant_id"] == "halcyon" and "admin" in rosa["roles"]
        assert theo["roles"] == ["member"] and wren["tenant_id"] == "brightwater"
        project = one(db.projects, {"tenant_id": "halcyon", "slug": "lantern"})
        assert project["repo_remotes"] == ["github.com/owner/demo-app"]
        assert sorted(project["members"]) == sorted([rosa["_id"], theo["_id"]])
        assert project["maintainers"] == [rosa["_id"]]
        assert db.projects.count_documents({}) == 1
    finally:
        client.close()


def test_refuses_the_shared_database_and_bad_input(test_db_name):
    assert demo_seed.main(["--db", "memorydock", *ARGS]) == 1
    bad_repo = ["--db", test_db_name, "--repo", "nope", *ARGS[2:]]
    assert demo_seed.main(bad_repo) == 1
    same = ["--db", test_db_name, "--repo", "github.com/o/r", "--rosa", "a@example.com",
            "--theo", "a@example.com", "--wren", "w@example.com"]  # fmt: skip
    assert demo_seed.main(same) == 1
