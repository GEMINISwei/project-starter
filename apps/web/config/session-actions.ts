"use server"

import { redirect } from "next/navigation"
import { deleteCookies } from "@/shared/session/cookies.server"

export async function logout() {
  await deleteCookies("access_token")
  redirect("/login")
}
