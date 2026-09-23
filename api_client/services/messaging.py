from typing import List, Optional
from api_client.models.base import ApiResponse
from api_client.models.messaging import (
    ConversationCreate,
    ConversationResponse,
    MarkReadRequest,
    MessageCreate,
    MessagePage,
    MessageResponse,
    NotificationPreferencesResponse,
    NotificationPreferencesUpdate,
    NotificationResponse,
)
from api_client.services.base import BaseService


class MessagingService(BaseService):
    def create_conversation(self, req: ConversationCreate) -> ApiResponse[ConversationResponse]:
        res = self._execute(method="POST", path="/conversations", json_payload=req.to_dict())
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=ConversationResponse.from_dict(res.data),
            success=True,
        )

    def list_conversations(self) -> ApiResponse[List[ConversationResponse]]:
        res = self._execute(method="GET", path="/conversations")
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=[ConversationResponse.from_dict(c) for c in res.data],
            success=True,
        )

    def send_message(self, conversation_id: str, req: MessageCreate) -> ApiResponse[MessageResponse]:
        res = self._execute(
            method="POST",
            path=f"/conversations/{conversation_id}/messages",
            json_payload=req.to_dict(),
        )
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=MessageResponse.from_dict(res.data),
            success=True,
        )

    def list_messages(
        self, conversation_id: str, cursor: Optional[str] = None, limit: int = 50
    ) -> ApiResponse[MessagePage]:
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        res = self._execute(method="GET", path=f"/conversations/{conversation_id}/messages", params=params)
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=MessagePage.from_dict(res.data),
            success=True,
        )

    def mark_conversation_read(self, conversation_id: str, req: MarkReadRequest) -> ApiResponse[None]:
        res = self._execute(
            method="PUT",
            path=f"/conversations/{conversation_id}/read",
            json_payload=req.to_dict(),
        )
        return ApiResponse(status_code=res.status_code, error=res.error, success=res.success)

    def get_notification_preferences(self) -> ApiResponse[NotificationPreferencesResponse]:
        res = self._execute(method="GET", path="/notification-preferences")
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=NotificationPreferencesResponse.from_dict(res.data),
            success=True,
        )

    def update_notification_preferences(
        self, req: NotificationPreferencesUpdate
    ) -> ApiResponse[NotificationPreferencesResponse]:
        res = self._execute(method="PUT", path="/notification-preferences", json_payload=req.to_dict())
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=NotificationPreferencesResponse.from_dict(res.data),
            success=True,
        )

    def list_notifications(self) -> ApiResponse[List[NotificationResponse]]:
        res = self._execute(method="GET", path="/notifications")
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=[NotificationResponse.from_dict(n) for n in res.data],
            success=True,
        )

    def mark_notification_read(self, notification_id: str) -> ApiResponse[NotificationResponse]:
        res = self._execute(method="PUT", path=f"/notifications/{notification_id}/read")
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=NotificationResponse.from_dict(res.data),
            success=True,
        )