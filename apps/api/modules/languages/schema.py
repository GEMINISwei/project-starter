from pydantic import BaseModel

from shared.http.errors import Language
from shared.http.schema import SimpleListResponse


class LanguageInfo(BaseModel):
    # 刻意標成 Language 而非 str：這樣 Language enum 會完整出現在 OpenAPI schema 上，
    # 前端才能從產生的型別取得語系字面值聯集，不必手抄一份
    # （見 apps/web/shared/api/entities.ts 與 shared/i18n/locale.ts）。同 PermissionInfo.value。
    value: Language


class LanguageList(SimpleListResponse["LanguageInfo"]):
    pass
