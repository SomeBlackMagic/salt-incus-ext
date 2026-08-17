from unittest.mock import Mock

import pytest

from incus.states import incus_image_mod


@pytest.fixture
def state_runtime(monkeypatch):
    salt_funcs = {
        "incus.image_list": Mock(return_value={"success": True, "images": []}),
        "incus.image_alias_get": Mock(return_value={"success": False}),
        "incus.image_alias_list": Mock(return_value={"success": True, "aliases": []}),
        "incus.image_create_from_remote": Mock(),
        "incus.image_create_from_file": Mock(),
        "incus.image_update": Mock(),
        "incus.image_get": Mock(),
        "incus.image_delete": Mock(),
    }
    opts = {"test": False}
    monkeypatch.setattr(incus_image_mod, "__salt__", salt_funcs, raising=False)
    monkeypatch.setattr(incus_image_mod, "__opts__", opts, raising=False)
    return salt_funcs, opts


def test_virtual_loads_when_image_execution_functions_are_available(monkeypatch):
    monkeypatch.setattr(
        incus_image_mod,
        "__salt__",
        {"incus.image_list": Mock()},
        raising=False,
    )

    assert incus_image_mod.__virtual__() == "incus"


def test_virtual_rejects_missing_image_execution_functions(monkeypatch):
    monkeypatch.setattr(incus_image_mod, "__salt__", {}, raising=False)

    assert incus_image_mod.__virtual__() == (
        False,
        "incus image execution functions are not available",
    )


@pytest.mark.parametrize(
    ("alias_result", "expected_info", "expected_fingerprint"),
    [
        ({"success": True, "alias": {"target": "fp-1"}}, {"target": "fp-1"}, "fp-1"),
        ({"success": False}, None, None),
        ({"success": True, "alias": None}, None, None),
    ],
)
def test_alias_helpers(state_runtime, alias_result, expected_info, expected_fingerprint):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.image_alias_get"].return_value = alias_result

    assert incus_image_mod._get_alias_info("stable") == expected_info
    assert incus_image_mod._find_image_by_alias("stable") == expected_fingerprint
    assert salt_funcs["incus.image_alias_get"].call_count == 2


def test_image_present_reports_list_error(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.image_list"].return_value = {
        "success": False,
        "error": "images unavailable",
    }

    result = incus_image_mod.image_present("stable")

    assert result == {
        "name": "stable",
        "result": False,
        "changes": {},
        "comment": "Failed to list images: images unavailable",
    }
    salt_funcs["incus.image_list"].assert_called_once_with(recursion=1)


def test_image_present_requires_source_for_missing_image(state_runtime):
    salt_funcs, _ = state_runtime

    result = incus_image_mod.image_present("stable")

    assert result == {
        "name": "stable",
        "result": False,
        "changes": {},
        "comment": "Image not found and no source specified for import",
    }
    salt_funcs["incus.image_create_from_remote"].assert_not_called()
    salt_funcs["incus.image_create_from_file"].assert_not_called()


