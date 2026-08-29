export function isRedirectError(err: unknown) {
  if (typeof err !== "object" || err === null || !("digest" in err)) {
    return false
  }

  return String((err as { digest?: unknown }).digest).startsWith("NEXT_REDIRECT")
}
