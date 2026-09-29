from typing import Any,Dict,Optional
import requests
    

from api_client.exceptions import MavunoApiError

from api_client.models.base import ApiResponse


class BaseService:
    def __init__(self,base_url: str,session:requests.Session):
        self.base_url=base_url.rstrip('/')
        self.session=session

    def _execute(
            self,method:str,path:str,
            params:Optional[Dict[str,Any]]=None,
            json_payload: Optional[Dict[str,Any]]=None

    )->ApiResponse:
        url=f"{self.base_url}/{path.lstrip('/')}"
        try:
            res=self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_payload,
                timeout=(10, 65),
            )

            if res.status_code >= 400:
                return ApiResponse(status_code=res.status_code, error=res.text, success=False)

            body = res.json() if res.content else {}
            return ApiResponse(status_code=res.status_code, data=body, success=True)

        except requests.RequestException as exc:
            raise MavunoApiError(f"Network transport error: {exc}") from exc
