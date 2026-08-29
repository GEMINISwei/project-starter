import { SignupPage, generateSignupMetadata } from "@/modules/auth/public.server"

export const generateMetadata = generateSignupMetadata

export default function Page() {
  return <SignupPage />
}
