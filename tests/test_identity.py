"""Each CLI profile signs in as the right user, in the right groups, and the
metastore admin is the delegate group."""

import pytest

from conftest import MEMBERSHIP, POC_GROUPS, USERS


@pytest.mark.parametrize("name", list(USERS))
def test_profile_signs_in_as_its_user(profile, name):
    assert profile(name).user == USERS[name]


@pytest.mark.parametrize("name", list(USERS))
def test_profile_is_in_the_expected_poc_groups(profile, name):
    assert profile(name).groups & POC_GROUPS == MEMBERSHIP[name]


def test_metastore_admin_is_the_metastore_admins_group(profile):
    assert profile("admin").w.metastores.summary().owner == "metastore_admins"


@pytest.mark.parametrize("name", ["frank", "david", "alice", "bob", "carol"])
def test_only_the_account_admin_is_a_workspace_admin(profile, name):
    assert "admins" not in profile(name).groups
