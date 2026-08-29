import type { ModuleManifest } from "@/shared/module"

// 推播沒有自己的頁面，是掛在 protected layout 底下的背景能力。
export const PUSH_MODULE = {
  name: "push",
  protectedRoutes: [],
} as const satisfies ModuleManifest
