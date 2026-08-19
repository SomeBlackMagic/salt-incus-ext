from unittest.mock import Mock

import pytest

from incus.modules import incus_trust_mod


@pytest.fixture
def client(monkeypatch):
    client = Mock()
    monkeypatch.setattr(incus_trust_mod, "_client", Mock(return_value=client))
    return client


def test_client_creates_incus_client(monkeypatch):
    from incus.modules import incus_mod

    mock_client = Mock()
    monkeypatch.setattr(incus_trust_mod, "__salt__", {}, raising=False)
    monkeypatch.setattr(incus_mod, "IncusClient", Mock(return_value=mock_client))

    assert incus_trust_mod._client() is mock_client


def test_trust_list_passes_recursion_and_returns_metadata(client):
    certificates = [{"fingerprint": "abc"}, {"fingerprint": "def"}]
    client._request.return_value = {
        "error_code": 0,
        "metadata": certificates,
    }

    assert incus_trust_mod.trust_list(recursion=2) == {
        "success": True,
        "certificates": certificates,
    }
    client._request.assert_called_once_with("GET", "/certificates", params={"recursion": 2})


def test_trust_list_uses_defaults(client):
    client._request.return_value = {"error_code": 0}

    assert incus_trust_mod.trust_list() == {"success": True, "certificates": []}
    client._request.assert_called_once_with("GET", "/certificates", params={"recursion": 1})


@pytest.mark.parametrize(
    ("response", "error"),
    [
        ({"error_code": 1, "error": "connection failed"}, "connection failed"),
        ({"error_code": 1}, "Failed to list trusted certificates"),
    ],
)
def test_trust_list_returns_api_error(client, response, error):
    client._request.return_value = response

    assert incus_trust_mod.trust_list() == {"success": False, "error": error}


@pytest.mark.parametrize("fingerprint", [None, ""])
def test_trust_get_rejects_missing_fingerprint_before_creating_client(monkeypatch, fingerprint):
    factory = Mock()
    monkeypatch.setattr(incus_trust_mod, "_client", factory)

    assert incus_trust_mod.trust_get(fingerprint) == {
        "success": False,
        "error": "fingerprint is required",
    }
    factory.assert_not_called()


def test_trust_get_quotes_fingerprint_and_returns_metadata(client):
    certificate = {"fingerprint": "finger print", "name": "salt"}
    client._request.return_value = {"error_code": 0, "metadata": certificate}

    assert incus_trust_mod.trust_get("finger print") == {
        "success": True,
        "certificate": certificate,
    }
    client._request.assert_called_once_with("GET", "/certificates/finger%20print")


def test_trust_get_defaults_to_empty_metadata(client):
    client._request.return_value = {"error_code": 0}

    assert incus_trust_mod.trust_get("fingerprint") == {
        "success": True,
        "certificate": {},
    }


@pytest.mark.parametrize(
    ("response", "error"),
    [
        ({"error_code": 1, "error": "not found"}, "not found"),
        ({"error_code": 1}, "Failed to get trusted certificate"),
    ],
)
def test_trust_get_returns_api_error(client, response, error):
    client._request.return_value = response

    assert incus_trust_mod.trust_get("fingerprint") == {
        "success": False,
        "error": error,
    }


@pytest.mark.parametrize("cert_pem", [None, ""])
def test_trust_add_rejects_missing_certificate_before_creating_client(monkeypatch, cert_pem):
    factory = Mock()
    monkeypatch.setattr(incus_trust_mod, "_client", factory)

    assert incus_trust_mod.trust_add(cert_pem) == {
        "success": False,
        "error": "cert_pem is required",
    }
    factory.assert_not_called()


def test_trust_add_builds_complete_request(client):
    client._sync_request.return_value = {"error_code": 0}

    assert incus_trust_mod.trust_add(
        "-----BEGIN CERTIFICATE-----", name="client one", restricted=1
    ) == {
        "success": True,
        "message": "Certificate added to trust store",
    }
    client._sync_request.assert_called_once_with(
        "POST",
        "/certificates",
        data={
            "type": "client",
            "certificate": "-----BEGIN CERTIFICATE-----",
            "name": "client one",
            "restricted": True,
        },
    )


