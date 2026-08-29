"use client"

import { KeyRound, Lock, Shield, User, UserPen } from "lucide-react"
import { ICON_SIZE } from "@/shared/ui"
import { Button } from "@/shared/ui"
import { useT } from "@/shared/i18n/context"
import { MIN_PASSWORD_LENGTH } from "@/shared/session/password-policy"
import { authMessages } from "../i18n"
import { useSignupForm } from "./useSignupForm"
import AuthField, { AuthErrorBanner, PasswordToggle } from "./AuthField"
import styles from "./auth.module.css"

export default function SignupForm() {
  const t = useT(authMessages)
  const {
    values,
    errors,
    isSubmit,
    isPending,
    showPassword,
    notifyState,
    closeNotify,
    changeValue,
    togglePassword,
    goLogin,
    submit,
  } = useSignupForm()

  // 四個欄位共通的狀態，展開進每個 AuthField。
  const fieldState = { disabled: isPending, showError: isSubmit }

  // 每個欄位的 onChange 都是「寫值 + 關掉錯誤提示」，包成一個 factory 以免四處重複。
  function handleChange(field: keyof typeof values) {
    return (value: string) => {
      changeValue(field, value)
      closeNotify()
    }
  }

  return (
    <div className={styles.page}>
      {/* action 而不是 onSubmit，理由見 LoginForm.tsx —— 這裡外洩的是密碼與註冊金鑰。 */}
      <form className={styles.card} action={() => submit()} noValidate>
        <div className={styles.appName}>{t("createAccount")}</div>

        <div className={styles.fields}>
          <AuthErrorBanner open={notifyState.open} message={notifyState.message} />

          <AuthField
            {...fieldState}
            icon={<UserPen size={ICON_SIZE.md} />}
            name="nickname"
            type="text"
            autoComplete="nickname"
            placeholder={t("nickname")}
            value={values.nickname}
            error={errors.nickname}
            onChange={handleChange("nickname")}
          />

          <AuthField
            {...fieldState}
            icon={<User size={ICON_SIZE.md} />}
            name="username"
            type="text"
            autoComplete="username"
            placeholder={t("username")}
            value={values.username}
            error={errors.username}
            onChange={handleChange("username")}
          />

          <AuthField
            {...fieldState}
            icon={<Lock size={ICON_SIZE.md} />}
            name="password"
            type={showPassword ? "text" : "password"}
            autoComplete="new-password"
            placeholder={t("newPasswordPlaceholder", { min: MIN_PASSWORD_LENGTH })}
            ariaLabel={t("password")}
            value={values.password}
            error={errors.password}
            onChange={handleChange("password")}
            trailing={
              <PasswordToggle
                visible={showPassword}
                showLabel={t("showPassword")}
                hideLabel={t("hidePassword")}
                onToggle={togglePassword}
              />
            }
          />

          <AuthField
            {...fieldState}
            icon={<KeyRound size={ICON_SIZE.md} />}
            name="register_key"
            type="password"
            autoComplete="off"
            placeholder={t("registerKey")}
            value={values.register_key}
            error={errors.register_key}
            onChange={handleChange("register_key")}
          />

          <Button type="submit" size="large" fullWidth disabled={isPending}>
            {isPending ? t("creating") : t("createAccount")}
          </Button>

          <Button variant="outlined" fullWidth disabled={isPending} onClick={goLogin}>
            {t("goLogin")}
          </Button>
        </div>

        <div className={styles.securityNote}>
          <Shield size={ICON_SIZE.sm} color="var(--color-primary)" />
          <span>{t("securityNote")}</span>
        </div>
      </form>
    </div>
  )
}
