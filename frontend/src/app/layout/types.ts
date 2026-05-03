export type ProtectedState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; categoryCount: number }
  | { status: 'error'; message: string }