def test_image_present_test_mode_reports_import_and_deduplicates_aliases(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    source = {"server": "https://images.example", "alias": "ubuntu/24.04"}

    result = incus_image_mod.image_present(
        "stable",
        source=source,
        aliases=["latest", "stable", "latest"],
    )

    assert result == {
        "name": "stable",
        "result": None,
        "changes": {
            "image": {"old": None, "new": source},
            "aliases": {"old": None, "new": ["stable", "latest"]},
        },
        "comment": "Image would be imported",
    }
    salt_funcs["incus.image_create_from_remote"].assert_not_called()


def test_image_present_imports_remote_image(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.image_list"].side_effect = [
        {"success": True, "images": []},
        {"success": True, "images": [{"fingerprint": "new-fp"}]},
    ]
    salt_funcs["incus.image_create_from_remote"].return_value = {
        "success": True,
        "fingerprint": "new-fp",
    }
    source = {
        "server": "https://images.example",
        "alias": "ubuntu/24.04",
        "protocol": "incus",
    }

    result = incus_image_mod.image_present(
        "stable",
        source=source,
        public=True,
        auto_update=True,
        aliases=["latest"],
        properties={"os": "ubuntu"},
    )

    assert result == {
        "name": "stable",
        "result": True,
        "changes": {
            "imported": {"old": None, "new": "new-fp"},
            "aliases": {"old": None, "new": ["stable", "latest"]},
        },
        "comment": "Image imported with fingerprint new-fp",
    }
    salt_funcs["incus.image_create_from_remote"].assert_called_once_with(
        "https://images.example",
        alias="ubuntu/24.04",
        protocol="incus",
        auto_update=True,
        public=True,
        aliases=["stable", "latest"],
        properties={"os": "ubuntu"},
    )
    assert salt_funcs["incus.image_list"].call_count == 2


def test_image_present_imports_local_image_with_default_flags(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.image_list"].side_effect = [
        {"success": True, "images": []},
        {"success": True, "images": []},
    ]
    salt_funcs["incus.image_create_from_file"].return_value = {
        "success": True,
        "fingerprint": "local-fp",
    }

    result = incus_image_mod.image_present("local", source="/tmp/image.tar.xz")

    assert result["result"] is True
    assert result["changes"] == {
        "imported": {"old": None, "new": "local-fp"},
        "aliases": {"old": None, "new": ["local"]},
    }
    salt_funcs["incus.image_create_from_file"].assert_called_once_with(
        "/tmp/image.tar.xz",
        public=False,
        properties=None,
        aliases=["local"],
        auto_update=False,
    )


@pytest.mark.parametrize(
    ("source", "import_function"),
    [
        ({"server": "https://images.example", "alias": "ubuntu"}, "remote"),
        ("/tmp/image.tar.xz", "file"),
    ],
)
def test_image_present_reports_import_errors(state_runtime, source, import_function):
    salt_funcs, _ = state_runtime
    function = salt_funcs[
        (
            "incus.image_create_from_remote"
            if import_function == "remote"
            else "incus.image_create_from_file"
        )
    ]
    function.return_value = {"success": False, "error": "import failed"}

    result = incus_image_mod.image_present("stable", source=source)

    assert result["result"] is False
    assert not result["changes"]
    assert result["comment"] == "Failed to import image: import failed"


@pytest.mark.parametrize("source", [{"alias": "ubuntu"}, 123, ["image.tar"]])
def test_image_present_rejects_invalid_import_source(state_runtime, source):
    result = incus_image_mod.image_present("stable", source=source)

    assert result["result"] is False
    assert result["comment"] == (
        "Invalid source for image import (must be dict with 'server' or file path string)"
    )


def test_image_present_reports_refresh_error(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.image_list"].side_effect = [
        {"success": True, "images": []},
        {"success": False, "error": "refresh failed"},
    ]
    salt_funcs["incus.image_create_from_file"].return_value = {
        "success": True,
        "fingerprint": "new-fp",
    }

    result = incus_image_mod.image_present("stable", source="image.tar")

    assert result["result"] is False
    assert result["comment"] == "Failed to refresh image list: refresh failed"


@pytest.mark.parametrize(
    ("kwargs", "alias_targets", "expected_calls"),
    [
        ({"fingerprint": "fp-1"}, {}, []),
        ({}, {"stable": "fp-1"}, ["stable"]),
        (
            {"aliases": ["fallback"]},
            {"fallback": "fp-1"},
            ["stable", "fallback"],
        ),
        (
            {"source": {"alias": "ubuntu/24.04"}},
            {"ubuntu/24.04": "fp-1"},
            ["stable", "ubuntu/24.04"],
        ),
    ],
)
def test_image_present_finds_existing_image_by_supported_identifiers(
    state_runtime,
    kwargs,
    alias_targets,
    expected_calls,
):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.image_list"].return_value = {
        "success": True,
        "images": [{"fingerprint": "fp-1"}],
    }
    salt_funcs["incus.image_alias_get"].side_effect = lambda alias: (
        {"success": True, "alias": {"target": alias_targets[alias]}}
        if alias in alias_targets
        else {"success": False}
    )
    desired_aliases = ["stable", *kwargs.get("aliases", [])]
    salt_funcs["incus.image_alias_list"].return_value = {
        "success": True,
        "aliases": [{"name": alias, "target": "fp-1"} for alias in desired_aliases],
    }

    result = incus_image_mod.image_present("stable", **kwargs)

    assert result["result"] is True
    assert not result["changes"]
    assert result["comment"] == "Image already present with alias stable and up-to-date"
    assert [call.args[0] for call in salt_funcs["incus.image_alias_get"].call_args_list] == (
        expected_calls
    )


def test_image_present_updates_all_reconciled_fields(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.image_list"].return_value = {
        "success": True,
        "images": [
            {
                "fingerprint": "fp-1",
                "public": False,
                "auto_update": False,
                "properties": {"os": "old"},
                "expires_at": None,
                "compression_algorithm": "gzip",
            }
        ],
    }
    salt_funcs["incus.image_alias_list"].return_value = {
        "success": True,
        "aliases": [
            {"name": "stable", "target": "fp-1"},
            {"name": "unrelated", "target": "other-fp"},
            "invalid-entry",
        ],
    }
    salt_funcs["incus.image_update"].return_value = {"success": True}

    result = incus_image_mod.image_present(
        "stable",
        fingerprint="fp-1",
        public=True,
        auto_update=True,
        aliases=["latest"],
        properties={"os": "ubuntu"},
        expires_at="2030-01-01T00:00:00Z",
        compression_algorithm="zstd",
    )

    expected_changes = {
        "public": {"old": False, "new": True},
        "auto_update": {"old": False, "new": True},
        "aliases": {"old": ["stable"], "new": ["latest", "stable"]},
        "properties": {"old": {"os": "old"}, "new": {"os": "ubuntu"}},
        "expires_at": {"old": None, "new": "2030-01-01T00:00:00Z"},
        "compression_algorithm": {"old": "gzip", "new": "zstd"},
    }
    assert result == {
        "name": "stable",
        "result": True,
        "changes": expected_changes,
        "comment": "Image updated with alias stable",
    }
    salt_funcs["incus.image_update"].assert_called_once_with(
        "fp-1",
        {key: change["new"] for key, change in expected_changes.items()},
    )


