Salt Cloud HTTPS bootstrap
==========================

The Incus cloud driver presents a TLS client certificate when it connects to a
remote Incus API. The public certificate must be registered in the server trust
store before that first HTTPS connection. Bootstrap the certificate through a
Salt minion that can access the local Incus Unix socket; do not copy the Salt
Cloud private key to the Incus server.

Register the public certificate
-------------------------------

Distribute the public certificate through pillar or another appropriate Salt
source and apply the following state on the Incus server:

.. code-block:: yaml

    salt-cloud-client:
      incus.trust_present:
        - cert_pem: |
            -----BEGIN CERTIFICATE-----
            ...
            -----END CERTIFICATE-----
        - restricted: false

The state identifies the certificate by its SHA-256 fingerprint. Reusing the
same display name for a different certificate does not produce a false
idempotent result. Changes to the display name, restriction flag, or project
list are updated in place.

Restricted certificates must specify the projects that Salt Cloud may manage:

.. code-block:: yaml

    salt-cloud-project-client:
      incus.trust_present:
        - cert_pem: {{ pillar["incus_cloud_client_certificate"] | yaml_encode }}
        - restricted: true
        - projects:
            - cloud

Configure the cloud provider
----------------------------

After the bootstrap state succeeds, configure Salt Cloud with the corresponding
certificate and private key on the Salt master:

.. code-block:: yaml

    my-incus:
      driver: incus
      connection:
        type: https
        url: https://incus.example.com:8443
        cert_storage:
          type: local_files
          cert: /etc/salt/pki/incus/client.crt
          key: /etc/salt/pki/incus/client.key
          verify: /etc/salt/pki/incus/server.crt

Revoke access
-------------

Use the fingerprint or the public certificate for unambiguous removal:

.. code-block:: yaml

    retired-salt-cloud-client:
      incus.trust_absent:
        - fingerprint: 0123456789abcdef...

When no fingerprint or certificate is supplied, ``trust_absent`` searches by
display name and refuses to remove anything if more than one entry matches.
