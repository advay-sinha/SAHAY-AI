const { AndroidConfig, withAndroidManifest } = require("expo/config-plugins");

function setCleartextPolicy(androidManifest, buildProfile) {
  const application = AndroidConfig.Manifest.getMainApplicationOrThrow(androidManifest);
  if (buildProfile === "preview") {
    application.$["android:usesCleartextTraffic"] = "true";
  } else if (buildProfile === "production") {
    application.$["android:usesCleartextTraffic"] = "false";
  }
  return androidManifest;
}

function withPreviewCleartextTraffic(config) {
  return withAndroidManifest(config, (mod) => {
    mod.modResults = setCleartextPolicy(mod.modResults, process.env.EAS_BUILD_PROFILE);
    return mod;
  });
}

module.exports = withPreviewCleartextTraffic;
module.exports.setCleartextPolicy = setCleartextPolicy;
