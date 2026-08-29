from fastapi import APIRouter, Depends

from shared.auth.dependency import check_user_permission
from shared.http.errors import Language

from .schema import LanguageInfo, LanguageList

router = APIRouter(prefix="/languages", tags=["languages"])


@router.get("/")
async def get_language_list_route(
    _=Depends(check_user_permission()),
) -> LanguageList:
    """列出這個 API 支援的訊息語系。"""
    return LanguageList(
        list_data=[LanguageInfo(value=language) for language in Language],
        count=len(Language),
    )
