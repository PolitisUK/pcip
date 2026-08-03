import { render } from "@testing-library/react-native";

import { CitizenCentricLogo } from "./CitizenCentricLogo";

describe("CitizenCentricLogo", () => {
  it("uses the required accessibility label", () => {
    const { getByLabelText } = render(<CitizenCentricLogo variant="full" />);

    expect(getByLabelText("Citizen Centric by Politis")).toBeTruthy();
  });

  it("renders the full lockup variant", () => {
    const { getByTestId, queryByTestId } = render(<CitizenCentricLogo variant="full" />);

    expect(getByTestId("citizen-centric-logo-full")).toBeTruthy();
    expect(queryByTestId("citizen-centric-logo-compact")).toBeNull();
  });

  it("renders the compact variant", () => {
    const { getByTestId, queryByTestId } = render(<CitizenCentricLogo variant="compact" />);

    expect(getByTestId("citizen-centric-logo-compact")).toBeTruthy();
    expect(queryByTestId("citizen-centric-logo-full")).toBeNull();
  });
});
