# Support matrix

This matrix shows which management layer currently covers each resource. An
execution function is imperative; a state adds idempotency and Salt test mode.

| Resource | Execution API | State API | Cloud driver | Guide |
| --- | --- | --- | --- | --- |
| Instances | create/get/update/delete and lifecycle | present/absent/running/stopped/initialized | create, query, destroy | [Instances](instances.md) |
| Instance snapshots | list/create/update/rename/restore/delete/publish | present/absent/restored/managed/rotated | no | [Snapshots](snapshots.md) |
| Images and aliases | import/copy/export/refresh/alias/secret | present/installed/absent | list local aliases | [Images](images.md) |
| Profiles | create/update/copy/rename/delete | present/config/absent | exposed as sizes | [Profiles](profiles.md) |
| Networks | create/update/rename/state/leases | present/absent | no | [Networking](networking.md) |
| Network ACLs | list/get/create/update/rename/delete | present/absent | no | [Networking](networking.md) |
| Network forwards | list/get/create/update/delete | present/absent | no | [Networking](networking.md) |
| Network peers | list/get/create/update/delete | present/absent | no | [Networking](networking.md) |
| DNS zones/records | list/get/create/update/delete | present/absent | no | [Networking](networking.md) |
| Storage pools | create/get/update/rename/resources/delete | present/config/absent | no | [Storage](storage.md) |
| Custom volumes | create/update/copy/move/delete | present/config/absent/attached/detached | no | [Storage](storage.md) |
| Volume snapshots | list/create/get/rename/restore/delete | present/absent | no | [Storage](storage.md) |
| Cluster members | info/list/add/remove | present/absent | exposed as locations | [Clusters](cluster.md) |
| Server settings | get/update/set/unset/replace | present/config/absent/managed | no | [Server settings](server-settings.md) |
| Trust entries | list/get/add/update/remove | present/absent | bootstrap dependency | [PKI and TLS](pki-guide.md) |
| Client PKI | read/generate/fingerprint | keypair/trust/client_trusted | local files only | [PKI and TLS](pki-guide.md) |

Functions not represented by a state must be made idempotent by the calling
orchestration if they may run repeatedly. Refer to the API reference for exact
signatures and return structures.
