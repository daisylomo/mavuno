import uuid
import pytest
from api_client.client import MavunoClient
from api_client.models.auth import LoginRequest, RegisterRequest
from api_client.models.profiles import AddressCreate, AddressUpdate, ProfileUpdate


def test_auth_and_profile_lifecycle(client: MavunoClient):
    unique_phone = f"+2547{str(uuid.uuid4().int)[:8]}"
    password = "SecurePassword123!"

    # Register
    reg_res = client.auth.register(
        RegisterRequest(
            phone=unique_phone,
            password=password,
            role="buyer",
        )
    )
    assert reg_res.success is True, f"Registration failed: {reg_res.error}"
    assert reg_res.data is not None

    # Login
    login_res = client.auth.login(
        LoginRequest(identifier=unique_phone, password=password)
    )
    assert login_res.success is True, f"Login failed: {login_res.error}"
    assert login_res.data is not None
    client.set_auth_token(login_res.data.access_token)

    # Fetch Profile (registration always seeds the default display name)
    profile_res = client.profiles.get_profile()
    assert profile_res.success is True
    assert profile_res.data is not None
    assert profile_res.data.display_name == "Mavuno User"

    # Update Profile
    update_res = client.profiles.update_profile(
        ProfileUpdate(display_name="Jane Wanjiku", bio="Fresh produce buyer")
    )
    assert update_res.success is True
    assert update_res.data.display_name == "Jane Wanjiku"

    # Address CRUD
    addr_create = client.profiles.create_address(
        AddressCreate(
            label="Home Delivery",
            line_1="Argwings Kodhek Rd",
            locality="Kilimani",
            county="Nairobi",
            is_default=True,
        )
    )
    assert addr_create.success is True
    address_id = addr_create.data.id

    addr_list = client.profiles.list_addresses()
    assert addr_list.success is True
    assert address_id in [a.id for a in addr_list.data]

    addr_update = client.profiles.update_address(
        address_id, AddressUpdate(label="Office Delivery")
    )
    assert addr_update.success is True
    assert addr_update.data.label == "Office Delivery"

    del_res = client.profiles.delete_address(address_id)
    assert del_res.success is True