def test_image_present_test_mode_reports_update_without_applying_it(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    salt_funcs["incus.image_list"].return_value = {
        "success": True,
        "images": [{"fingerprint": "fp-1", "public": False}],
    }
    salt_funcs["incus.image_alias_list"].return_value = {
        "success": True,
        "aliases": [{"name": "stable", "target": "fp-1"}],
    }

    result = incus_image_mod.image_present("stable", fingerprint="fp-1", public=True)

    assert result == {
        "name": "stable",
        "result": None,
        "changes": {"public": {"old": False, "new": True}},
        "comment": "Image would be updated",
    }
    salt_funcs["incus.image_update"].assert_not_called()


def test_image_present_reports_update_error(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.image_list"].return_value = {
        "success": True,
        "images": [{"fingerprint": "fp-1", "public": False}],
    }
    salt_funcs["incus.image_alias_list"].return_value = {
        "success": True,
        "aliases": [{"name": "stable", "target": "fp-1"}],
    }
    salt_funcs["incus.image_update"].return_value = {
        "success": False,
        "error": "update rejected",
    }

    result = incus_image_mod.image_present("stable", fingerprint="fp-1", public=True)

    assert result["result"] is False
    assert not result["changes"]
    assert result["comment"] == "Failed to update image: update rejected"


def test_image_absent_without_identifier_is_idempotent(state_runtime):
    salt_funcs, _ = state_runtime

    result = incus_image_mod.image_absent()

    assert result == {
        "name": "image",
        "result": True,
        "changes": {},
        "comment": "Image already absent",
    }
    salt_funcs["incus.image_get"].assert_not_called()


def test_image_absent_uses_fingerprint_when_alias_is_missing(state_runtime):
    salt_funcs, opts = state_runtime
    opts["test"] = True
    salt_funcs["incus.image_get"].return_value = {"success": True}

    result = incus_image_mod.image_absent(fingerprint="fp-1", alias="missing")

    assert result == {
        "name": "missing",
        "result": None,
        "changes": {"old": "fp-1", "new": None},
        "comment": "Image would be removed",
    }
    salt_funcs["incus.image_get"].assert_called_once_with("fp-1")
    salt_funcs["incus.image_delete"].assert_not_called()


def test_image_absent_treats_get_error_as_already_absent(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.image_alias_get"].return_value = {
        "success": True,
        "alias": {"target": "fp-1"},
    }
    salt_funcs["incus.image_get"].return_value = {"success": False}

    result = incus_image_mod.image_absent(alias="stable")

    assert result["result"] is True
    assert not result["changes"]
    assert result["comment"] == "Image already absent"


def test_image_absent_removes_image(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.image_get"].return_value = {"success": True}
    salt_funcs["incus.image_delete"].return_value = {"success": True}

    result = incus_image_mod.image_absent(fingerprint="fp-1")

    assert result == {
        "name": "fp-1",
        "result": True,
        "changes": {"old": "fp-1", "new": None},
        "comment": "Image removed",
    }
    salt_funcs["incus.image_delete"].assert_called_once_with("fp-1")


def test_image_absent_reports_delete_error(state_runtime):
    salt_funcs, _ = state_runtime
    salt_funcs["incus.image_get"].return_value = {"success": True}
    salt_funcs["incus.image_delete"].return_value = {
        "success": False,
        "error": "in use",
    }

    result = incus_image_mod.image_absent(fingerprint="fp-1")

    assert result == {
        "name": "fp-1",
        "result": False,
        "changes": {},
        "comment": "Failed to delete image: in use",
    }


def test_image_installed_delegates_to_image_present(monkeypatch):
    image_present = Mock(return_value={"result": True})
    monkeypatch.setattr(incus_image_mod, "image_present", image_present)

    result = incus_image_mod.image_installed(
        "stable",
        fingerprint="fp-1",
        source={"server": "https://images.example"},
        auto_update=True,
        public=True,
        aliases=["latest"],
        properties={"os": "ubuntu"},
    )

    assert result == {"result": True}
    image_present.assert_called_once_with(
        name="stable",
        fingerprint="fp-1",
        source={"server": "https://images.example"},
        auto_update=True,
        public=True,
        aliases=["latest"],
        properties={"os": "ubuntu"},
    )
