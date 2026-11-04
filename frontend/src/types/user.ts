/** Users and the colleague directory. */

export interface UserPublic {
  id: string
  email: string
  full_name: string
  roles: string[]
  created_at?: string | null
}

/** A person in the directory any signed-in user may pick from (share, assign, @mention). */
export interface Colleague {
  id: string
  email: string
  full_name: string
  avatar?: string | null
}
