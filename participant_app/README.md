# Citizen Centric participant app

The participant app uses the PCIP participant API only. The normal participant
journey uses an invitation, study-specific consent, and a short-lived,
single-use app access code. A separately provisioned reusable username and
password is also available for authorised review and accessibility use cases;
the invitation/app-code option remains the default. Participants are never
asked to enter a service address.

## Accessibility

The app follows the device text-size setting on Android and iOS. A participant
can also choose **Standard**, **Large**, or **Extra Large** in Profile; this
supplements rather than replaces the device setting. Activity icons are
decorative, while activity type and state are exposed as text and screen-reader
semantics. Primary controls use at least 48 logical-pixel touch targets.

## API configuration

Release builds default to the approved PCIP API root configured by the existing
Azure deployment workflow. A signed-build pipeline may set the same approved
HTTPS root explicitly at build time:

```sh
flutter build <platform> --dart-define=PCIP_API_BASE_URL=https://approved-pcip-api.example
```

The app fails closed for an invalid endpoint. It does not accept a
participant-supplied endpoint and will not restore a session for another host.

For isolated debug-only QA, a build may set `PCIP_QA_API_BASE_URL`. Local HTTP
is additionally restricted to debug builds with `PCIP_LOCAL_QA=true` and to
`localhost` or `10.0.2.2`; it is never selected by a release build. Do not put
secrets in dart defines.
