import React, {
  createContext,
  PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import Purchases, {
  CustomerInfo,
  CustomerInfoUpdateListener,
  LOG_LEVEL,
  PURCHASES_ERROR_CODE,
  PurchasesOffering,
  PurchasesPackage,
} from 'react-native-purchases';
import RevenueCatUI, {
  PAYWALL_RESULT,
} from 'react-native-purchases-ui';

import { isBackendConfigured } from '@/services/auth-api';
import { Entitlements } from '@/services/social-contracts';
import { socialApi } from '@/services/social-api';
import { userService } from '@/services/user-service';

/**
 * Payment layer only. RevenueCat sells Premium in the app stores; it does not decide who is
 * Premium. After any purchase, restore or account switch the backend is asked to re-verify the
 * purchase with RevenueCat, and screens gate on the backend's answer (`/premium/entitlements`).
 */
export const MAVUNO_ENTITLEMENT = 'mavuno_premium';

const API_KEY = process.env.EXPO_PUBLIC_REVENUECAT_API_KEY;

/** Ask the backend to re-check this account's store purchases and return its verdict. */
async function syncWithBackend(): Promise<Entitlements | null> {
  if (!isBackendConfigured()) return null;
  return socialApi.syncStorePurchases();
}

function errorMessage(error: unknown): string {
  if (
    typeof error === 'object' &&
    error !== null &&
    'message' in error &&
    typeof error.message === 'string'
  ) {
    return error.message;
  }

  return 'An unexpected subscription error occurred.';
}

function wasCancelled(error: unknown): boolean {
  if (typeof error !== 'object' || error === null) return false;

  const purchaseError = error as {
    code?: string;
    userCancelled?: boolean;
  };

  return (
    purchaseError.userCancelled === true ||
    purchaseError.code ===
      PURCHASES_ERROR_CODE.PURCHASE_CANCELLED_ERROR
  );
}

interface RevenueCatContextValue {
  ready: boolean;
  busy: boolean;
  error: string | null;
  customerInfo: CustomerInfo | null;
  currentOffering: PurchasesOffering | null;
  refresh: () => Promise<CustomerInfo>;
  /** Each store action resolves to the backend's entitlements after it re-verified the store. */
  purchase: (purchasePackage: PurchasesPackage) => Promise<Entitlements | null>;
  restore: () => Promise<Entitlements | null>;
  presentPaywall: () => Promise<Entitlements | null>;
  presentCustomerCenter: () => Promise<Entitlements | null>;
  identifyUser: (userId: string) => Promise<void>;
  forgetUser: () => Promise<void>;
}

const RevenueCatContext =
  createContext<RevenueCatContextValue | null>(null);

export function RevenueCatProvider({
  children,
}: PropsWithChildren) {
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [customerInfo, setCustomerInfo] =
    useState<CustomerInfo | null>(null);
  const [currentOffering, setCurrentOffering] =
    useState<PurchasesOffering | null>(null);

  const refresh = useCallback(async () => {
    const info = await Purchases.getCustomerInfo();
    setCustomerInfo(info);
    return info;
  }, []);

  useEffect(() => {
    let mounted = true;

    const listener: CustomerInfoUpdateListener = (info) => {
      if (mounted) setCustomerInfo(info);
    };

    Purchases.addCustomerInfoUpdateListener(listener);

    async function initialize() {
      try {
        if (!API_KEY) {
          throw new Error(
            'EXPO_PUBLIC_REVENUECAT_API_KEY is not configured.',
          );
        }

        const currentUser = await userService.getCurrentUser();

        if (!(await Purchases.isConfigured())) {
          Purchases.setLogLevel(
            __DEV__ ? LOG_LEVEL.DEBUG : LOG_LEVEL.INFO,
          );

          Purchases.configure({
            apiKey: API_KEY,
            appUserID: currentUser?.id ?? null,
          });
        } else if (currentUser?.id) {
          const revenueCatUserId = await Purchases.getAppUserID();

          if (revenueCatUserId !== currentUser.id) {
            await Purchases.logIn(currentUser.id);
          }
        }

        const [info, offerings] = await Promise.all([
          Purchases.getCustomerInfo(),
          Purchases.getOfferings(),
        ]);

        if (!mounted) return;

        setCustomerInfo(info);
        setCurrentOffering(offerings.current);

        if (!offerings.current) {
          setError(
            'RevenueCat has no current Offering. Mark the default Offering as current.',
          );
        }
      } catch (initializationError) {
        if (mounted) setError(errorMessage(initializationError));
      } finally {
        if (mounted) setReady(true);
      }
    }

    void initialize();

    return () => {
      mounted = false;
      Purchases.removeCustomerInfoUpdateListener(listener);
    };
  }, []);

  const identifyUser = useCallback(async (userId: string) => {
    setError(null);

    try {
      const currentId = await Purchases.getAppUserID();

      if (currentId === userId) return;

      const result = await Purchases.logIn(userId);
      setCustomerInfo(result.customerInfo);
      // Purchases made on another device or before signing in now belong to this account.
      // Best effort: RevenueCat's webhook reaches the backend anyway.
      await syncWithBackend().catch((syncError: unknown) => {
        console.warn('Premium sync after sign-in failed:', syncError);
      });
    } catch (identificationError) {
      setError(errorMessage(identificationError));
      throw identificationError;
    }
  }, []);

  const forgetUser = useCallback(async () => {
    setError(null);

    try {
      if (!(await Purchases.isAnonymous())) {
        const info = await Purchases.logOut();
        setCustomerInfo(info);
      }
    } catch (logoutError) {
      setError(errorMessage(logoutError));
      throw logoutError;
    }
  }, []);

  const purchase = useCallback(
    async (purchasePackage: PurchasesPackage) => {
      setBusy(true);
      setError(null);

      try {
        const result =
          await Purchases.purchasePackage(purchasePackage);

        setCustomerInfo(result.customerInfo);
        return await syncWithBackend();
      } catch (purchaseError) {
        if (wasCancelled(purchaseError)) return null;

        setError(errorMessage(purchaseError));
        throw purchaseError;
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  const restore = useCallback(async () => {
    setBusy(true);
    setError(null);

    try {
      const info = await Purchases.restorePurchases();
      setCustomerInfo(info);
      return await syncWithBackend();
    } catch (restoreError) {
      setError(errorMessage(restoreError));
      throw restoreError;
    } finally {
      setBusy(false);
    }
  }, []);

  const presentPaywall = useCallback(async () => {
    setError(null);

    try {
      const result =
        await RevenueCatUI.presentPaywallIfNeeded({
          requiredEntitlementIdentifier: MAVUNO_ENTITLEMENT,
          displayCloseButton: true,
        });

      if (
        result === PAYWALL_RESULT.PURCHASED ||
        result === PAYWALL_RESULT.RESTORED ||
        // The store already holds the entitlement; the backend may simply not know yet.
        result === PAYWALL_RESULT.NOT_PRESENTED
      ) {
        await refresh();
        return await syncWithBackend();
      }

      return null;
    } catch (paywallError) {
      setError(errorMessage(paywallError));
      throw paywallError;
    }
  }, [refresh]);

  const presentCustomerCenter = useCallback(async () => {
    setError(null);

    try {
      await RevenueCatUI.presentCustomerCenter();
      await refresh();
      return await syncWithBackend();
    } catch (customerCenterError) {
      setError(errorMessage(customerCenterError));
      throw customerCenterError;
    }
  }, [refresh]);

  const value = useMemo<RevenueCatContextValue>(
    () => ({
      ready,
      busy,
      error,
      customerInfo,
      currentOffering,
      refresh,
      purchase,
      restore,
      presentPaywall,
      presentCustomerCenter,
      identifyUser,
      forgetUser,
    }),
    [
      ready,
      busy,
      error,
      customerInfo,
      currentOffering,
      refresh,
      purchase,
      restore,
      presentPaywall,
      presentCustomerCenter,
      identifyUser,
      forgetUser,
    ],
  );

  return (
    <RevenueCatContext.Provider value={value}>
      {children}
    </RevenueCatContext.Provider>
  );
}

export function useRevenueCat(): RevenueCatContextValue {
  const context = useContext(RevenueCatContext);

  if (!context) {
    throw new Error(
      'useRevenueCat must be used inside RevenueCatProvider.',
    );
  }

  return context;
}