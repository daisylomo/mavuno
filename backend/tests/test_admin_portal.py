from fastapi.testclient import TestClient


def test_admin_portal_and_assets(client: TestClient) -> None:
    for path, content_type in (
        ("/admin", "text/html"),
        ("/admin/", "text/html"),
        ("/admin/portal.js", "text/javascript"),
        ("/admin/portal.css", "text/css"),
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert content_type in response.headers["content-type"]
        assert response.headers["cache-control"] == "no-store"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert response.headers["x-content-type-options"] == "nosniff"
    assert "Administrator sign in" in client.get("/admin").text


def test_admin_assets_do_not_allow_arbitrary_files(client: TestClient) -> None:
    assert client.get("/admin/unknown.js").status_code == 404


def test_admin_shell_does_not_expose_private_data(client: TestClient) -> None:
    assert client.get("/api/v1/admin/refunds").status_code == 401
