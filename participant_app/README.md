# Citizen Centric participant app

The participant app uses the PCIP participant API only. Its invitation flow
accepts an invitation token; participants are never asked to enter a service
address, email address, or password.

## API configuration

Release builds must supply the approved HTTPS PCIP API root at build time:

```sh
flutter build <platform> --dart-define=PCIP_API_BASE_URL=https://approved-pcip-api.example
```

The app fails closed if this value is absent or invalid. It does not accept a
participant-supplied endpoint and will not restore a session for another host.

For isolated debug-only QA, a build may set `PCIP_QA_API_BASE_URL`. Local HTTP
is additionally restricted to debug builds with `PCIP_LOCAL_QA=true` and to
`localhost` or `10.0.2.2`; it is never selected by a release build. Do not put
secrets in dart defines.
