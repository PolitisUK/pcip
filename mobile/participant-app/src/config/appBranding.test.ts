const appConfig = require("../../app.json") as {
  expo: {
    name: string;
    icon: string;
    android: {
      adaptiveIcon: {
        foregroundImage: string;
      };
    };
  };
};

describe("app branding config", () => {
  it("sets the participant-facing app name to Citizen Centric", () => {
    expect(appConfig.expo.name).toBe("Citizen Centric");
  });

  it("uses the square Citizen Centric brand mark as app icon", () => {
    expect(appConfig.expo.icon).toBe("./assets/citizen-centric-brand-mark.png");
    expect(appConfig.expo.android.adaptiveIcon.foregroundImage).toBe("./assets/citizen-centric-brand-mark.png");
  });
});
