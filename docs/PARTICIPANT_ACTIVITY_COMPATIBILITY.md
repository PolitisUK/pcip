# Participant activity compatibility

This matrix records the contract shared by the researcher study builder, the
participant API, and the canonical Flutter app in `participant_app`. The
backend identifiers in this document are the complete `ACTIVITY_TYPES` set.

## Compatibility before this change

| Type | Researcher configuration | API response value | Previous Flutter control | Draft/retry | State |
|---|---|---|---|---|---|
| `short_text` | prompt, required, repeatable | `answer` | multi-line text | text draft/queue | Partial |
| `long_text` | prompt, required, repeatable | `answer` | multi-line text | text draft/queue | Supported |
| `single_choice` | ordered options | `choices` (one) | text field using `answer` | wrong payload | Broken |
| `multiple_choice` | ordered options | `choices` | text field using `answer` | wrong payload | Broken |
| `rating` | established 1–10 scale | `answer` | text field | unvalidated text | Broken |
| `slider` | established 1–10 scale | `answer` | text field | unvalidated text | Broken |
| `photo` | media activity | evidence upload | camera/gallery | durable media queue | Supported |
| `audio` | media activity | evidence upload | voice recorder | durable media queue | Supported |
| `video` | media activity | evidence upload | text field | wrong payload | Broken |
| `gps` | current device location | `location` | text field using `answer` | wrong payload | Broken |
| `ranking` | ordered options | `choices` in ranked order | text field | wrong payload | Broken |
| `file` | document upload | evidence upload | text field | wrong payload | Broken |
| unknown | none | none | editable text fallback | could submit invalid data | Unsafe |

## Compatibility after this change

| Type | Participant control | Submitted representation | Draft/offline behaviour | Submitted state |
|---|---|---|---|---|
| `short_text` | single-line text | `answer` | study-scoped draft and queue | locked unless repeatable |
| `long_text` | multi-line text | `answer` | study-scoped draft and queue | locked unless repeatable |
| `single_choice` | native radio group | one configured `choices` value | structured study-scoped draft and queue | locked unless repeatable |
| `multiple_choice` | native checkboxes | configured `choices` values | structured study-scoped draft and queue | locked unless repeatable |
| `rating` | accessible configured-value chips | one permitted `answer` value | structured study-scoped draft and queue | locked unless repeatable |
| `slider` | accessible discrete slider | one permitted `answer` value | structured study-scoped draft and queue | locked unless repeatable |
| `photo` | camera or system photo picker | evidence upload | study-scoped durable media queue | locked unless repeatable |
| `audio` | recorder and playback | evidence upload | study-scoped durable media queue | locked unless repeatable |
| `video` | camera or system video picker | evidence upload | study-scoped durable media queue | locked unless repeatable |
| `gps` | explicit foreground current-location capture and removal | `location` | study-scoped structured draft and queue | locked unless repeatable |
| `ranking` | reorderable list plus labelled up/down controls | every configured `choices` value exactly once in order | structured study-scoped draft and queue | locked unless repeatable |
| `file` | system document picker | evidence upload | study-scoped durable media queue | locked unless repeatable |
| unknown | non-editable compatibility notice | no request allowed | none | fail closed |

Rating and slider options are emitted by the API as the existing web product's
authoritative 1–10 scale. Choice and ranking options continue to come from each
activity's stored researcher configuration.

## Multi-study boundaries

The server remains the authority for study access. `available-studies` returns
only accepted, unrevoked, unexpired invitations with an active enrolment in the
session's organisation. `session/switch` issues a new session bound to the
selected invitation and rejects arbitrary study IDs. The Flutter app shows the
“My studies” control only when more than one server-returned study exists.

Local drafts, response retries, media retries, history, messages, profile data,
and evidence receipts are keyed or tagged by the selected study. A switch
rebuilds the study dashboard with the replacement study-scoped bearer session;
pending work from another study is retained but is not replayed into the new
study. Legacy unscoped local entries are bound once to the active study before
switching is offered.
