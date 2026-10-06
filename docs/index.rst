``incus``: Integrate Salt with Incus
====================================

Manage Incus containers, virtual machines, networks, storage, images,
certificates, and clusters with Salt execution modules, idempotent states, and
salt-cloud. Local Unix-socket and remote mutually authenticated HTTPS
connections use the same resource interface.

Start with :doc:`topics/installation` and :doc:`topics/quickstart`. The
:doc:`topics/architecture` guide explains how states, execution modules, the
client, and the Incus API fit together.

.. toctree::
  :maxdepth: 2
  :caption: Guides
  :hidden:

  topics/installation
  topics/configuration
  topics/architecture
  topics/pki-guide
  topics/quickstart
  topics/images
  topics/instances
  topics/profiles
  topics/networking
  topics/storage
  topics/snapshots
  topics/cluster
  topics/server-settings
  topics/cloud-driver
  topics/support-matrix
  topics/limitations
  topics/troubleshooting
  topics/contributing

.. toctree::
  :maxdepth: 2
  :caption: Provided Modules
  :hidden:

  ref/modules/index
  ref/states/index
  ref/clouds/index

.. toctree::
  :maxdepth: 2
  :caption: Reference
  :hidden:

  changelog
  Development

Module overview
===============

Execution modules provide the imperative Incus client and resource operations:

* ``incus_mod`` -- transport, configuration, and asynchronous operation client.
* ``incus_instance_mod`` -- instances, lifecycle, snapshots, and cloud-init.
* ``incus_network_mod`` -- networks, ACLs, forwards, peers, and DNS zones.
* ``incus_storage_pool_mod`` and ``incus_volume_mod`` -- pools and volumes.
* ``incus_image_mod`` and ``incus_profile_mod`` -- images and reusable profiles.
* ``incus_cluster_mod``, ``incus_settings_mod``, and ``incus_trust_mod`` --
  server-wide administration.
* ``incus_pki_mod`` -- client certificate generation and storage.

State modules expose matching ``present`` and ``absent`` workflows plus
resource-specific lifecycle, configuration, attachment, snapshot, and rotation
states. All state functions support Salt test mode and report planned or
applied values in ``changes``. See :doc:`ref/modules/index` and
:doc:`ref/states/index` for the full API.


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
