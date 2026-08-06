import { fireEvent, render } from "@testing-library/react-native";

import { ConsentRequiredScreen } from "./ConsentRequiredScreen";

describe("ConsentRequiredScreen", () => {
  it("allows the participant to re-check consent without signing out", () => {
    const onCheckAgain = jest.fn();
    const onSignOut = jest.fn();
    const screen = render(
      <ConsentRequiredScreen
        participantDisplayName="Pat"
        onCheckAgain={onCheckAgain}
        onSignOut={onSignOut}
      />,
    );

    fireEvent.press(screen.getByRole("button", { name: "Check consent again" }));

    expect(onCheckAgain).toHaveBeenCalledTimes(1);
    expect(onSignOut).not.toHaveBeenCalled();
  });
});
