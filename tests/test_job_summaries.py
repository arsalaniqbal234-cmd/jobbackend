from sqlalchemy import event

from app.models import Job
from database import engine


def test_summary_omits_description_in_sql_and_json_without_changing_detail(client, db):
    description = "<p>Detailed responsibilities and requirements for this role.</p>" * 1000
    db.add_all([Job(source_id=f"summary_{index}", title=f"Engineer {index}", company="Example",
                    url=f"https://example.com/jobs/{index}", description=description,
                    is_remote=True, location="London") for index in range(20)])
    db.commit()
    statements = []

    def record(_conn, _cursor, statement, _params, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        summary = client.get("/jobs?summary=true&location=London")
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert summary.status_code == 200
    assert len(summary.json()) == 20
    assert all("description" not in item for item in summary.json())
    assert len(statements) == 1  # Serialization must not lazily fetch each description.
    assert "description" not in statements[0].split("FROM", 1)[0]

    full = client.get("/jobs?location=London")
    assert full.status_code == 200
    assert full.json()[0]["description"] == description
    assert summary.json() == [{key: value for key, value in row.items() if key != "description"}
                              for row in full.json()]
    detail = client.get(f"/jobs/{summary.json()[0]['id']}")
    assert detail.json()["description"] == description
    assert len(summary.content) < len(full.content) * 0.1
    print(f"Listing payload: full={len(full.content)} B, summary={len(summary.content)} B, "
          f"reduction={100 * (1 - len(summary.content) / len(full.content)):.2f}%")


def test_summary_cache_and_cursor_remain_separate_from_full_lists(client, db):
    db.add_all([Job(source_id=f"cursor_{index}", title="Engineer", company="Example",
                    url=f"https://example.com/{index}", description="Full detail", is_remote=False)
                for index in range(3)])
    db.commit()
    full = client.get("/search?limit=1")
    summary = client.get("/search?limit=1&summary=true")
    assert full.headers["x-cache"] == "MISS"
    assert summary.headers["x-cache"] == "MISS"
    assert "description" in full.json()[0]
    assert "description" not in summary.json()[0]
    assert client.get("/search?limit=1&summary=true").headers["x-cache"] == "HIT"
    first = summary.json()[0]
    second = client.get(f"/jobs?limit=1&summary=true&before_id={first['id']}").json()[0]
    assert second["id"] < first["id"]
    assert "description" not in second
