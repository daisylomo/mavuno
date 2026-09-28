module.exports = ({ config }) => {
  if (process.env.EAS_BUILD_PROFILE === 'release-apk' || process.env.MAVUNO_RELEASE_BUILD === '1') {
    const raw = process.env.EXPO_PUBLIC_MAVUNO_API_URL;
    let url;
    try { url = new URL(raw); } catch { throw new Error('Release APK requires a public HTTPS EXPO_PUBLIC_MAVUNO_API_URL.'); }
    const localHost = /^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|.*\.local$)/i.test(url.hostname);
    if (url.protocol !== 'https:' || localHost || !url.pathname.replace(/\/+$/, '').endsWith('/api/v1') ||
        url.username || url.password || url.search || url.hash) {
      throw new Error('Release APK requires a public HTTPS API URL ending in /api/v1.');
    }
  }
  return config;
};
