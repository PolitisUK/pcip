const appConfig = require("../../app.json") as {
  expo: {
    name: string;
    icon: string;
    splash: {
      image: string;
    };
    android: {
      adaptiveIcon: {
        foregroundImage: string;
        backgroundImage?: string;
      };
    };
  };
};

describe("app branding config", () => {
  it("sets the participant-facing app name to Citizen Centric", () => {
    expect(appConfig.expo.name).toBe("Citizen Centric");
  });

  it("uses the square Citizen Centric brand mark as app icon", () => {
    expect(appConfig.expo.icon).toBe("./assets/citizen-centric-app-icon.png");
    expect(appConfig.expo.android.adaptiveIcon.foregroundImage).toBe("./assets/android-icon-foreground.png");
    expect(appConfig.expo.android.adaptiveIcon.backgroundImage).toBeUndefined();
    expect(appConfig.expo.splash.image).toBe("./assets/splash-icon.png");
  });
});
