import AsyncStorage from '@react-native-async-storage/async-storage';

export interface AppUser {
  id: string;
  name: string;
  email: string;
  phone: string;
  password?: string;
  role: 'farmer' | 'customer' | 'admin';
  location?: string;
  createdAt: string;
}

const USERS_STORAGE_KEY = '@mavuno_registered_users';
const CURRENT_USER_KEY = '@mavuno_current_user';

/**
 * Normalizes Kenyan and international phone numbers into canonical E.164 format.
 * Examples:
 *  - "+254 712 345 678" -> "+254712345678"
 *  - "0712345678"        -> "+254712345678"
 *  - "0111820845"        -> "+254111820845"
 *  - "+254111820845"     -> "+254111820845"
 */
export function normalizePhone(phone: string): string {
  if (!phone) return '';
  const digits = phone.replace(/\D/g, '');
  if (!digits) return '';
  if (digits.length >= 9) {
    const last9 = digits.slice(-9);
    return `+254${last9}`;
  }
  return digits;
}

/**
 * Checks whether an identifier matches a user record by email, phone, or name.
 */
function matchesIdentifier(user: AppUser, rawIdentifier: string): boolean {
  const cleanId = rawIdentifier.trim().toLowerCase();
  if (!cleanId) return false;

  // 1. Email check (exact lowercase)
  if (user.email && user.email.toLowerCase() === cleanId) {
    return true;
  }

  // 2. Normalized phone check
  const idNormPhone = normalizePhone(cleanId);
  const userNormPhone = normalizePhone(user.phone || '');
  if (idNormPhone && userNormPhone && idNormPhone === userNormPhone) {
    return true;
  }

  // 3. Digit-based phone check (last 9 digits)
  const idDigits = cleanId.replace(/\D/g, '');
  const userDigits = (user.phone || '').replace(/\D/g, '');
  if (idDigits.length >= 8 && userDigits.length >= 8) {
    if (idDigits.slice(-9) === userDigits.slice(-9)) {
      return true;
    }
  }

  // 4. Exact name check (case-insensitive)
  if (user.name && user.name.trim().toLowerCase() === cleanId) {
    return true;
  }

  return false;
}

/** Check if name is a real human/business name rather than a phone number or placeholder */
function isRealName(name: string): boolean {
  if (!name) return false;
  const clean = name.trim().replace(/\s/g, '');
  // If it's all digits or begins with + followed by digits, it's a phone number fallback
  return !/^\+?\d+$/.test(clean);
}

export const userService = {
  /** Get all registered users with deduplication */
  async getUsers(): Promise<AppUser[]> {
    try {
      const data = await AsyncStorage.getItem(USERS_STORAGE_KEY);
      return data ? JSON.parse(data) : [];
    } catch {
      return [];
    }
  },

  /** Register a new user without logging them in */
  async register(params: {
    name: string;
    email: string;
    phone: string;
    password?: string;
    role: 'farmer' | 'customer';
    location?: string;
  }): Promise<AppUser> {
    const users = await this.getUsers();
    const cleanEmail = params.email ? params.email.trim().toLowerCase() : '';
    const cleanPhone = normalizePhone(params.phone);
    const cleanName = params.name.trim();

    // Look for existing registered user
    const existingIndex = users.findIndex((u) => {
      if (cleanEmail && u.email?.toLowerCase() === cleanEmail) return true;
      if (cleanPhone && normalizePhone(u.phone) === cleanPhone) return true;
      return false;
    });

    if (existingIndex !== -1) {
      const existing = users[existingIndex];
      // If the existing record is a phantom user (name was saved as a phone number),
      // heal it with the real registration details instead of throwing an error!
      if (!isRealName(existing.name)) {
        const healedUser: AppUser = {
          ...existing,
          name: cleanName,
          email: cleanEmail || existing.email,
          phone: cleanPhone || existing.phone,
          password: params.password || existing.password,
          role: params.role,
          location: params.location || existing.location || 'Nairobi, Kenya',
        };
        users[existingIndex] = healedUser;
        await AsyncStorage.setItem(USERS_STORAGE_KEY, JSON.stringify(users));
        return healedUser;
      }

      throw new Error('An account with this email or phone number already exists.');
    }

    const newUser: AppUser = {
      id: 'usr_' + Date.now(),
      name: cleanName,
      email: cleanEmail,
      phone: cleanPhone || params.phone.trim(),
      password: params.password,
      role: params.role,
      location: params.location || 'Nairobi, Kenya',
      createdAt: new Date().toISOString(),
    };

    const updatedUsers = [...users, newUser];
    await AsyncStorage.setItem(USERS_STORAGE_KEY, JSON.stringify(updatedUsers));
    return newUser;
  },

  /** Authenticate and store as current active session */
  async login(identifier: string, password?: string): Promise<AppUser> {
    const users = await this.getUsers();
    const cleanId = identifier.trim();

    // Find all users matching the identifier
    const matching = users.filter((u) => matchesIdentifier(u, cleanId));

    if (matching.length === 0) {
      throw new Error(
        'No account found with this email or phone number. Please check your credentials or create an account.'
      );
    }

    // If multiple records exist (e.g. phantom entry + real registered user), pick the one with a real name
    const user = matching.find((u) => isRealName(u.name)) || matching[0];

    if (password && user.password && user.password !== password) {
      throw new Error('Incorrect password. Please try again.');
    }

    // Set as currently active logged-in user
    await AsyncStorage.setItem(CURRENT_USER_KEY, JSON.stringify(user));
    return user;
  },

  /** Retrieve currently logged in user, with self-healing for name display */
  async getCurrentUser(): Promise<AppUser | null> {
    try {
      const data = await AsyncStorage.getItem(CURRENT_USER_KEY);
      if (!data) return null;
      let current: AppUser = JSON.parse(data);

      // Self-healing: If current user's name is a phone number or placeholder,
      // resolve the actual name from USERS_STORAGE_KEY
      if (!isRealName(current.name)) {
        const users = await this.getUsers();
        const realMatch = users.find(
          (u) =>
            isRealName(u.name) &&
            ((current.id && u.id === current.id) ||
              (current.email && u.email?.toLowerCase() === current.email.toLowerCase()) ||
              (current.phone && matchesIdentifier(u, current.phone)))
        );

        if (realMatch) {
          current = { ...current, name: realMatch.name };
          await AsyncStorage.setItem(CURRENT_USER_KEY, JSON.stringify(current));
        }
      }

      return current;
    } catch {
      return null;
    }
  },

  /** Update current user's profile */
  async updateProfile(updates: Partial<AppUser>): Promise<AppUser | null> {
    const current = await this.getCurrentUser();
    if (!current) return null;

    const updatedUser: AppUser = {
      ...current,
      ...updates,
      phone: updates.phone ? normalizePhone(updates.phone) : current.phone,
      email: updates.email ? updates.email.trim().toLowerCase() : current.email,
    };

    // Update current session
    await AsyncStorage.setItem(CURRENT_USER_KEY, JSON.stringify(updatedUser));

    // Update in user list
    const users = await this.getUsers();
    const updatedUsers = users.map((u) => (u.id === updatedUser.id ? updatedUser : u));
    await AsyncStorage.setItem(USERS_STORAGE_KEY, JSON.stringify(updatedUsers));

    return updatedUser;
  },

  /** Clear current session on logout */
  async logout(): Promise<void> {
    await AsyncStorage.removeItem(CURRENT_USER_KEY);
  },
};

