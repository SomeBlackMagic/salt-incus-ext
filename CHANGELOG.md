The changelog format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

This project uses [Semantic Versioning](https://semver.org/) - MAJOR.MINOR.PATCH

# Changelog

## 1.0.0 (2026-10-06)


### Changed

- Added optional, configurable exponential backoff with jitter to operation and IP
  polling loops while preserving the existing fixed polling behavior by default.
- Expanded the Incus documentation with complete configuration, architecture,
  PKI, image, instance, profile, network, storage, snapshot, cluster, server
  settings, Salt Cloud, support-matrix, limitation, and troubleshooting guides.
  Improved execution/state API navigation and made direct Sphinx builds prefer
  the project's documentation environment.


### Fixed

- Fixed Incus cloud driver loading, Unix-socket adapter callbacks, cleanup, and error handling.


### Added

- Added Unix-socket/HTTPS Incus API client and execution modules for instances,
  snapshots, images and aliases, profiles, networks, ACLs, forwards, peers, DNS
  zones, storage pools, volumes and volume snapshots, server settings, trust
  entries, and cluster members.
- Added an Incus Salt Cloud provider for provisioning, listing, deploying to, and
  destroying containers and virtual machines over Unix-socket and HTTPS
  connections, including cluster locations, image/profile discovery, event
  emission, and configurable IP polling.
- Added declarative Incus trust-store states for bootstrapping Salt Cloud HTTPS client certificates.
- Added state modules for declarative management of instances, instance
  snapshots and retention, images, profiles, networks, ACLs, forwards, peers, DNS
  zones and records, storage pools, volumes and volume snapshots, attachments,
  server settings, cluster members, trust entries, and PKI certificates, with
  idempotent updates and Salt test-mode support.
- Added the `incus_pki` execution module for generating and managing Incus client TLS certificates using local filesystem or Salt SDB storage.
