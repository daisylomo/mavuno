import pytest
from api_client.client import MavunoClient
from api_client.models.profiles import AddressCreate, AddressUpdate, ProfileUpdate
from api_client.tests.conftest import register_and_login


@pytest.fixture
def user_client(client: MavunoClient) -> MavunoClient:
    c, _ = register_and_login(client, "buyer")
    return c


def test_profiles_lifecycle(user_client: MavunoClient):
    # 1. Fetch current profile (registration always seeds the default display name)
    profile_res = user_client.profiles.get_profile()
    assert profile_res.success is True, f"Get profile failed: {profile_res.error}"
    assert profile_res.data is not None
    assert profile_res.data.display_name == "Mavuno User"

    # 2. Update profile bio & display name
    update_res = user_client.profiles.update_profile(
        ProfileUpdate(
            display_name="Tester Pro",
            bio="Organic food distributor based in Kiambu.",
        )
    )
    assert update_res.success is True, f"Update profile failed: {update_res.error}"
    assert update_res.data.display_name == "Tester Pro"
    assert update_res.data.bio == "Organic food distributor based in Kiambu."

    # 3. Create Delivery Address
    addr_create_res = user_client.profiles.create_address(
        AddressCreate(
            label="Central Warehouse",
            line_1="Limuru Road, Plot 42",
            locality="Ruaka",
            county="Kiambu",
            postal_code="00218",
            is_default=True,
        )
    )
    assert addr_create_res.success is True, f"Create address failed: {addr_create_res.error}"
    address_id = addr_create_res.data.id

    # 4. List Addresses & Verify Presence
    addr_list_res = user_client.profiles.list_addresses()
    assert addr_list_res.success is True
    assert any(addr.id == address_id for addr in addr_list_res.data)

    # 5. Update Address Label & Line
    addr_update_res = user_client.profiles.update_address(
        address_id,
        AddressUpdate(label="Main Distribution Center", line_1="Limuru Road, Unit B"),
    )
    assert addr_update_res.success is True
    assert addr_update_res.data.label == "Main Distribution Center"

    # 6. Delete Address
    del_res = user_client.profiles.delete_address(address_id)
    assert del_res.success is True

    # 7. Confirm Address Removed
    final_list_res = user_client.profiles.list_addresses()
    assert final_list_res.success is True
    assert not any(addr.id == address_id for addr in final_list_res.data)