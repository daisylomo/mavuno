import { Href, Redirect } from 'expo-router';
import { ReactNode, useEffect, useState } from 'react';
import { ActivityIndicator, View } from 'react-native';

import { AppUser, userService } from '@/services/user-service';

type Role = AppUser['role'];

const roleHome: Record<Role, Href> = {
  admin: '/admin',
  farmer: '/farmer',
  customer: '/customer',
};

export default function RoleGate({
  allowedRoles,
  children,
}: {
  allowedRoles: readonly Role[];
  children: ReactNode;
}) {
  const [user, setUser] = useState<AppUser | null>();

  useEffect(() => {
    let active = true;
    userService.getCurrentUser().then((current) => {
      if (active) setUser(current);
    });
    return () => { active = false; };
  }, []);

  if (user === undefined) {
    return <View style={{ flex: 1, justifyContent: 'center' }}><ActivityIndicator /></View>;
  }
  if (!user) return <Redirect href="/auth/login" />;
  if (!allowedRoles.includes(user.role)) return <Redirect href={roleHome[user.role] ?? '/auth/login'} />;
  return <>{children}</>;
}
