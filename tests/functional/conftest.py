import logging
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from saltfactories.utils.functional import Loaders

FUNCTIONAL_DATA_DIR = Path(__file__).parent / "data"

log = logging.getLogger(__name__)


@pytest.fixture(scope="package")
def minion_id():  # pragma: no cover
    return "func-tests-minion-opts"


@pytest.fixture(scope="module")
def state_tree(tmp_path_factory):  # pragma: no cover
    state_tree_path = tmp_path_factory.mktemp("state-tree-base")
    try:
        yield state_tree_path
    finally:
        shutil.rmtree(str(state_tree_path), ignore_errors=True)


@pytest.fixture(scope="module")
def state_tree_prod(tmp_path_factory):  # pragma: no cover
    state_tree_path = tmp_path_factory.mktemp("state-tree-prod")
    try:
        yield state_tree_path
    finally:
        shutil.rmtree(str(state_tree_path), ignore_errors=True)


@pytest.fixture(scope="module")
def minion_config_defaults():  # pragma: no cover
    """
    Functional test modules can provide this fixture to tweak the default
    configuration dictionary passed to the minion factory
    """
    return {}


@pytest.fixture(scope="module")
def minion_config_overrides():  # pragma: no cover
    """
    Functional test modules can provide this fixture to tweak the configuration
    overrides dictionary passed to the minion factory.

    Incus connection can be configured via environment variables:

      INCUS_SOCKET=/var/lib/incus/unix.socket   (default)
      INCUS_URL=https://my-host:8443            (enables HTTPS mode)
      INCUS_CERT=/path/to/client.crt            (HTTPS only)
      INCUS_KEY=/path/to/client.key             (HTTPS only)
      INCUS_VERIFY=true|false|/path/to/ca.crt   (HTTPS only, default true)
    """
    incus_url = os.environ.get("INCUS_URL")
    if incus_url:
        verify_raw = os.environ.get("INCUS_VERIFY", "true")
        if verify_raw.lower() == "true":
            verify = True
        elif verify_raw.lower() == "false":
            verify = False
        else:
            verify = verify_raw
        incus_cfg = {
            "connection": {
                "type": "https",
                "url": incus_url,
                "cert_storage": {
                    "cert": os.environ.get("INCUS_CERT"),
                    "key": os.environ.get("INCUS_KEY"),
                    "verify": verify,
                },
            }
        }
    else:
        socket_path = os.environ.get("INCUS_SOCKET", "/var/lib/incus/unix.socket")
        incus_cfg = {
            "connection": {
                "type": "unix",
                "socket": socket_path,
            }
        }

    return {"incus": incus_cfg}


@pytest.fixture(scope="module")
def minion_opts(
    salt_factories,
    minion_id,
    state_tree,
    state_tree_prod,
    minion_config_defaults,
    minion_config_overrides,
):  # pragma: no cover
    minion_config_overrides.update(
        {
            "file_client": "local",
            "file_roots": {
                "base": [
                    str(state_tree),
                ],
                "prod": [
                    str(state_tree_prod),
                ],
            },
        }
    )
    factory = salt_factories.salt_minion_daemon(
        minion_id,
        defaults=minion_config_defaults or None,
        overrides=minion_config_overrides,
    )
    return factory.config.copy()


@pytest.fixture(scope="module")
def master_config_defaults():  # pragma: no cover
    """
    Functional test modules can provide this fixture to tweak the default
    configuration dictionary passed to the master factory
    """
    return {}


@pytest.fixture(scope="module")
def master_config_overrides():  # pragma: no cover
    """
    Functional test modules can provide this fixture to tweak the configuration
    overrides dictionary passed to the master factory
    """
    return {}


@pytest.fixture(scope="module")
def master_opts(
    salt_factories,
    state_tree,
    state_tree_prod,
    master_config_defaults,
    master_config_overrides,
):  # pragma: no cover
    master_config_overrides.update(
        {
            "file_client": "local",
            "file_roots": {
                "base": [
                    str(state_tree),
                ],
                "prod": [
                    str(state_tree_prod),
                ],
            },
        }
    )
    factory = salt_factories.salt_master_daemon(
        "func-tests-master-opts",
        defaults=master_config_defaults or None,
        overrides=master_config_overrides,
    )
    return factory.config.copy()


@pytest.fixture(scope="module")
def loaders(minion_opts):  # pragma: no cover
    return Loaders(minion_opts, loaded_base_name=f"{__name__}.loaded")


@pytest.fixture(autouse=True)
def reset_loaders_state(loaders):  # pragma: no cover
    try:
        # Run the tests
        yield
    finally:
        # Reset the loaders state
        loaders.reset_state()


@pytest.fixture(scope="module")
def modules(loaders):  # pragma: no cover
    return loaders.modules


@pytest.fixture(scope="module")
def states(loaders):  # pragma: no cover
    return loaders.states


# ============================================================
# YAML-based parametrize helpers
# ============================================================


def load_yaml_cases(filename):
    path = FUNCTIONAL_DATA_DIR / filename
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("cases", [])


def create_case_parametrize(filename):
    cases = load_yaml_cases(filename)
    ids = [case.get("name", f"case_{i}") for i, case in enumerate(cases)]
    return pytest.mark.parametrize("case", cases, ids=ids)


# ============================================================
# Shell helpers
# ============================================================


def run_local_shell(cmd):
    """Run a shell command, injecting INCUS_SOCKET into the environment if set."""
    env = os.environ.copy()
    return subprocess.run(
        cmd, shell=True, check=False, capture_output=True, text=True, env=env
    )  # nosec B602


def run_setup(commands):
    for cmd in commands or []:
        r = run_local_shell(cmd)
        if r.returncode != 0:
            raise AssertionError(f"Setup command failed: {cmd}\n{r.stderr}")


def run_cleanup(commands):
    for cmd in commands or []:
        r = run_local_shell(cmd)
        if r.returncode != 0:
            log.warning("Cleanup command failed: %s\n%s", cmd, r.stderr)


def check_requirements(case):
    """Skip test if system requirements are not met."""
    for req in case.get("requires") or []:
        r = run_local_shell(req["cmd"])
        if r.returncode != 0:
            pytest.skip(req.get("message", f"Requirement not met: {req['cmd']}"))


def check_local_shell(commands):
    for item in commands:
        r = run_local_shell(item["cmd"])

        if r.returncode != 0 and not item.get("expect_stderr"):
            raise AssertionError(
                f"Local command failed (exit {r.returncode}): {item['cmd']}\n{r.stderr}"
            )

        for s in item.get("expect_stdout", []):
            assert s in r.stdout, f"'{s}' not in stdout of: {item['cmd']}"

        for s in item.get("expect_not_stdout", []):
            assert s not in r.stdout, f"'{s}' unexpectedly in stdout of: {item['cmd']}"

        for s in item.get("expect_stderr", []):
            assert s in r.stderr, f"'{s}' not in stderr of: {item['cmd']}"


# ============================================================
# setup_environment fixture
# ============================================================


@pytest.fixture
def setup_environment():
    def _runner(commands=None):
        run_setup(commands)

    return _runner
