import { render } from "@testing-library/react-native";

import { SignedOutScreen } from "./SignedOutScreen";

describe("participant screen branding", () => {
  it("renders the full lockup on the signed-out screen", () => {
    const { getByTestId } = render(<SignedOutScreen onRetry={() => {}} />);

    expect(getByTestId("citizen-centric-logo-full")).toBeTruthy();
  });

  it("does not show legacy participant-facing PCIP copy", () => {
    const { queryByText } = render(<SignedOutScreen onRetry={() => {}} />);

    expect(queryByText(/PCIP/i)).toBeNull();
  });
});
