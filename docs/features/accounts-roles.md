# 帳號、角色與密碼

誰能建立帳號、角色與權限怎麼分、後台開放給誰，以及忘記密碼時怎麼辦。為什麼網頁不開註冊見
[ADR 0002](../decisions/0002-no-web-signup.md)。

## 帳號

超級管理者**只能**用 `make db superuser` 建立（見 [`operations.md`](../operations.md#建立超級管理者)）：
第一個、第二個、唯一的超管失聯時的救援都是。網頁上刻意沒有註冊入口，能建立超管的前提是握有主機的
shell，不需要保管任何註冊代碼。

其餘帳號由超級管理者在「使用者管理」頁面建立。需要讓使用者自助註冊的專案自行開發
（Email 驗證、防機器人、限流都要一起考慮）。

## 角色與權限

預設只有一個內建角色 `super_admin`（權限 `*`，涵蓋所有操作與日後新增的權限）。
它**不能經由 API 指派**，只能由 `make db superuser` 產生。新建的使用者沒指定角色時沒有任何權限；
需要 `member` 之類的預設角色，在 `RoleTable.seed_data` 新增（見
[`extending.md`](../extending.md#初始資料seed)）。系統角色（有 `code` 的）的權限、名稱與啟用狀態
都由模板擁有，不能經由 API 修改，畫面上的名稱依 `code` 查前端字典。

### 後台只開放給超級管理者

使用者與角色的管理（後台）只有超級管理者進得去：前端的 `admin/layout.tsx` 只看是不是
超級管理者，後端這些端點一律要求 `Permission.ALL`。角色上的權限是給**一般帳號**的業務功能用的，
沒有任何一個權限能打開後台。

一般帳號對自己帳號的操作（改暱稱、改密碼、語系）集中在設定頁，不需要任何權限。

即使是超級管理者也不能做的事：停用自己、停用超級管理者、指派超級管理者角色、把 `*` 放進一般角色、
修改系統角色。

## 密碼

- 記得舊密碼 → 自己在設定頁改。
- 忘記密碼 → 請超級管理者在後台重設（超級管理者全部失聯時用 `make db superuser` 另建一個）。
  模板沒有 email，所以沒有寄重設連結。

改密碼會讓其他裝置登出，見 [Session](session.md#撤銷)。

## 程式與測試

- 建立超管：[`modules/users/superuser.py`](../../apps/api/modules/users/superuser.py)、
  [`test_superuser.py`](../../apps/api/tests/modules/users/test_superuser.py)
- 系統角色與 seed：[`modules/roles/model.py`](../../apps/api/modules/roles/model.py)
- 後台的限制：[`modules/users/service.py`](../../apps/api/modules/users/service.py)、
  [`modules/roles/service.py`](../../apps/api/modules/roles/service.py)、
  前端 `apps/web/app/(protected)/admin/layout.tsx`
