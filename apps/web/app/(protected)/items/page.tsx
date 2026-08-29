import { ItemsPage, generateItemsMetadata, type ItemsPageProps } from "@/modules/items/public.server"

export const generateMetadata = generateItemsMetadata

export default function Page(props: ItemsPageProps) {
  return <ItemsPage {...props} />
}
