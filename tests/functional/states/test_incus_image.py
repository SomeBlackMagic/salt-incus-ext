"""Functional tests for Incus image state functions."""

import pytest

from tests.functional.conftest import check_local_shell
from tests.functional.conftest import create_case_parametrize
from tests.functional.conftest import run_cleanup
from tests.functional.conftest import run_setup

pytestmark = pytest.mark.requires_salt_states("incus.image_present")


@create_case_parametrize("images.yml")
def test_image(case, states):
    run_setup(case.get("setup"))

    images = case["pillars"]["incus"]["images"]

    try:
        for name, opts in images.items():
            ret = states["incus.image_present"](
                name,
                source=opts.get("source"),
                public=opts.get("public"),
                auto_update=opts.get("auto_update"),
                aliases=opts.get("aliases"),
                properties=opts.get("properties"),
                compression_algorithm=opts.get("compression_algorithm"),
            )

            assert (
                ret.result is True
            ), f"State incus.image_present failed for '{name}': {ret.comment}"

        expected = case.get("expected", {})
        if "local_shell" in expected:
            check_local_shell(expected["local_shell"])

    finally:
        run_cleanup(case.get("cleanup", []))
