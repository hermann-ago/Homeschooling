def test_boot_and_crud(harness):
    r = harness.call("POST", "/api/children", json={"name": "Lucas", "color": "#123456"}, key="k1")
    assert r.status_code == 201, r.text
    assert r.headers["x-sync-state"] == "saved"
    assert harness.call("GET", "/api/children").json()[0]["name"] == "Lucas"
