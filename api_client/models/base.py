
from dataclasses import dataclass
from typing import Generic,Optional,TypeVar

T=TypeVar("T")

@dataclass
class ApiResponse(Generic[T]):
    """Standard wrapper returned by service methods"""
    status_code:int
    data:Optional[T]=None
    error:Optional[str]=None
    success:bool=True

