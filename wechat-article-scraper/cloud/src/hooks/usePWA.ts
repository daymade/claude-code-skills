'use client';

import { useState, useEffect, useCallback } from 'react';

interface PWAStatus {
  isInstalled: boolean;
  isStandalone: boolean;
  canInstall: boolean;
  isOffline: boolean;
  pushEnabled: boolean;
  swRegistered: boolean;
}

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

export function usePWA() {
  const [status, setStatus] = useState<PWAStatus>({
    isInstalled: false,
    isStandalone: false,
    canInstall: false,
    isOffline: false,
    pushEnabled: false,
    swRegistered: false,
  });

  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);

  // Register service worker
  useEffect(() => {
    if (typeof window === 'undefined' || !('serviceWorker' in navigator)) {
      return;
    }

    const registerSW = async () => {
      try {
        const registration = await navigator.serviceWorker.register('/sw.js');
        console.log('[PWA] Service Worker registered:', registration);

        setStatus(prev => ({ ...prev, swRegistered: true }));

        // Check for updates
        registration.addEventListener('updatefound', () => {
          const newWorker = registration.installing;
          if (newWorker) {
            newWorker.addEventListener('statechange', () => {
              if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                // New version available
                if (confirm('新版本可用，是否刷新更新？')) {
                  window.location.reload();
                }
              }
            });
          }
        });
      } catch (error) {
        console.error('[PWA] Service Worker registration failed:', error);
      }
    };

    registerSW();

    // Check if already installed/standalone
    const isStandalone = window.matchMedia('(display-mode: standalone)').matches ||
                        (window.navigator as any).standalone === true;

    setStatus(prev => ({
      ...prev,
      isStandalone,
      isInstalled: isStandalone,
    }));

    // Listen for beforeinstallprompt
    const handleBeforeInstallPrompt = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptPromptEvent);
      setStatus(prev => ({ ...prev, canInstall: true }));
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt);

    // Listen for app installed
    const handleAppInstalled = () => {
      setDeferredPrompt(null);
      setStatus(prev => ({
        ...prev,
        isInstalled: true,
        canInstall: false,
      }));
      console.log('[PWA] App was installed');
    };

    window.addEventListener('appinstalled', handleAppInstalled);

    // Listen for online/offline
    const handleOnline = () => setStatus(prev => ({ ...prev, isOffline: false }));
    const handleOffline = () => setStatus(prev => ({ ...prev, isOffline: true }));

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    // Set initial offline status
    setStatus(prev => ({ ...prev, isOffline: !navigator.onLine }));

    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
      window.removeEventListener('appinstalled', handleAppInstalled);
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  // Install app
  const install = useCallback(async () => {
    if (!deferredPrompt) {
      return { success: false, error: '无法安装' };
    }

    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;

    setDeferredPrompt(null);
    setStatus(prev => ({ ...prev, canInstall: false }));

    return { success: outcome === 'accepted', outcome };
  }, [deferredPrompt]);

  // Request push notification permission
  const requestPushPermission = useCallback(async () => {
    if (!('Notification' in window)) {
      return { success: false, error: '浏览器不支持推送通知' };
    }

    try {
      const permission = await Notification.requestPermission();
      const enabled = permission === 'granted';

      setStatus(prev => ({ ...prev, pushEnabled: enabled }));

      if (enabled && 'serviceWorker' in navigator) {
        const registration = await navigator.serviceWorker.ready;
        // Subscribe to push (would need VAPID keys from server)
        // const subscription = await registration.pushManager.subscribe({...});
      }

      return { success: enabled, permission };
    } catch (error) {
      console.error('[PWA] Push permission error:', error);
      return { success: false, error: String(error) };
    }
  }, []);

  // Send a test push notification
  const sendTestNotification = useCallback(async (title: string, body: string) => {
    if (!('Notification' in window) || Notification.permission !== 'granted') {
      return { success: false, error: '未获得通知权限' };
    }

    try {
      const registration = await navigator.serviceWorker.ready;
      await registration.showNotification(title, {
        body,
        icon: '/icons/icon-192x192.png',
        badge: '/icons/icon-72x72.png',
      });
      return { success: true };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  }, []);

  // Check for updates
  const checkForUpdate = useCallback(async () => {
    if (!('serviceWorker' in navigator)) {
      return { success: false, error: '不支持Service Worker' };
    }

    try {
      const registration = await navigator.serviceWorker.ready;
      await registration.update();
      return { success: true };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  }, []);

  return {
    status,
    install,
    requestPushPermission,
    sendTestNotification,
    checkForUpdate,
  };
}

// Hook for network status
export function useNetworkStatus() {
  const [isOnline, setIsOnline] = useState(true);
  const [connectionType, setConnectionType] = useState<string>('unknown');

  useEffect(() => {
    if (typeof window === 'undefined') return;

    setIsOnline(navigator.onLine);

    // Get connection info if available
    const connection = (navigator as any).connection;
    if (connection) {
      setConnectionType(connection.effectiveType || 'unknown');

      connection.addEventListener('change', () => {
        setConnectionType(connection.effectiveType || 'unknown');
      });
    }

    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  return { isOnline, connectionType };
}
