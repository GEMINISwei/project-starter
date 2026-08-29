// 表單驗證與 query 參數解析的純函式。密碼規則本身住在 `shared/session/password-policy`
// （登入與註冊的規則不同：登入只檢查有沒有填，註冊才檢查強度）。

import { translate } from "@/shared/i18n/dictionary"
import type { Locale } from "@/shared/i18n/locale"
import { validateLoginPassword, validateNewPassword } from "@/shared/session/password-policy"
import { authMessages } from "./i18n"
import { LOGIN_REDIRECT_REASONS } from "./constants"
import type {
  LoginFormErrors,
  LoginFormValues,
  LoginRedirectReason,
  SignupFormErrors,
  SignupFormValues,
} from "./types"

// 收 `locale` 讓這兩支維持純函式（好測），同 `shared/session/password-policy`。
export function validateLoginValues(values: LoginFormValues, locale: Locale) {
  const t = translate(authMessages, locale)
  const errors: LoginFormErrors = {}

  if (!values.username.trim()) {
    errors.username = t("usernameRequired")
  }

  errors.password = validateLoginPassword(values.password, locale)

  return errors
}

export function validateSignupValues(values: SignupFormValues, locale: Locale): SignupFormErrors {
  const t = translate(authMessages, locale)
  const errors: SignupFormErrors = {}

  if (!values.register_key.trim()) errors.register_key = t("registerKeyRequired")
  if (!values.nickname.trim()) errors.nickname = t("nicknameRequired")
  if (!values.username.trim()) errors.username = t("usernameRequired")
  errors.password = validateNewPassword(values.password, locale)

  return errors
}

export function getLoginRedirectReason(
  reason?: string | string[],
): LoginRedirectReason | undefined {
  if (reason === LOGIN_REDIRECT_REASONS.sessionExpired) {
    return reason
  }

  return undefined
}
