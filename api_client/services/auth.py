
from api_client.models.auth import AuthTokensResponse, LoginRequest,RegisterRequest
from api_client.services.base import BaseService
from api_client.models.base import ApiResponse

class AuthService(BaseService):
    
    def login(self,req:LoginRequest)->ApiResponse[AuthTokensResponse]:
        res=self._execute(
            method="POST",
            path="/auth/login",
            json_payload=req.to_dict(),
        )
        if not res.success or not res.data:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)

        return ApiResponse(
            status_code=res.status_code,
            data=AuthTokensResponse.from_dict(res.data),
            success=True
        )
    def register(self, req: RegisterRequest) -> ApiResponse[AuthTokensResponse]:
        res = self._execute(
            method="POST",
            path="/auth/register",
            json_payload=req.to_dict(),
        )
        if not res.success or not res.data:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)

        return ApiResponse(
            status_code=res.status_code,
            data=AuthTokensResponse.from_dict(res.data),
            success=True,
        )
        