const { withAppBuildGradle } = require('expo/config-plugins');

/**
 * Marks the Android release build debuggable while keeping the bundled JavaScript, so the APK
 * runs on its own. RevenueCat's Test Store refuses non-debuggable builds (it alerts and crashes
 * on purpose), and app.config.js applies this plugin only when a Test Store key is used.
 */
module.exports = function withDebuggableRelease(config) {
  return withAppBuildGradle(config, (gradle) => {
    const contents = gradle.modResults.contents;
    if (/release\s*\{[^}]*debuggable\s+true/.test(contents)) return gradle;
    const releaseBlock = /(buildTypes\s*\{[\s\S]*?\n\s*release\s*\{)/;
    if (!releaseBlock.test(contents)) {
      throw new Error('with-debuggable-release: could not find the release build type in app/build.gradle.');
    }
    gradle.modResults.contents = contents.replace(
      releaseBlock,
      '$1\n            // RevenueCat Test Store only runs in debuggable builds.\n            debuggable true',
    );
    return gradle;
  });
};
