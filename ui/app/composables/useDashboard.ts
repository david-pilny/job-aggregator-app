import { createSharedComposable } from '@vueuse/core'

const _useDashboard = () => {
  const router = useRouter()

  defineShortcuts({
    'g-j': () => router.push('/'),
    'g-t': () => router.push('/tracker'),
    'g-r': () => router.push('/runs'),
    'g-s': () => router.push('/settings')
  })
}

export const useDashboard = createSharedComposable(_useDashboard)
