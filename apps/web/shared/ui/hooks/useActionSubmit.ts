"use client"

import { useState, useTransition } from "react"
import { getApiFieldErrors, getApiResponseErrorMessage } from "@/shared/api/error"
import { useT } from "@/shared/i18n/context"
import type { ApiResponse } from "@/shared/api/contract"
import { uiMessages } from "../i18n"

export function useActionSubmit() {
  const t = useT(uiMessages)
  const [isPending, startTransition] = useTransition()
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  function submit(
    run: () => Promise<ApiResponse>,
    options: {
      onSuccess: () => void
      onError: (message: string) => void
      errorFallback?: string
    }
  ) {
    setFieldErrors({})
    startTransition(async () => {
      const res = await run()

      if (res.status === "success" || res.status === "info") {
        options.onSuccess()
        return
      }

      setFieldErrors(getApiFieldErrors(res))
      options.onError(getApiResponseErrorMessage(res, options.errorFallback ?? t("actionFailed")))
    })
  }

  // key 就是欄位名，由 shared/api/payload.ts 的 collectFieldErrors 決定（那裡寫了為什麼
  // 不帶 body/query/path 前綴）。這一層刻意不做任何字串加工 —— 一做就會變成兩邊各持
  // 一半的約定，而那條接縫沒有檢查器守著。
  function fieldError(name: string): string | undefined {
    return fieldErrors[name]
  }

  function clearFieldErrors() {
    setFieldErrors({})
  }

  return { isPending, submit, fieldError, clearFieldErrors }
}
