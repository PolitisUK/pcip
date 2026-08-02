# API Client Foundation

This directory provides a typed participant API foundation for the mobile app.

- `generated/participant-api-types.ts`: checked-in TypeScript type baseline aligned with the current OpenAPI contract.
- `participantApi.ts`: thin endpoint wrappers for session exchange/status/revoke.
- `client.ts`: authenticated fetch wrapper using the environment base URL.

Regeneration command (once OpenAPI updates are approved):

```sh
npm run generate:api-types
```
