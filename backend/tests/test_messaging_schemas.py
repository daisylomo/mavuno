import pytest
from pydantic import ValidationError

from mavuno.messaging.schemas import MessageCreate


def test_message_body_is_trimmed_and_whitespace_is_rejected() -> None:
    value = MessageCreate(client_message_id="ef10d41b-307d-4946-b291-9c37c12a1049", body=" hello ")
    assert value.body == "hello"
    with pytest.raises(ValidationError):
        MessageCreate(client_message_id="ef10d41b-307d-4946-b291-9c37c12a1049", body="   ")