def test_trust_add_includes_projects_when_provided(client):
    client._sync_request.return_value = {"error_code": 0}

    assert (
        incus_trust_mod.trust_add(
            "certificate",
            name="salt-cloud",
            restricted=True,
            projects=("default", "cloud"),
        )["success"]
        is True
    )
    client._sync_request.assert_called_once_with(
        "POST",
        "/certificates",
        data={
            "type": "client",
            "certificate": "certificate",
            "name": "salt-cloud",
            "restricted": True,
            "projects": ["default", "cloud"],
        },
    )


@pytest.mark.parametrize("name", [None, ""])
def test_trust_add_uses_default_name_and_false_restriction(client, name):
    client._sync_request.return_value = {"error_code": 0}

    incus_trust_mod.trust_add("certificate", name=name, restricted=0)

    client._sync_request.assert_called_once_with(
        "POST",
        "/certificates",
        data={
            "type": "client",
            "certificate": "certificate",
            "name": "salt-cloud",
            "restricted": False,
        },
    )


@pytest.mark.parametrize(
    ("response", "error"),
    [
        ({"error_code": 1, "error": "duplicate"}, "duplicate"),
        ({"error_code": 1}, "Failed to add trusted certificate"),
    ],
)
def test_trust_add_returns_api_error(client, response, error):
    client._sync_request.return_value = response

    assert incus_trust_mod.trust_add("certificate") == {
        "success": False,
        "error": error,
    }


@pytest.mark.parametrize("fingerprint", [None, ""])
def test_trust_update_rejects_missing_fingerprint(monkeypatch, fingerprint):
    factory = Mock()
    monkeypatch.setattr(incus_trust_mod, "_client", factory)

    assert incus_trust_mod.trust_update(fingerprint, name="salt-cloud") == {
        "success": False,
        "error": "fingerprint is required",
    }
    factory.assert_not_called()


def test_trust_update_requires_at_least_one_field(monkeypatch):
    factory = Mock()
    monkeypatch.setattr(incus_trust_mod, "_client", factory)

    assert incus_trust_mod.trust_update("abc") == {
        "success": False,
        "error": "at least one update field is required",
    }
    factory.assert_not_called()


def test_trust_update_patches_selected_fields(client):
    client._sync_request.return_value = {"error_code": 0}

    assert incus_trust_mod.trust_update(
        "finger print",
        name="salt-cloud",
        restricted=True,
        projects=("default",),
    ) == {
        "success": True,
        "message": "Certificate finger print updated",
    }
    client._sync_request.assert_called_once_with(
        "PATCH",
        "/certificates/finger%20print",
        data={
            "name": "salt-cloud",
            "restricted": True,
            "projects": ["default"],
        },
    )


@pytest.mark.parametrize(
    ("response", "error"),
    [
        ({"error_code": 1, "error": "not found"}, "not found"),
        ({"error_code": 1}, "Failed to update trusted certificate"),
    ],
)
def test_trust_update_returns_api_error(client, response, error):
    client._sync_request.return_value = response

    assert incus_trust_mod.trust_update("abc", restricted=False) == {
        "success": False,
        "error": error,
    }


@pytest.mark.parametrize("fingerprint", [None, ""])
def test_trust_remove_rejects_missing_fingerprint_before_creating_client(monkeypatch, fingerprint):
    factory = Mock()
    monkeypatch.setattr(incus_trust_mod, "_client", factory)

    assert incus_trust_mod.trust_remove(fingerprint) == {
        "success": False,
        "error": "fingerprint is required",
    }
    factory.assert_not_called()


def test_trust_remove_quotes_fingerprint(client):
    client._sync_request.return_value = {"error_code": 0}

    assert incus_trust_mod.trust_remove("finger print") == {
        "success": True,
        "message": "Certificate finger print removed from trust store",
    }
    client._sync_request.assert_called_once_with("DELETE", "/certificates/finger%20print")


@pytest.mark.parametrize(
    ("response", "error"),
    [
        ({"error_code": 1, "error": "in use"}, "in use"),
        ({"error_code": 1}, "Failed to remove trusted certificate"),
    ],
)
def test_trust_remove_returns_api_error(client, response, error):
    client._sync_request.return_value = response

    assert incus_trust_mod.trust_remove("fingerprint") == {
        "success": False,
        "error": error,
    }
